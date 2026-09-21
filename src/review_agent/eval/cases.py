import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from review_agent.sql_tool import run_sql

# `{리뷰 수 1위 상품}` 또는 `{리뷰 수 1위 상품:parent_asin}`
PLACEHOLDER = re.compile(r"\{([^{}:]+)(?::([^{}]+))?\}")


@dataclass
class Case:
    """평가의 단위. 질문 하나 또는 이어지는 질문 여러 개와, 그에 대한 기대값이다."""

    id: str
    type: str
    turns: list[str]
    expected_sql: str | None = None
    must_refuse: bool = False
    rubric: str | None = None
    human_label: str | None = None
    expected_trajectory: list[dict] = field(default_factory=list)
    forbidden: list[dict] = field(default_factory=list)
    resolved: dict[str, str] = field(default_factory=dict)


def load_cases(path: Path, db_path: Path | None = None) -> list[Case]:
    """케이스 파일을 읽고, 적재 데이터가 주어지면 상품 자리표시자를 실제 값으로 렌더링한다.

    자리표시자는 케이스 파일의 `[placeholders]` 절에 SQL로 정의한다. `{이름}`은 그 SQL의 첫 컬럼,
    `{이름:컬럼}`은 지정한 컬럼의 값이 된다.

    Returns:
        파일에 적힌 순서대로의 케이스.
    """
    doc = tomllib.loads(path.read_text(encoding="utf-8"))
    cases = [
        Case(
            id=c["id"], type=c["type"], turns=list(c["turns"]), expected_sql=c.get("expected_sql"),
            must_refuse=c.get("must_refuse", False), rubric=c.get("rubric"), human_label=c.get("human_label"),
            expected_trajectory=c.get("expected_trajectory", []), forbidden=c.get("forbidden", []),
        )
        for c in doc["cases"]
    ]
    if db_path is not None:
        values = _placeholder_values(doc.get("placeholders", {}), cases, db_path)
        for case in cases:
            case.resolved = {key: values[key] for key in _keys_in(case)}
            case.turns = [_render(turn, values) for turn in case.turns]
    return cases


def _keys_in(case: Case) -> list[str]:
    return [m.group(0)[1:-1] for turn in case.turns for m in PLACEHOLDER.finditer(turn)]


def _placeholder_values(placeholders: dict, cases: list[Case], db_path: Path) -> dict[str, str]:
    """케이스에 쓰인 자리표시자를 적재 데이터에서 조회해 `이름` 또는 `이름:컬럼` → 값으로 돌려준다."""
    values: dict[str, str] = {}
    for key in {key for case in cases for key in _keys_in(case)}:
        name, _, column = key.partition(":")
        result = run_sql(db_path, placeholders[name]["sql"])
        if "error" in result or not result["rows"]:
            raise ValueError(f"자리표시자 '{name}'의 SQL이 값을 내지 못했습니다: {result}")
        row = result["rows"][0]
        values[key] = str(row[result["columns"].index(column)] if column else row[0])
    return values


def _render(turn: str, values: dict[str, str]) -> str:
    return PLACEHOLDER.sub(lambda m: values.get(m.group(0)[1:-1], m.group(0)), turn)
