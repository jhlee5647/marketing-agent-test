from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

from review_agent.eval.cases import Case
from review_agent.eval.judge import JudgeVerdict
from review_agent.eval.scoring import score_answer, score_trajectory, verify_evidence


@dataclass
class TurnResult:
    """질문 하나를 처리한 결과. 마케터가 받은 답변과, 그 답변에 이르기까지 관측한 것들이다."""

    answer: str
    trajectory: list[dict] = field(default_factory=list)
    timings_ms: dict[str, list[float]] = field(default_factory=dict)
    tokens: dict[str, int] = field(default_factory=dict)
    embedding_calls: int = 0


Execute = Callable[[Sequence[str]], list[TurnResult]]
Judge = Callable[[str, str, str], JudgeVerdict]


def evaluate(cases: list[Case], db_path: Path, execute: Execute, judge: Judge | None = None, runs: int = 3) -> dict:
    """케이스 전부를 `runs`회씩 실행해 채점한다.

    실행기와 심판을 주입받으므로 하네스는 에이전트가 무엇으로 만들어졌는지, 적재 데이터가 어떤 저장소에 있는지 모른다.
    회차가 통과하려면 답변 채점·궤적 채점·근거 검증을 모두 만족해야 한다.
    여러 턴짜리 케이스는 마지막 턴만 채점한다. 앞 턴까지 채점하면 앞 턴의 실패가 뒤 턴의 실패를 유발해 이중으로 계산된다.

    Returns:
        케이스별 통과 횟수와 회차별 채점 결과를 담은 평가 결과.
    """
    results = [_evaluate_case(case, db_path, execute, judge, runs) for case in cases]
    return {"cases": results, "summary": _summarize(results)}


def _summarize(results: list[dict]) -> dict:
    """전체·유형별 통과 횟수, 질문당 소요 시간, 모듈별 시간, 토큰 합을 모은다. 판정에 쓰는 값은 아니다."""
    attempts = [attempt for case in results for attempt in case["runs"]]
    by_type: dict[str, dict[str, int]] = {}
    for case in results:
        counts = by_type.setdefault(case["type"], {"passed": 0, "total": 0})
        counts["passed"] += case["passed"]
        counts["total"] += case["total"]
    module_ms: dict[str, float] = {}
    tokens: dict[str, int] = {}
    judge_tokens: dict[str, int] = {}
    for attempt in attempts:
        for name, count in attempt["judge_tokens"].items():
            judge_tokens[name] = judge_tokens.get(name, 0) + count
        for label, durations in attempt["timings_ms"].items():
            if label != "total":  # 질문당 총시간은 모듈이 아니므로 분해에 섞지 않는다.
                module_ms[label] = module_ms.get(label, 0.0) + sum(durations)
        for name, count in attempt["tokens"].items():
            tokens[name] = tokens.get(name, 0) + count
    seconds = [sum(attempt["timings_ms"].get("total", [])) / 1000 for attempt in attempts]
    per_question = [sum(attempt["tokens"].values()) for attempt in attempts]
    return {
        "passed": sum(case["passed"] for case in results),
        "total": sum(case["total"] for case in results),
        "by_type": by_type,
        "question_seconds": {"median": median(seconds) if seconds else 0.0, "max": max(seconds, default=0.0)},
        "question_tokens": {"median": median(per_question) if per_question else 0, "total": sum(per_question)},
        "module_ms": module_ms,
        "tokens": tokens,
        "judge_tokens": judge_tokens,
        "judge_agreement": _judge_agreement(results),
        "embedding_calls": sum(attempt["embedding_calls"] for attempt in attempts),
    }



def _evaluate_case(case: Case, db_path: Path, execute: Execute, judge: Judge | None, runs: int) -> dict:
    attempts = []
    for _ in range(runs):
        turns = execute(case.turns)
        attempts.append(_score(case, turns, db_path, judge))
    return {
        "id": case.id,
        "type": case.type,
        "turns": case.turns,
        "passed": sum(bool(a["answer_ok"]) and a["trajectory_ok"] and a["evidence_ok"] for a in attempts),
        "total": runs,
        "resolved": case.resolved,
        "human_label": case.human_label,
        "runs": attempts,
    }


def _score(case: Case, turns: list[TurnResult], db_path: Path, judge: Judge | None) -> dict:
    last = turns[-1]
    verdict = _judged(case, last.answer, judge)
    if verdict is not None:
        answer_ok, answer_reason = verdict.passed, verdict.reason
    elif case.rubric is not None:
        # 심판 없이 돈 축약 측정. 답변은 채점하지 않았다는 뜻으로 남긴다(실패와 구별한다).
        answer_ok, answer_reason = None, "심판을 부르지 않아 답변을 채점하지 않았다"
    else:
        answer_ok, answer_reason = score_answer(case, last.answer, db_path)
    trajectory_ok, trajectory_reason = score_trajectory(case, last.trajectory)
    evidence_ok, evidence_reason = verify_evidence(last.answer, db_path)
    return {
        "answer_ok": answer_ok,
        "trajectory_ok": trajectory_ok,
        "evidence_ok": evidence_ok,
        "fail_reason": (not answer_ok and answer_reason) or trajectory_reason or evidence_reason or None,
        "judge_tokens": verdict.tokens if verdict else {},
        "judge_passed": verdict.passed if verdict else None,
        "trajectory": last.trajectory,
        "timings_ms": _merge_timings(turns),
        "tokens": _sum_tokens(turns),
        "embedding_calls": sum(turn.embedding_calls for turn in turns),
        "answer": last.answer,
    }


def _judge_agreement(results: list[dict]) -> dict:
    """사람이 매긴 라벨이 있는 케이스에서 심판의 판정이 그 라벨과 얼마나 맞는지 센다.

    심판을 믿어도 되는지를 재는 값이다. 낮으면 루브릭 채점 결과를 그대로 읽으면 안 된다.
    """
    labelled = [
        (attempt["judge_passed"], case["human_label"] == "pass")
        for case in results
        if case.get("human_label") is not None
        for attempt in case["runs"]
    ]
    return {"matched": sum(verdict == label for verdict, label in labelled), "of": len(labelled)}


def _judged(case: Case, answer: str, judge: Judge | None) -> JudgeVerdict | None:
    """루브릭이 있는 케이스는 심판이 채점한다. 정답이 하나로 정해지지 않기 때문이다.

    심판이 없으면 부르지 않는다. 규모가 다른 점끼리는 품질을 비교하지 않으므로, 축약 측정은 심판을 두지 않는다.
    """
    if case.rubric is None or judge is None:
        return None
    return judge(case.rubric, case.turns[-1], answer)


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
