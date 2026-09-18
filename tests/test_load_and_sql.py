import json

from review_agent.loader import load
from review_agent.sql_tool import run_sql

FACE = ["Beauty & Personal Care", "Skin Care", "Face", "Creams & Moisturizers", "Face Moisturizers"]
BODY = ["Beauty & Personal Care", "Skin Care", "Body", "Moisturizers", "Lotions"]
LIP = ["Beauty & Personal Care", "Skin Care", "Lip Care", "Balms & Moisturizers"]


def meta(parent_asin, categories=FACE, title="Hydra Cream"):
    return json.dumps({
        "main_category": "All Beauty", "title": title, "average_rating": 4.2, "rating_number": 15,
        "features": ["Formulation: Cream"], "description": [], "price": None, "images": [], "videos": [],
        "store": "Bissport", "categories": categories, "details": {"Brand": "Bissport"},
        "parent_asin": parent_asin, "bought_together": None,
    })


def review(parent_asin, timestamp=1588687728923, rating=5.0, text="Lovely."):
    return json.dumps({
        "rating": rating, "title": "Nice", "text": text, "images": [], "asin": parent_asin + "-V",
        "parent_asin": parent_asin, "user_id": "AGKHLEW2SOWHNMFQIJGBECAF7INQ", "timestamp": timestamp,
        "helpful_vote": 0, "verified_purchase": True,
    })


def rows(db, sql):
    return run_sql(db, sql)["rows"]


def test_only_face_moisturizers_and_their_reviews_are_loaded(tmp_path):
    db = tmp_path / "reviews.db"
    metas = [meta("FACE1"), meta("BODY1", BODY), meta("LIP1", LIP)]
    reviews = [review("FACE1"), review("BODY1"), review("LIP1")]

    load(metas, reviews, db)

    assert rows(db, "SELECT parent_asin FROM products") == [["FACE1"]]
    assert rows(db, "SELECT parent_asin FROM reviews") == [["FACE1"]]


def test_only_top_n_products_by_review_count_are_loaded_with_all_their_reviews(tmp_path):
    db = tmp_path / "reviews.db"
    metas = [meta("A"), meta("B"), meta("C")]
    reviews = [review("A")] + [review("B")] * 3 + [review("C")] * 2

    load(metas, reviews, db, top_n=2)

    assert rows(db, "SELECT parent_asin FROM products ORDER BY parent_asin") == [["B"], ["C"]]
    assert rows(db, "SELECT parent_asin, COUNT(*) FROM reviews GROUP BY parent_asin ORDER BY parent_asin") == [
        ["B", 3], ["C", 2],
    ]


def test_reviews_without_meta_are_not_loaded(tmp_path):
    db = tmp_path / "reviews.db"

    load([meta("A")], [review("A"), review("ORPHAN"), review("ORPHAN")], db)

    assert rows(db, "SELECT parent_asin FROM reviews") == [["A"]]
    assert rows(db, "SELECT parent_asin FROM products") == [["A"]]


def test_reloading_leaves_no_previous_data(tmp_path):
    db = tmp_path / "reviews.db"
    load([meta("OLD")], [review("OLD")], db)

    load([meta("NEW")], [review("NEW")], db)

    assert rows(db, "SELECT parent_asin FROM products") == [["NEW"]]
    assert rows(db, "SELECT parent_asin FROM reviews") == [["NEW"]]


def test_millisecond_timestamp_is_queryable_as_iso_date(tmp_path):
    db = tmp_path / "reviews.db"

    load([meta("A")], [review("A", timestamp=1588687728923)], db)

    assert rows(db, "SELECT date(reviewed_at) FROM reviews") == [["2020-05-05"]]


def test_run_sql_rejects_writes_and_leaves_data_unchanged(tmp_path):
    db = tmp_path / "reviews.db"
    load([meta("A")], [review("A")], db)

    for sql in [
        "INSERT INTO products (parent_asin) VALUES ('X')",
        "UPDATE reviews SET rating = 1",
        "DELETE FROM reviews",
        "DROP TABLE reviews",
        f"ATTACH '{tmp_path / 'other.db'}' AS other",
    ]:
        assert "error" in run_sql(db, sql)

    assert not (tmp_path / "other.db").exists()
    assert rows(db, "SELECT parent_asin, rating FROM reviews") == [["A", 5.0]]
    assert rows(db, "SELECT parent_asin FROM products") == [["A"]]
