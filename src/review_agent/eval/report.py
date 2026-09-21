import json
import subprocess
from pathlib import Path
from uuid import uuid4

from review_agent.loader import DEFAULT_SCOPE, load_metrics, scale_label
from review_agent.sql_tool import run_sql


def run_meta(
    db_path: Path, model: str, judge_model: str | None, prompt_hash: str, vector_store_open_ms: float
) -> dict:
    """평가 결과에 함께 남길 실행 조건을 모은다.

    규모 라벨은 적재 데이터에서 직접 센다. 적재 측정값은 적재가 남긴 파일에서 읽고, 없으면 비운다.
    규모가 다른 결과끼리 품질을 비교하지 않으려면 이 라벨이 결과 안에 있어야 한다.

    Returns:
        규모, 적재 측정값, 모델과 프롬프트·커밋 해시를 담은 dict.
    """
    scale = _scale(db_path)
    return {
        "run_id": f"{scale['label']}-{_commit()}-{uuid4().hex[:6]}",
        "scale": scale,
        "load_metrics": load_metrics(db_path),
        "model": model,
        "judge_model": judge_model,
        "prompt_hash": prompt_hash,
        "commit": _commit(),
        "vector_store_open_ms": vector_store_open_ms,
    }


def _scale(db_path: Path) -> dict:
    """적재 데이터의 규모. 적재 범위와 상위 N을 모두 담은 라벨이고, 같은 라벨끼리만 품질을 비교한다."""
    counts = run_sql(db_path, "SELECT (SELECT COUNT(*) FROM products), (SELECT COUNT(*) FROM reviews)")["rows"][0]
    metrics = load_metrics(db_path) or {}
    scope = metrics.get("scope", DEFAULT_SCOPE)
    # 측정값이 없는 옛 적재 데이터는 상위 N도 모른다. 그때는 적재된 상품 수가 곧 상위 N이던 옛 라벨을 따른다.
    top_n = metrics.get("top_n", counts[0])
    return {
        "label": scale_label(scope, top_n), "scope": scope, "top_n": top_n,
        "products": counts[0], "reviews": counts[1],
    }


def label_of(run: dict) -> str:
    """평가 결과의 규모 라벨.

    적재 범위 필드가 없는 옛 결과는 기본 적재 범위로 읽는다. 옛 라벨은 `n<상위 N>`이었으므로 그 앞에 적재 범위만
    붙이면 지금 라벨과 같아져, 얼굴 보습·상위 20의 기준선이 새 라벨 형식에서도 계속 기준선으로 잡힌다.
    """
    scale = run["scale"]
    if "scope" in scale:
        return scale["label"]
    return scale_label(DEFAULT_SCOPE, int(scale["label"].removeprefix("n")))


def _commit() -> str:
    """평가를 돌린 저장소 커밋. 결과를 나중에 해석할 때 조건을 알기 위해 남긴다."""
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def save_run(result: dict, runs_dir: Path, details_dir: Path, meta: dict) -> tuple[Path, Path]:
    """평가 결과를 저장소에 커밋하는 파일과 로컬에만 남기는 상세 파일로 나눠 쓴다.

    커밋본에는 점수·궤적·소요 시간·토큰만 넣는다. 답변 전문에는 리뷰 원문 인용이 섞이는데,
    그 텍스트는 재배포하지 않기로 했으므로 저장소에 들어가지 않는다.

    Returns:
        (커밋본 경로, 상세본 경로).
    """
    run_id = meta["run_id"]
    committed = {
        **meta,
        "cases": [
            {**case, "runs": [{k: v for k, v in attempt.items() if k != "answer"} for attempt in case["runs"]]}
            for case in result["cases"]
        ],
        "summary": result["summary"],
    }
    details = {
        "run_id": run_id,
        "cases": [
            {"id": case["id"], "runs": [{"answer": attempt["answer"]} for attempt in case["runs"]]}
            for case in result["cases"]
        ],
    }
    return _write(runs_dir / f"{run_id}.json", committed), _write(details_dir / f"{run_id}.json", details)


def _write(path: Path, document: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def latest_run(runs_dir: Path, label: str, exclude: str) -> dict | None:
    """같은 규모의 가장 최근 평가 결과. 회귀를 판정할 기준선이다.

    규모가 다른 결과는 품질을 비교할 수 없으므로 고르지 않는다.

    Returns:
        기준선으로 쓸 결과. 같은 규모의 이전 결과가 없으면 None.
    """
    candidates = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if path.stem != exclude
    ]
    return next((run for run in candidates if label_of(run) == label), None)


def save_report(markdown: str, reports_dir: Path, name: str) -> Path:
    """비교 리포트를 저장소에 커밋되는 마크다운으로 쓴다."""
    return _write_text(reports_dir / f"{name}.md", markdown)


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
