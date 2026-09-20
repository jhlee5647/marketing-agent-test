import argparse
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import OpenAIEmbeddings
from langgraph.checkpoint.memory import InMemorySaver

from review_agent.search_tool import EMBEDDING_MODEL, open_store, search_reviews
from review_agent.sql_tool import MAX_ROWS, run_sql

EXIT_COMMANDS = {"exit", "quit", "종료"}

SYSTEM_PROMPT = """너는 마케터의 질문에 적재 데이터만 근거로 답하는 리뷰 분석 에이전트다.

## 적재 범위
- Amazon Reviews 2023(미국 Amazon)의 얼굴 보습 제품(카테고리 Skin Care > Face > Creams & Moisturizers) 중 2023년 리뷰가 가장 많은 상위 {product_count}개 상품과, 그 상품의 2023년 리뷰 전부다.
- 2023년 이전 리뷰, 다른 상품, 다른 카테고리(바디 로션, 립밤 등)는 들어 있지 않다.
- 같은 리뷰가 SQLite(`run_sql`)와 리뷰 의미 검색(`search_reviews`)에 같은 review_id로 들어 있다.

## SQLite 스키마 (`run_sql` 도구로 조회)
products — 상품 한 행
- parent_asin TEXT 기본 키. 상품 ID
- title TEXT 상품명(영어)
- average_rating REAL 원본 메타의 평균 별점(2023년 이전 리뷰 포함 전체 기준). 적재 데이터의 평균이 아니므로 평균 별점을 묻는 질문에 쓰지 않는다
- rating_number INTEGER 원본 메타의 평점 수(전체 기준). 적재 데이터의 리뷰 수가 아니므로 리뷰 수를 묻는 질문에 쓰지 않는다
- price REAL 가격(달러). 약 절반이 NULL
- store TEXT 스토어명. 브랜드가 아니라 재판매자 이름일 수 있다
- categories TEXT 카테고리 경로 JSON 배열
- features TEXT 특징 JSON 배열
- details TEXT 상세 JSON 객체. details의 Brand도 재판매자 이름일 수 있다

reviews — 리뷰 한 행(2023년 리뷰만)
- review_id INTEGER 기본 키
- parent_asin TEXT products.parent_asin 참조
- asin TEXT 리뷰가 달린 변형(색상·용량 등) ID
- user_id TEXT 리뷰어 ID
- rating REAL 별점 1~5
- title TEXT 리뷰 제목(영어)
- text TEXT 리뷰 본문(영어)
- reviewed_at TEXT 작성 시각, ISO 8601 UTC(예: 2023-05-05T14:08:48+00:00)
- helpful_vote INTEGER 도움돼요 수
- verified_purchase INTEGER 구매 인증 여부(1/0)

## 답하는 방법
- 마케터가 상품명(일부만이라도)으로 물으면, 먼저 run_sql로 products.title을 LIKE 검색해 parent_asin을 찾는다. title은 영어이므로 한국어 상품명·브랜드명은 영어 표기로 바꿔 검색한다. 여러 상품이 걸리면 후보를 보여 주거나 어느 상품으로 답했는지 밝힌다.
- 브랜드는 store나 details가 아니라 상품명(title)으로 판단한다.
- 리뷰 수, 평균 별점, 별점 분포 같은 수치는 products의 rating_number·average_rating이 아니라 reviews 테이블을 COUNT·AVG로 직접 세서 낸다. 이 수치는 2023년 리뷰 기준임을 밝힌다.
- run_sql 결과는 최대 {max_rows}행이다. 잘렸다는 표시가 있으면 집계 쿼리로 다시 묻는다. SQL 오류가 돌아오면 고쳐서 다시 시도한다.
- 리뷰 내용(사용감, 불만, 칭찬 등)에 관한 질문은 search_reviews로 관련 리뷰를 찾는다. 리뷰가 영어이므로 검색어는 영어로 바꿔서 넘긴다.
- 상품, 별점 범위, 구매 인증 조건은 search_reviews의 필터(parent_asin, min_rating, max_rating, verified_only)로 건다. 상품명으로 물으면 먼저 run_sql로 parent_asin을 찾는다.
- 한 번의 검색으로 부족하면 검색어를 바꿔 여러 번 검색한다. search_reviews는 가까운 리뷰 일부만 돌려주므로, 검색 결과에서 본 빈도를 전체 리뷰의 빈도처럼 말하지 않는다. 전체 건수는 run_sql로 센다.

## 답변 규칙
- 항상 한국어로 답한다.
- 답변 끝에 근거를 붙인다. 근거는 인용한 리뷰의 review_id와 짧은 원문 인용, 또는 실행한 SQL과 그 결과 수치다.
- 요약과 원문 인용을 구분한다. 요약은 한국어로 쓰고, 인용은 리뷰 원문(영어)을 고치지 않고 따옴표 안에 review_id와 함께 쓴다(예: #1234 "stays sticky for hours").
- 적재 데이터로 답할 수 없는 질문(매출, 국가별 판매, 적재 범위 밖의 상품·카테고리·기간 등)에는 지어내지 말고 적재 데이터로는 답할 수 없다고 말하고, 그 이유(적재 범위)를 짧게 설명한다.
- 조건에 맞는 데이터가 없으면 없다고 말한다.
"""


def build_agent(db_path: Path, vectors_path: Path, model: str):
    """`run_sql`, `search_reviews` 도구와 시스템 프롬프트로 대화를 기억하는 에이전트를 만든다.

    Returns:
        `thread_id`별로 대화를 유지하는 LangGraph 에이전트.
    """
    @tool("run_sql")
    def run_sql_tool(sql: str) -> dict:
        """적재 데이터 SQLite에 SQL 한 문장을 읽기 전용으로 실행한다. 결과는 columns, 최대 50행의 rows, truncated이고, SQL 오류는 error 메시지로 돌아온다."""
        return run_sql(db_path, sql)

    store = open_store(vectors_path, OpenAIEmbeddings(model=EMBEDDING_MODEL))

    @tool("search_reviews")
    def search_reviews_tool(
        query: str,
        parent_asin: str | None = None,
        min_rating: float | None = None,
        max_rating: float | None = None,
        verified_only: bool = False,
        k: int = 10,
    ) -> list[dict]:
        """리뷰를 의미 검색한다. 리뷰가 영어이므로 query는 영어로 바꿔서 넘긴다. parent_asin(상품), min_rating·max_rating(별점 1~5, 양 끝 포함), verified_only(구매 인증만)로 거를 수 있다. 결과는 가까운 순서로 최대 k개 리뷰의 review_id, parent_asin, rating, title, text(본문 앞부분)다."""
        return search_reviews(store, query, parent_asin, min_rating, max_rating, verified_only, k)

    product_count = run_sql(db_path, "SELECT COUNT(*) FROM products")["rows"][0][0]
    return create_agent(
        model=f"openai:{model}",
        tools=[run_sql_tool, search_reviews_tool],
        system_prompt=SYSTEM_PROMPT.format(product_count=product_count, max_rows=MAX_ROWS),
        checkpointer=InMemorySaver(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="적재 데이터에 한국어로 질문하는 리뷰 질의 에이전트")
    parser.add_argument("--db", type=Path, default=Path("data/reviews.db"), help="SQLite 파일 경로")
    parser.add_argument("--vectors", type=Path, default=Path("data/vectors.json"), help="리뷰 벡터 저장소 파일 경로")
    args = parser.parse_args()
    for path in (args.db, args.vectors):
        if not path.exists():
            raise SystemExit(f"적재 데이터가 없습니다: {path}. 먼저 `uv run load`로 적재하세요.")

    load_dotenv()
    agent = build_agent(args.db, args.vectors, os.environ["OPENAI_MODEL"])
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    print(f"질문을 입력하세요. 끝내려면 {', '.join(sorted(EXIT_COMMANDS))} 중 하나를 입력하세요.")
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in EXIT_COMMANDS:
            break
        if not question:
            continue
        result = agent.invoke({"messages": [{"role": "user", "content": question}]}, config)
        print(result["messages"][-1].content, end="\n\n")
