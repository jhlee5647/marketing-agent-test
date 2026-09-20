from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from review_agent.eval.cases import Case
from review_agent.eval.scoring import score_answer, score_trajectory


@dataclass
class TurnResult:
    """질문 하나를 처리한 결과. 마케터가 받은 답변과, 그 답변에 이르기까지 관측한 것들이다."""

    answer: str
    calls: list[dict] = field(default_factory=list)
    timings_ms: dict[str, list[float]] = field(default_factory=dict)
    tokens: dict[str, int] = field(default_factory=dict)
    embedding_calls: int = 0


Execute = Callable[[Sequence[str]], list[TurnResult]]


def evaluate(cases: list[Case], db_path: Path, execute: Execute, runs: int = 3) -> dict:
    """케이스 전부를 `runs`회씩 실행해 채점한다.

    실행기를 주입받으므로 하네스는 에이전트가 무엇으로 만들어졌는지, 적재 데이터가 어떤 저장소에 있는지 모른다.
    여러 턴짜리 케이스는 마지막 턴만 채점한다. 앞 턴까지 채점하면 앞 턴의 실패가 뒤 턴의 실패를 유발해 이중으로 계산된다.

    Returns:
        케이스별 통과 횟수와 회차별 채점 결과를 담은 평가 결과.
    """
    results = [_evaluate_case(case, db_path, execute, runs) for case in cases]
    return {"cases": results, "summary": _summarize(results)}


def _summarize(results: list[dict]) -> dict:
    """전체·유형별 통과 횟수, 질문당 소요 시간, 모듈별 시간, 토큰 합을 모은다. 판정에 쓰는 값은 아니다."""
    attempts = [attempt for case in results for attempt in case["runs"]]
    by_type: dict[str, dict[str, int]] = {}
    for case in results:
        counts = by_type.setdefault(case["type"], {"passed": 0, "of": 0})
        counts["passed"] += case["passed"]
        counts["of"] += case["of"]
    module_ms: dict[str, float] = {}
    tokens: dict[str, int] = {}
    for attempt in attempts:
        for label, durations in attempt["timings_ms"].items():
            module_ms[label] = module_ms.get(label, 0.0) + sum(durations)
        for name, count in attempt["tokens"].items():
            tokens[name] = tokens.get(name, 0) + count
    seconds = sorted(sum(attempt["timings_ms"].get("total", [])) / 1000 for attempt in attempts)
    return {
        "passed": sum(case["passed"] for case in results),
        "of": sum(case["of"] for case in results),
        "by_type": by_type,
        "question_seconds": {"median": _median(seconds), "max": max(seconds, default=0.0)},
        "module_ms": module_ms,
        "tokens": tokens,
        "embedding_calls": sum(attempt["embedding_calls"] for attempt in attempts),
    }


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2


def _evaluate_case(case: Case, db_path: Path, execute: Execute, runs: int) -> dict:
    attempts = []
    for _ in range(runs):
        turns = execute(case.turns)
        attempts.append(_score(case, turns, db_path))
    return {
        "id": case.id,
        "type": case.type,
        "passed": sum(a["answer_ok"] and a["trajectory_ok"] for a in attempts),
        "of": runs,
        "resolved": case.resolved,
        "runs": attempts,
    }


def _score(case: Case, turns: list[TurnResult], db_path: Path) -> dict:
    last = turns[-1]
    answer_ok, answer_reason = score_answer(case, last.answer, db_path)
    trajectory_ok, trajectory_reason = score_trajectory(case, last.calls)
    return {
        "answer_ok": answer_ok,
        "trajectory_ok": trajectory_ok,
        "fail_reason": answer_reason or trajectory_reason,
        "calls": last.calls,
        "timings_ms": _merge_timings(turns),
        "tokens": _sum_tokens(turns),
        "embedding_calls": sum(turn.embedding_calls for turn in turns),
        "answer": last.answer,
    }


def _merge_timings(turns: list[TurnResult]) -> dict[str, list[float]]:
    merged: dict[str, list[float]] = {}
    for turn in turns:
        for label, durations in turn.timings_ms.items():
            merged.setdefault(label, []).extend(durations)
    return merged


def _sum_tokens(turns: list[TurnResult]) -> dict[str, int]:
    summed: dict[str, int] = {}
    for turn in turns:
        for name, count in turn.tokens.items():
            summed[name] = summed.get(name, 0) + count
    return summed
