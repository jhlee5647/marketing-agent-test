import argparse
import hashlib
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

from review_agent.cli import SYSTEM_PROMPT, build_agent
from review_agent.eval.cases import load_cases
from review_agent.eval.harness import evaluate
from review_agent.eval.instrument import TimingEmbeddings, agent_executor
from review_agent.eval.report import save_run
from review_agent.search_tool import EMBEDDING_MODEL


def main() -> None:
    parser = argparse.ArgumentParser(description="케이스를 실행해 답변과 궤적을 채점하고 소요 시간과 토큰을 기록한다.")
    parser.add_argument("--cases", type=Path, default=Path("evals/cases.toml"), help="케이스 파일 경로")
    parser.add_argument("--db", type=Path, default=Path("data/reviews.db"), help="SQLite 파일 경로")
    parser.add_argument("--vectors", type=Path, default=Path("data/vectors.json"), help="리뷰 벡터 저장소 파일 경로")
    parser.add_argument("--runs", type=int, default=3, help="케이스 하나를 실행할 횟수")
    parser.add_argument("--runs-dir", type=Path, default=Path("evals/runs"), help="커밋하는 결과를 둘 디렉터리")
    parser.add_argument("--details-dir", type=Path, default=Path("evals/details"), help="답변 전문을 둘 디렉터리")
    args = parser.parse_args()
    for path in (args.cases, args.db, args.vectors):
        if not path.exists():
            raise SystemExit(f"없는 파일입니다: {path}")

    load_dotenv()
    model = os.environ["OPENAI_MODEL"]
    embeddings = TimingEmbeddings(OpenAIEmbeddings(model=EMBEDDING_MODEL))

    start = time.perf_counter()
    agent = build_agent(args.db, args.vectors, model, embeddings)
    setup_ms = (time.perf_counter() - start) * 1000
    print(f"세션 준비(대부분 벡터 저장소 로드): {setup_ms / 1000:.1f}s")

    cases = load_cases(args.cases, args.db)
    print(f"케이스 {len(cases)}개 × {args.runs}회, 모델 {model}")
    result = evaluate(cases, args.db, agent_executor(agent, embeddings), args.runs)

    meta = {
        "run_id": f"{_commit()}-{uuid4().hex[:6]}",
        "model": model,
        "commit": _commit(),
        "prompt_hash": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:8],
        "session_setup_ms": setup_ms,
    }
    run_path, details_path = save_run(result, args.runs_dir, args.details_dir, meta)
    _print_summary(result)
    print(f"\n저장: {run_path}  (상세: {details_path})")


def _print_summary(result: dict) -> None:
    summary = result["summary"]
    for case in result["cases"]:
        reasons = {attempt["fail_reason"] for attempt in case["runs"] if attempt["fail_reason"]}
        print(f"  {case['id']:<28} {case['passed']}/{case['of']}  {'· '.join(reasons)}")
    print(f"\n통과     {summary['passed']}/{summary['of']} 회차")
    print("유형별   " + " · ".join(f"{t} {c['passed']}/{c['of']}" for t, c in summary["by_type"].items()))
    print(f"질문당   중앙값 {summary['question_seconds']['median']:.1f}s · 최대 {summary['question_seconds']['max']:.1f}s")
    print("모듈별   " + " · ".join(f"{label} {ms / 1000:.1f}s" for label, ms in summary["module_ms"].items()))
    print(f"토큰     입력 {summary['tokens'].get('input', 0)} · 출력 {summary['tokens'].get('output', 0)}"
          f" · 임베딩 호출 {summary['embedding_calls']}회")


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
