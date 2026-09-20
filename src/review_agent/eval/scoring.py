import operator
import re
from pathlib import Path

from review_agent.eval.cases import Case
from review_agent.sql_tool import run_sql

# 에이전트는 거절을 여러 말로 한다. 실제 답변에서 관측한 표현을 모은 목록이다.
REFUSAL_PHRASES = ["답할 수 없", "답변할 수 없", "답해 드릴 수 없", "알 수 없", "확인할 수 없", "들어 있지 않", "포함되어 있지 않"]
COMPARISONS = {"<=": operator.le, ">=": operator.ge, "<": operator.lt, ">": operator.gt, "=": operator.eq}


def score_answer(case: Case, answer: str, db_path: Path) -> tuple[bool, str | None]:
    """답변을 케이스의 기대값에 비추어 채점한다.

    거절 케이스는 거절 표현이 있는지, 집계 케이스는 기대 SQL을 지금 실행해 나온 값이 답변에 있는지 본다.

    Returns:
        통과 여부와, 실패했다면 그 이유.
    """
    if case.must_refuse:
        if any(phrase in answer for phrase in REFUSAL_PHRASES):
            return True, None
        return False, "거절해야 할 질문에 거절하지 않았다"
    if case.expected_sql:
        result = run_sql(db_path, case.expected_sql)
        if "error" in result:
            return False, f"기대 SQL이 실패했다: {result['error']}"
        cells = [cell for row in result["rows"] for cell in row]
        if any(cell is None for cell in cells):
            return False, "기대 SQL 결과에 NULL이 있다. 검사할 값이 없으므로 케이스를 고쳐야 한다"
        missing = [cell for cell in cells if not _contains(answer, cell)]
        if missing:
            return False, f"답변에 없는 기대값: {missing}"
        return True, None
    raise ValueError(f"케이스 '{case.id}'에 기대 SQL도 거절 여부도 없습니다. 루브릭 채점은 심판이 맡습니다.")


def score_trajectory(case: Case, trajectory: list[dict]) -> tuple[bool, str | None]:
    """궤적을 케이스의 기대 부분 순서와 금지 패턴에 비추어 채점한다.

    기대한 호출 사이에 다른 호출이 끼는 것은 허용한다. 검색어를 바꿔 여러 번 검색하는 것은 의도된 동작이다.

    Returns:
        통과 여부와, 실패했다면 그 이유.
    """
    for pattern in case.forbidden:
        if any(_matches(call, pattern) for call in trajectory):
            return False, f"금지 패턴이 나타났다: {pattern}"
    position = 0
    for expected in case.expected_trajectory:
        while position < len(trajectory) and not _matches(trajectory[position], expected):
            position += 1
        if position == len(trajectory):
            return False, f"기대한 호출이 없거나 순서가 어긋났다: {expected}"
        position += 1
    return True, None


def _matches(call: dict, pattern: dict) -> bool:
    if call["tool"] != pattern["tool"]:
        return False
    args = call["args"]
    if any(args.get(name) is not None for name in pattern.get("args_missing", [])):
        return False
    return all(_matches_arg(args.get(name), condition) for name, condition in pattern.get("args_match", {}).items())


def _matches_arg(value, condition: str) -> bool:
    """인자 하나가 조건을 만족하는지 본다. 조건은 비교 연산자로 시작하는 수 비교이거나, 그 밖에는 정규식이다."""
    if value is None:
        return False
    for symbol, compare in COMPARISONS.items():
        if condition.startswith(symbol):
            try:
                return compare(float(value), float(condition[len(symbol):]))
            except (TypeError, ValueError):
                return False
    return re.search(condition, str(value), re.IGNORECASE) is not None


def _contains(answer: str, value) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _contains_number(answer, value)
    return str(value).lower() in answer.lower()


def _contains_number(answer: str, value: float) -> bool:
    """수가 답변에 있는지 본다. 자릿수 구분 쉼표는 지운다.

    답변의 자릿수는 에이전트가 정하는 것이므로 표기를 그대로 맞추라고 요구하지 않는다. 대신 기대값과
    답변 속 수가 각자의 자릿수로 가리키는 범위가 겹치면 같은 수로 본다. 4.85를 4.853이나 4.9로 쓴 것은
    통과하고, 4.7로 쓴 것은 통과하지 못한다.
    """
    text = re.sub(r"(?<=\d),(?=\d)", "", answer)
    tolerance = _half_step(f"{value:f}".rstrip("0"))
    return any(
        abs(float(found) - value) <= tolerance + _half_step(found)
        for found in re.findall(r"\d+(?:\.\d+)?", text)
    )


def _half_step(number: str) -> float:
    """표기된 자릿수가 함의하는 반올림 오차의 절반. `4.85`는 0.005, `414`는 0.5다."""
    _, _, decimals = number.partition(".")
    return 0.5 * 10 ** -len(decimals)
