import argparse
import gzip
import json
import sqlite3
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import OpenAIEmbeddings

from review_agent.search_tool import EMBEDDING_MODEL, document_prefix

UCSD_RAW = "https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/raw"
META_URL = f"{UCSD_RAW}/meta_categories/meta_Beauty_and_Personal_Care.jsonl.gz"
REVIEW_URL = f"{UCSD_RAW}/review_categories/Beauty_and_Personal_Care.jsonl.gz"

FACE_MOISTURIZER_PATH = ["Skin Care", "Face", "Creams & Moisturizers"]
# 2023년 리뷰만 적재한다. 원본이 2023-09에서 끝나므로 상한은 두지 않는다.
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
    top_n: int = 20,
) -> tuple[int, int]:
    """메타·리뷰 줄 스트림에서 2023년 리뷰 수 상위 `top_n`개 얼굴 보습 제품과 그 2023년 리뷰 전부를 SQLite와 리뷰 벡터 저장소 파일에 적재한다.

    Returns:
        적재된 (상품 수, 리뷰 수).
    """
    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)

    for line in meta_lines:
        m = json.loads(line)
        if (m["categories"] or [])[1:4] != FACE_MOISTURIZER_PATH:
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
    conn.execute(
        "CREATE TEMP TABLE top_products AS SELECT parent_asin FROM reviews"
        " GROUP BY parent_asin ORDER BY COUNT(*) DESC, parent_asin LIMIT ?",
        (top_n,),
    )
    conn.execute("DELETE FROM reviews WHERE parent_asin NOT IN (SELECT parent_asin FROM top_products)")
    conn.execute("DELETE FROM products WHERE parent_asin NOT IN (SELECT parent_asin FROM top_products)")

    conn.commit()

    reviews = conn.execute(
        "SELECT review_id, parent_asin, rating, title, text, reviewed_at, verified_purchase FROM reviews"
    ).fetchall()
    store = InMemoryVectorStore(embeddings)
    store.add_texts(
        [document_prefix(title) + text for _, _, _, title, text, _, _ in reviews],
        metadatas=[
            {"parent_asin": parent_asin, "rating": rating, "title": title, "reviewed_at": reviewed_at,
             "verified_purchase": bool(verified)}
            for _, parent_asin, rating, title, _, reviewed_at, verified in reviews
        ],
        ids=[str(review_id) for review_id, *_ in reviews],
    )
    store.dump(str(vectors_path))

    counts = conn.execute("SELECT (SELECT COUNT(*) FROM products), (SELECT COUNT(*) FROM reviews)").fetchone()
    conn.close()
    return counts


def stream_lines(url: str) -> Iterator[str]:
    """`.jsonl.gz`를 디스크에 저장하지 않고 HTTP로 받으며 압축을 풀어 한 줄씩 넘긴다.

    첫 줄을 읽을 때 연결을 연다. 메타를 훑는 동안 리뷰 연결이 놀다가 끊기지 않게 하기 위해서다.
    """
    with urlopen(url) as response, gzip.open(response, "rt", encoding="utf-8") as lines:
        yield from lines


def main() -> None:
    parser = argparse.ArgumentParser(description="UCSD Beauty_and_Personal_Care에서 얼굴 보습 제품을 적재한다.")
    parser.add_argument("--db", type=Path, default=Path("data/reviews.db"), help="SQLite 파일 경로")
    parser.add_argument("--vectors", type=Path, default=Path("data/vectors.json"), help="리뷰 벡터 저장소 파일 경로")
    parser.add_argument("--top-n", type=int, default=20, help="적재할 상위 상품 개수")
    args = parser.parse_args()

    load_dotenv()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    products, reviews = load(
        stream_lines(META_URL), stream_lines(REVIEW_URL), args.db, args.vectors,
        OpenAIEmbeddings(model=EMBEDDING_MODEL), args.top_n,
    )
    print(f"완료: 상품 {products}개, 리뷰 {reviews}건")
