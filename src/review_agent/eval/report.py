import json
from pathlib import Path


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
