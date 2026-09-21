import argparse
import hashlib
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

from review_agent.cli import SYSTEM_PROMPT, build_agent
from review_agent.eval.cases import load_cases
from review_agent.eval.compare import compare
from review_agent.eval.harness import evaluate
from review_agent.eval.instrument import TimingEmbeddings, agent_executor
from review_agent.eval.judge import openai_judge
from review_agent.eval.report import latest_run, run_meta, save_report, save_run
from review_agent.search_tool import EMBEDDING_MODEL, open_store


def main() -> None:
    parser = argparse.ArgumentParser(description="케이스를 실행해 답변과 궤적을 채점하고 소요 시간과 토큰을 기록한다.")
    parser.add_argument("--cases", type=Path, default=Path("evals/cases.toml"), help="케이스 파일 경로")
    parser.add_argument("--db", type=Path, default=Path("data/reviews.db"), help="SQLite 파일 경로")
    parser.add_argument("--vectors", type=Path, default=Path("data/vectors.json"), help="리뷰 벡터 저장소 파일 경로")
    parser.add_argument("--runs", type=int, default=3, help="케이스 하나를 실행할 횟수")
    parser.add_argument("--runs-dir", type=Path, default=Path("evals/runs"), help="커밋하는 결과를 둘 디렉터리")
    parser.add_argument("--details-dir", type=Path, default=Path("evals/details"), help="답변 전문을 둘 디렉터리")
    parser.add_argument("--reports-dir", type=Path, default=Path("evals/reports"), help="비교 리포트를 둘 디렉터리")
    args = parser.parse_args()
    for path in (args.cases, args.db, args.vectors):
        if not path.exists():
            raise SystemExit(f"없는 파일입니다: {path}")

    load_dotenv()
    model = os.environ["OPENAI_MODEL"]
    judge_model = os.environ.get("EVAL_JUDGE_MODEL")
    embeddings = TimingEmbeddings(OpenAIEmbeddings(model=EMBEDDING_MODEL))

    start = time.perf_counter()
    store = open_store(args.vectors, embeddings)
    store_open_ms = (time.perf_counter() - start) * 1000
    agent = build_agent(args.db, args.vectors, model, store)
    print(f"벡터 저장소 로드: {store_open_ms / 1000:.1f}s (세션당 1회, 질문당 시간과 섞지 않는다)")

    cases = load_cases(args.cases, args.db)
    if judge_model is None and any(case.rubric for case in cases):
        raise SystemExit("루브릭이 있는 케이스가 있습니다. .env에 EVAL_JUDGE_MODEL을 설정하세요.")
    print(f"케이스 {len(cases)}개 × {args.runs}회, 모델 {model}, 심판 {judge_model}")
    judge = openai_judge(judge_model) if judge_model else None
    result = evaluate(cases, args.db, agent_executor(agent, embeddings), judge, args.runs)

    meta = run_meta(
        args.db, model, judge_model,
        hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:8], store_open_ms,
    )
    baseline = latest_run(args.runs_dir, meta["scale"]["label"], meta["run_id"]) if args.runs_dir.exists() else None
    run_path, details_path = save_run(result, args.runs_dir, args.details_dir, meta)
    comparison = compare({**meta, **result}, baseline)
    name = f"{meta['run_id']}-vs-{baseline['run_id']}" if baseline else meta["run_id"]
    report_path = save_report(comparison.markdown, args.reports_dir, name)

    _print_summary(result, meta)
    print(f"\n판정     {comparison.verdict}" + (f" — {', '.join(comparison.regressed)}" if comparison.regressed else ""))
    print(f"저장     {run_path}  (상세: {details_path})")
    print(f"리포트   {report_path}")


def _print_summary(result: dict, meta: dict) -> None:
    summary = result["summary"]
    for case in result["cases"]:
        reasons = {attempt["fail_reason"] for attempt in case["runs"] if attempt["fail_reason"]}
        print(f"  {case['id']:<28} {case['passed']}/{case['total']}  {'· '.join(reasons)}")
    print(f"\n통과     {summary['passed']}/{summary['total']} 회차")
    print("유형별   " + " · ".join(f"{t} {c['passed']}/{c['total']}" for t, c in summary["by_type"].items()))
    print(f"질문당   중앙값 {summary['question_seconds']['median']:.1f}s · 최대 {summary['question_seconds']['max']:.1f}s")
    print("모듈별   " + " · ".join(f"{label} {ms / 1000:.1f}s" for label, ms in summary["module_ms"].items()))
    print(f"토큰     입력 {summary['tokens'].get('input', 0)} · 출력 {summary['tokens'].get('output', 0)}"
          f" · 질문당 중앙값 {summary['question_tokens']['median']:.0f} · 임베딩 호출 {summary['embedding_calls']}회")
    agreement = summary["judge_agreement"]
    if summary["judge_tokens"]:
        print(f"심판     입력 {summary['judge_tokens'].get('input', 0)} · 출력 {summary['judge_tokens'].get('output', 0)}"
              + (f" · 사람 라벨과 일치 {agreement['matched']}/{agreement['of']}" if agreement["of"] else " · 사람 라벨 없음"))
    scale = meta["scale"]
    print(f"규모     {scale['label']} (상품 {scale['products']}개 · 리뷰 {scale['reviews']}건)"
          f" · 벡터 저장소 로드 {meta['vector_store_open_ms'] / 1000:.1f}s")
    metrics = meta["load_metrics"]
    if metrics is None:
        print("적재      측정값 없음 — 이 적재 데이터는 측정값을 남기기 전에 만들어졌다")
    else:
        print(f"적재     {metrics['load_seconds'] / 60:.1f}분 (임베딩 {metrics['embedding_seconds'] / 60:.1f}분)"
              f" · SQLite {metrics['db_bytes'] / 1e6:.0f}MB · 벡터 {metrics['vectors_bytes'] / 1e6:.0f}MB")


def _commit() -> str:
    """평가를 돌린 저장소 커밋. 결과를 나중에 해석할 때 조건을 알기 위해 남긴다."""
    result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True)
    return result.stdout.strip()
