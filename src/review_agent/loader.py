import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

FACE_MOISTURIZER_PATH = ["Skin Care", "Face", "Creams & Moisturizers"]

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


def load(meta_lines: Iterable[str], review_lines: Iterable[str], db_path: Path, top_n: int = 20) -> None:
    """메타·리뷰 줄 스트림에서 리뷰 수 상위 `top_n`개 얼굴 보습 제품과 그 리뷰 전부를 SQLite에 적재한다."""
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
        if r["parent_asin"] not in product_ids:
            continue
        conn.execute(
            "INSERT INTO reviews (parent_asin, asin, user_id, rating, title, text, reviewed_at, helpful_vote,"
            " verified_purchase) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                r["parent_asin"], r["asin"], r["user_id"], r["rating"], r["title"], r["text"], None,
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
    conn.close()
