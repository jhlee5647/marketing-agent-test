import argparse
import gzip
import json
import re
import sqlite3
import time
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

import numpy as np
from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from review_agent.search_tool import EMBEDDING_MODEL, document_prefix

UCSD_RAW = "https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/raw"
META_URL = f"{UCSD_RAW}/meta_categories/meta_Beauty_and_Personal_Care.jsonl.gz"
REVIEW_URL = f"{UCSD_RAW}/review_categories/Beauty_and_Personal_Care.jsonl.gz"

# 적재 범위의 기본값(얼굴 보습 제품). 실행 인자로 상위 경로까지 넓힐 수 있다.
DEFAULT_SCOPE = ["Skin Care", "Face", "Creams & Moisturizers"]
# 임베딩 한 번에 넘기는 리뷰 수. langchain_openai가 안에서 쓰는 묶음 크기와 같아 API 왕복 수는 달라지지 않는다.
EMBEDDING_BATCH = 1000
# 2023년 리뷰만 적재한다. 원본이 2023-09에서 끝나므로 상한은 두지 않는다. 적재 범위와 달리 축이 아니라 상수다.
REVIEWS_SINCE_MS = int(datetime(2023, 1, 1, tzinfo=UTC).timestamp() * 1000)

SCHEMA = """
CREATE TABLE products (
    parent_asin TEXT PRIMARY KEY,
    title TEXT,
    average_rating REAL,
    rating_number INTEGER,
    price REAL,
    store TEXT,
    categories TEXT,
    features TEXT,
    details TEXT
);
CREATE TABLE reviews (
    review_id INTEGER PRIMARY KEY,
    parent_asin TEXT NOT NULL REFERENCES products(parent_asin),
    asin TEXT,
    user_id TEXT,
    rating REAL,
    title TEXT,
    text TEXT,
    reviewed_at TEXT,
    helpful_vote INTEGER,
    verified_purchase INTEGER
);
"""


def load(
    meta_lines: Iterable[str],
    review_lines: Iterable[str],
    db_path: Path,
    vectors_path: Path,
    embeddings: Embeddings,
    top_n: int | None = 20,
    scope: list[str] = DEFAULT_SCOPE,
) -> tuple[int, int]:
    """메타·리뷰 줄 스트림에서 적재 범위 안 2023년 리뷰 수 상위 `top_n`개 상품과 그 2023년 리뷰 전부를 SQLite와 리뷰 벡터 저장소 파일에 적재한다.

    적재에 걸린 시간과 만들어진 파일 크기는 적재 데이터 옆 `<db 이름>.metrics.json`에 남긴다. 규모를 키웠을 때
    무엇이 몇 배로 늘어나는지 평가 결과와 함께 보기 위해서다. 적재 범위도 같은 파일에 남긴다.

    Args:
        top_n: 적재할 상위 상품 개수. None이면 적재 범위 안에서 2023년 리뷰가 있는 상품 전량.
        scope: 적재 범위. 원본 카테고리 경로에서 루트(`Beauty & Personal Care`) 다음부터의 접두사다.

    Returns:
        적재된 (상품 수, 리뷰 수).
    """
    started = time.perf_counter()
    metrics_path = db_path.with_suffix(".metrics.json")
    db_path.unlink(missing_ok=True)
    vectors_path.unlink(missing_ok=True)
    metrics_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)

    for line in meta_lines:
        m = json.loads(line)
        # 0번 칸은 원본 파일의 루트(`Beauty & Personal Care`)라 적재 범위에서 뺀다.
        if (m["categories"] or [])[1 : 1 + len(scope)] != scope:
            continue
        conn.execute(
            "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                m["parent_asin"], m["title"], m["average_rating"], m["rating_number"], m["price"], m["store"],
                json.dumps(m["categories"]), json.dumps(m["features"]), json.dumps(m["details"]),
            ),
        )
    product_ids = {row[0] for row in conn.execute("SELECT parent_asin FROM products")}

    for line in review_lines:
        r = json.loads(line)
        if r["parent_asin"] not in product_ids or r["timestamp"] < REVIEWS_SINCE_MS:
            continue
        conn.execute(
            "INSERT INTO reviews (parent_asin, asin, user_id, rating, title, text, reviewed_at, helpful_vote,"
            " verified_purchase) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                r["parent_asin"], r["asin"], r["user_id"], r["rating"], r["title"], r["text"],
                datetime.fromtimestamp(r["timestamp"] / 1000, UTC).isoformat(timespec="seconds"),
                r["helpful_vote"], r["verified_purchase"],
            ),
        )

    # 후보 리뷰를 모두 쓴 뒤 상위 N개 밖을 지운다. 리뷰를 메모리에 쌓지 않기 위해서다.
    # 전량(`top_n`이 None)이면 LIMIT -1로 제한을 풀어, 2023년 리뷰가 없는 상품만 빠진다.
    conn.execute(
        "CREATE TEMP TABLE top_products AS SELECT parent_asin FROM reviews"
        " GROUP BY parent_asin ORDER BY COUNT(*) DESC, parent_asin LIMIT ?",
        (-1 if top_n is None else top_n,),
    )
    conn.execute("DELETE FROM reviews WHERE parent_asin NOT IN (SELECT parent_asin FROM top_products)")
    conn.execute("DELETE FROM products WHERE parent_asin NOT IN (SELECT parent_asin FROM top_products)")

    conn.commit()
    # 상위 N개 밖을 지운 자리는 VACUUM 전까지 파일에 그대로 남는다. 적재 데이터 크기가 실제 내용을
    # 나타내야 규모별 비교가 의미를 갖는다.
    conn.execute("VACUUM")

    reviews = conn.execute(
        "SELECT review_id, parent_asin, rating, title, text, verified_purchase FROM reviews"
    ).fetchall()
    documents = [document_prefix(title) + text for _, _, _, title, text, _ in reviews]
    embedding_started = time.perf_counter()
    # 한 번에 다 임베딩하면 리뷰 수 × 1,536개의 파이썬 실수가 동시에 살아 있다(리뷰 27만 건에 약 13GB).
    # 묶음마다 float32로 바꿔 쌓으면 적재가 들고 있는 것이 결국 저장할 행렬 하나가 된다.
    batches = [
        np.asarray(embeddings.embed_documents(documents[at : at + EMBEDDING_BATCH]), dtype=np.float32)
        for at in range(0, len(documents), EMBEDDING_BATCH)
    ]
    embedding_seconds = time.perf_counter() - embedding_started
    vectors = np.vstack(batches) if batches else np.zeros((0, 0), dtype=np.float32)
    # 검색은 코사인 유사도다. 여기서 한 번 정규화해 두면 검색 한 번이 행렬 곱 하나로 끝난다.
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    with vectors_path.open("wb") as file:
        # 경로를 그대로 쓴다. np.savez에 경로를 넘기면 확장자가 .npz가 아닐 때 멋대로 붙인다.
        np.savez(
            file,
            ids=np.array([review_id for review_id, *_ in reviews], dtype=np.int64),
            vectors=vectors,
            parent_asins=np.array([parent_asin for _, parent_asin, *_ in reviews]),
            ratings=np.array([rating for _, _, rating, *_ in reviews], dtype=np.float32),
            verified=np.array([bool(verified) for *_, verified in reviews], dtype=bool),
        )

    counts = conn.execute("SELECT (SELECT COUNT(*) FROM products), (SELECT COUNT(*) FROM reviews)").fetchone()
    conn.close()
    metrics_path.write_text(
        json.dumps(
            {
                "products": counts[0], "reviews": counts[1], "top_n": top_n, "scope": scope,
                "load_seconds": time.perf_counter() - started, "embedding_seconds": embedding_seconds,
                "db_bytes": db_path.stat().st_size, "vectors_bytes": vectors_path.stat().st_size,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    return counts


def scale_label(scope: list[str], top_n: int | None) -> str:
    """규모 라벨. 적재 범위와 상위 N을 모두 담아, 두 인자가 다른 적재 데이터가 같은 규모로 읽히지 않게 한다.

    규모별 적재 데이터와 축약 측정 파일의 이름으로도 쓴다(`data/scale/<규모 라벨>/`).
    """
    path = "-".join(re.sub(r"[^a-z0-9]+", "-", segment.lower()).strip("-") for segment in scope)
    return f"{path}-{'all' if top_n is None else f'n{top_n}'}"


def load_metrics(db_path: Path) -> dict | None:
    """적재가 남긴 측정값. 측정값을 남기기 전에 만들어진 적재 데이터면 None."""
    path = db_path.with_suffix(".metrics.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def stream_lines(url: str) -> Iterator[str]:
    """`.jsonl.gz`를 디스크에 저장하지 않고 HTTP로 받으며 압축을 풀어 한 줄씩 넘긴다.

    첫 줄을 읽을 때 연결을 연다. 메타를 훑는 동안 리뷰 연결이 놀다가 끊기지 않게 하기 위해서다.
    """
    with urlopen(url) as response, gzip.open(response, "rt", encoding="utf-8") as lines:
        yield from lines


def _scope_arg(text: str) -> list[str]:
    return [segment.strip() for segment in text.split(">")]


def _top_n_arg(text: str) -> int | None:
    return None if text == "all" else int(text)


def main() -> None:
    parser = argparse.ArgumentParser(description="UCSD Beauty_and_Personal_Care에서 적재 범위 안의 상품을 적재한다.")
    parser.add_argument("--db", type=Path, default=Path("data/reviews.db"), help="SQLite 파일 경로")
    parser.add_argument("--vectors", type=Path, default=Path("data/vectors.npz"), help="리뷰 벡터 저장소 파일 경로")
    parser.add_argument("--top-n", type=_top_n_arg, default=20, help="적재할 상위 상품 개수. all이면 적재 범위 안 전량")
    parser.add_argument(
        "--scope", type=_scope_arg, default=DEFAULT_SCOPE,
        help="적재 범위. 루트(Beauty & Personal Care)를 뺀 카테고리 경로를 >로 잇는다(예: 'Skin Care > Face')",
    )
    args = parser.parse_args()

    load_dotenv()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    args.vectors.parent.mkdir(parents=True, exist_ok=True)
    products, reviews = load(
        stream_lines(META_URL), stream_lines(REVIEW_URL), args.db, args.vectors,
        OpenAIEmbeddings(model=EMBEDDING_MODEL), args.top_n, args.scope,
    )
    print(f"완료: 상품 {products}개, 리뷰 {reviews}건 · 규모 {scale_label(args.scope, args.top_n)}")
