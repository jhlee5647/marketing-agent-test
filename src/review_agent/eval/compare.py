from dataclasses import dataclass

# 기준선에서 모든 회차를 통과하던 케이스가 이 비율 이하로 떨어지면 회귀다.
REGRESSION_RATE = 1 / 3


@dataclass
class Comparison:
    """현재 평가 결과를 기준선과 견준 결과."""

    verdict: str
    regressed: list[str]
    newly_passing: list[str]
    markdown: str


def compare(current: dict, baseline: dict | None) -> Comparison:
    """현재 결과를 기준선과 견주어 회귀를 판정하고 리포트를 만든다.

    판정은 케이스 단위로만 한다. 총점은 상쇄를 허용해서, 거절 케이스가 무너지고 주제 케이스가 좋아지면
    총점은 그대로지만 실제로는 핵심 약속이 깨진 것이다. 규모가 다르면 정답 자체가 다르므로 품질을
    비교하지 않고 시간과 자원만 견준다.

    Returns:
        판정, 회귀한 케이스, 새로 통과하게 된 케이스, 그리고 사람이 읽을 마크다운 리포트.
    """
    if baseline is None:
        return Comparison("기준선 없음", [], [], _single_report(current))
    if current["scale"]["label"] != baseline["scale"]["label"]:
        return Comparison("규모 다름", [], [], _across_scales_report(current, baseline))

    before = {case["id"]: case for case in baseline["cases"]}
    regressed, newly_passing = [], []
    for case in current["cases"]:
        was = before.get(case["id"])
        if was is None:
            continue
        if was["passed"] == was["total"] and case["passed"] / case["total"] <= REGRESSION_RATE:
            regressed.append(case["id"])
        elif was["passed"] < was["total"] and case["passed"] == case["total"]:
            newly_passing.append(case["id"])
    verdict = "회귀" if regressed else "이상 없음"
    return Comparison(verdict, regressed, newly_passing, _comparison_report(current, baseline, verdict, regressed, newly_passing))


def _comparison_report(current: dict, baseline: dict, verdict: str, regressed: list[str], newly: list[str]) -> str:
    before = {case["id"]: case for case in baseline["cases"]}
    lines = [
        f"# 평가 비교: {current['run_id']} (현재) vs {baseline['run_id']} (기준선)",
        "",
        f"**판정: {verdict}**" + (f" — 회귀 {len(regressed)}건" if regressed else ""),
        "",
        _conditions_table(current, baseline),
        "",
        "## 회귀한 케이스",
        "",
    ]
    lines += [_change_line(before[case_id], _case(current, case_id)) for case_id in regressed] or ["없음"]
    lines += ["", "## 새로 통과하게 된 케이스", ""]
    lines += [_change_line(before[case_id], _case(current, case_id)) for case_id in newly] or ["없음"]
    lines += [
        "",
        "## 통과율 (판정에는 쓰지 않는다)",
        "",
        f"전체 {baseline['summary']['passed']}/{baseline['summary']['total']} →"
        f" {current['summary']['passed']}/{current['summary']['total']}",
        "",
        "## 소요 시간과 토큰 (판정에는 쓰지 않는다)",
        "",
        _resources_table(current, baseline),
        "",
        f"실패한 회차의 답변 전문은 `evals/details/{current['run_id']}.json`에 있다.",
    ]
    return "\n".join(lines) + "\n"


def _single_report(current: dict) -> str:
    summary = current["summary"]
    by_type = " · ".join(f"{name} {counts['passed']}/{counts['total']}" for name, counts in summary["by_type"].items())
    agreement = summary["judge_agreement"]
    lines = [
        f"# 평가 결과: {current['run_id']}",
        "",
        "비교할 기준선이 없습니다. 이 결과가 기준선이 됩니다.",
        "",
        _conditions_table(current, None),
        "",
        "## 통과",
        "",
        f"전체 {summary['passed']}/{summary['total']} 회차" + (f" · 유형별 {by_type}" if by_type else ""),
        "",
        "### 케이스별",
        "",
    ]
    lines += [
        f"- `{case['id']}` ({case['type']}) {case['passed']}/{case['total']}"
        + _reasons(case)
        for case in current["cases"]
    ]
    lines += [
        "",
        "## 소요 시간과 토큰",
        "",
        f"- 질문당 중앙값 {summary['question_seconds']['median']:.1f}s · 최대 {summary['question_seconds']['max']:.1f}s",
        "- 모듈별 " + " · ".join(f"{label} {ms / 1000:.1f}s" for label, ms in summary["module_ms"].items()),
        f"- 토큰 입력 {summary['tokens'].get('input', 0)} · 출력 {summary['tokens'].get('output', 0)}"
        f" · 질문당 중앙값 {summary['question_tokens']['median']:.0f}",
        f"- 심판 토큰 입력 {summary['judge_tokens'].get('input', 0)} · 출력 {summary['judge_tokens'].get('output', 0)}",
        f"- 심판이 사람 라벨과 일치 {agreement['matched']}/{agreement['of']}",
        "",
        "## 적재",
        "",
        _load_line(current),
        "",
        f"답변 전문은 `evals/details/{current['run_id']}.json`에 있다.",
    ]
    return "\n".join(lines) + "\n"


def _across_scales_report(current: dict, baseline: dict) -> str:
    return "\n".join([
        f"# 규모 비교: {current['run_id']} vs {baseline['run_id']}",
        "",
        f"규모 라벨이 다릅니다({baseline['scale']['label']} vs {current['scale']['label']})."
        " 데이터가 다르면 정답 자체가 다르므로 **품질은 비교하지 않습니다.** 시간과 자원만 견줍니다.",
        "",
        _conditions_table(current, baseline),
        "",
        _resources_table(current, baseline),
        "",
    ]) + "\n"


def _conditions_table(current: dict, baseline: dict | None) -> str:
    rows = [
        ("규모", lambda run: f"{run['scale']['label']} (상품 {run['scale']['products']} · 리뷰 {run['scale']['reviews']})"),
        ("모델", lambda run: run["model"]),
        ("심판", lambda run: run["judge_model"] or "없음"),
        ("프롬프트 해시", lambda run: run["prompt_hash"]),
        ("커밋", lambda run: run["commit"]),
    ]
    if baseline is None:
        return "\n".join(["| 조건 | 값 |", "|---|---|"] + [f"| {name} | {value(current)} |" for name, value in rows])
    return "\n".join(
        ["| 조건 | 기준선 | 현재 |", "|---|---|---|"]
        + [f"| {name} | {value(baseline)} | {value(current)} |" for name, value in rows]
    )


def _resources_table(current: dict, baseline: dict) -> str:
    def row(name, pick):
        return f"| {name} | {pick(baseline)} | {pick(current)} |"

    return "\n".join([
        "| 값 | 기준선 | 현재 |",
        "|---|---|---|",
        row("질문당 중앙값", lambda run: f"{run['summary']['question_seconds']['median']:.1f}s"),
        row("질문당 최대", lambda run: f"{run['summary']['question_seconds']['max']:.1f}s"),
        row("모듈별", lambda run: " · ".join(f"{k} {v / 1000:.1f}s" for k, v in run["summary"]["module_ms"].items())),
        row("토큰 입력", lambda run: str(run["summary"]["tokens"].get("input", 0))),
        row("토큰 출력", lambda run: str(run["summary"]["tokens"].get("output", 0))),
        row("심판 토큰", lambda run: str(sum(run["summary"]["judge_tokens"].values()))),
        row("벡터 저장소 로드", lambda run: f"{run['vector_store_open_ms'] / 1000:.1f}s"),
        row("적재", _load_line),
    ])


def _load_line(run: dict) -> str:
    metrics = run["load_metrics"]
    if metrics is None:
        return "측정값 없음"
    return (
        f"{metrics['load_seconds'] / 60:.1f}분 (임베딩 {metrics['embedding_seconds'] / 60:.1f}분)"
        f" · SQLite {metrics['db_bytes'] / 1e6:.0f}MB · 벡터 {metrics['vectors_bytes'] / 1e6:.0f}MB"
    )


def _case(run: dict, case_id: str) -> dict:
    return next(case for case in run["cases"] if case["id"] == case_id)


def _change_line(was: dict, now: dict) -> str:
    return f"- `{now['id']}` ({now['type']}) {was['passed']}/{was['total']} → {now['passed']}/{now['total']}{_reasons(now)}"


def _reasons(case: dict) -> str:
    reasons = {attempt["fail_reason"] for attempt in case["runs"] if attempt.get("fail_reason")}
    return f" — {' · '.join(sorted(reasons))}" if reasons else ""
