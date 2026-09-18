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
