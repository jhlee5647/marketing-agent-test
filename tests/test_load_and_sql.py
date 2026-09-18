import json

from langchain_core.embeddings import DeterministicFakeEmbedding

from review_agent.loader import load
from review_agent.search_tool import open_store, search_reviews
from review_agent.sql_tool import run_sql

FACE = ["Beauty & Personal Care", "Skin Care", "Face", "Creams & Moisturizers", "Face Moisturizers"]
BODY = ["Beauty & Personal Care", "Skin Care", "Body", "Moisturizers", "Lotions"]
LIP = ["Beauty & Personal Care", "Skin Care", "Lip Care", "Balms & Moisturizers"]
FAKE_EMBEDDINGS = DeterministicFakeEmbedding(size=8)


def meta(parent_asin, categories=FACE, title="Hydra Cream"):
    return json.dumps({
        "main_category": "All Beauty", "title": title, "average_rating": 4.2, "rating_number": 15,
        "features": ["Formulation: Cream"], "description": [], "price": None, "images": [], "videos": [],
        "store": "Bissport", "categories": categories, "details": {"Brand": "Bissport"},
        "parent_asin": parent_asin, "bought_together": None,
    })


def review(parent_asin, timestamp=1683295728923, rating=5.0, text="Lovely."):
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

    load(metas, reviews, db, tmp_path / "vectors.json", FAKE_EMBEDDINGS)

    assert rows(db, "SELECT parent_asin FROM products") == [["FACE1"]]
    assert rows(db, "SELECT parent_asin FROM reviews") == [["FACE1"]]


def test_only_top_n_products_by_review_count_are_loaded_with_all_their_reviews(tmp_path):
    db = tmp_path / "reviews.db"
    metas = [meta("A"), meta("B"), meta("C")]
    reviews = [review("A")] + [review("B")] * 3 + [review("C")] * 2

    load(metas, reviews, db, tmp_path / "vectors.json", FAKE_EMBEDDINGS, top_n=2)

    assert rows(db, "SELECT parent_asin FROM products ORDER BY parent_asin") == [["B"], ["C"]]
    assert rows(db, "SELECT parent_asin, COUNT(*) FROM reviews GROUP BY parent_asin ORDER BY parent_asin") == [
        ["B", 3], ["C", 2],
    ]


def test_reviews_without_meta_are_not_loaded(tmp_path):
    db = tmp_path / "reviews.db"

    load(
        [meta("A")], [review("A"), review("ORPHAN"), review("ORPHAN")], db, tmp_path / "vectors.json", FAKE_EMBEDDINGS
    )

    assert rows(db, "SELECT parent_asin FROM reviews") == [["A"]]
    assert rows(db, "SELECT parent_asin FROM products") == [["A"]]


def test_reloading_leaves_no_previous_data(tmp_path):
    db = tmp_path / "reviews.db"
    load([meta("OLD")], [review("OLD")], db, tmp_path / "vectors.json", FAKE_EMBEDDINGS)

    load([meta("NEW")], [review("NEW")], db, tmp_path / "vectors.json", FAKE_EMBEDDINGS)

    assert rows(db, "SELECT parent_asin FROM products") == [["NEW"]]
    assert rows(db, "SELECT parent_asin FROM reviews") == [["NEW"]]


def test_millisecond_timestamp_is_queryable_as_iso_date(tmp_path):
    db = tmp_path / "reviews.db"

    load([meta("A")], [review("A", timestamp=1683295728923)], db, tmp_path / "vectors.json", FAKE_EMBEDDINGS)

    assert rows(db, "SELECT date(reviewed_at) FROM reviews") == [["2023-05-05"]]


def test_run_sql_rejects_writes_and_leaves_data_unchanged(tmp_path):
    db = tmp_path / "reviews.db"
    load([meta("A")], [review("A")], db, tmp_path / "vectors.json", FAKE_EMBEDDINGS)

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


def test_run_sql_truncates_results_over_50_rows(tmp_path):
    db = tmp_path / "reviews.db"
    load([meta("A")], [review("A")] * 51, db, tmp_path / "vectors.json", FAKE_EMBEDDINGS)

    result = run_sql(db, "SELECT review_id FROM reviews")

    assert len(result["rows"]) == 50
    assert result["truncated"] is True


def test_run_sql_does_not_mark_results_of_50_rows_or_fewer_as_truncated(tmp_path):
    db = tmp_path / "reviews.db"
    load([meta("A")], [review("A")] * 50, db, tmp_path / "vectors.json", FAKE_EMBEDDINGS)

    result = run_sql(db, "SELECT review_id FROM reviews")

    assert len(result["rows"]) == 50
    assert result["truncated"] is False


def test_run_sql_returns_syntax_error_as_message(tmp_path):
    db = tmp_path / "reviews.db"
    load([meta("A")], [review("A")], db, tmp_path / "vectors.json", FAKE_EMBEDDINGS)

    result = run_sql(db, "SELEC * FROM reviews")

    assert "syntax error" in result["error"]


def test_load_returns_loaded_product_and_review_counts(tmp_path):
    db = tmp_path / "reviews.db"
    metas = [meta("A"), meta("B"), meta("C"), meta("BODY1", BODY)]
    reviews = [review("A")] * 3 + [review("B")] * 2 + [review("C")] + [review("BODY1")] * 5

    assert load(metas, reviews, db, tmp_path / "vectors.json", FAKE_EMBEDDINGS, top_n=2) == (2, 5)


def test_run_sql_returns_error_message_when_nothing_is_loaded(tmp_path):
    result = run_sql(tmp_path / "missing.db", "SELECT * FROM reviews")

    assert "error" in result
    assert not (tmp_path / "missing.db").exists()


def test_only_2023_reviews_are_loaded_and_ranked(tmp_path):
    db = tmp_path / "reviews.db"
    end_of_2022 = 1672531199999  # 2022-12-31T23:59:59.999Z
    start_of_2023 = 1672531200000  # 2023-01-01T00:00:00Z
    metas = [meta("OLD_POPULAR"), meta("NEW")]
    reviews = [review("OLD_POPULAR", timestamp=end_of_2022)] * 3 + [review("NEW", timestamp=start_of_2023)]

    load(metas, reviews, db, tmp_path / "vectors.json", FAKE_EMBEDDINGS, top_n=1)

    assert rows(db, "SELECT parent_asin FROM products") == [["NEW"]]
    assert rows(db, "SELECT parent_asin, reviewed_at FROM reviews") == [["NEW", "2023-01-01T00:00:00+00:00"]]


def test_search_reviews_returns_only_reviews_of_the_given_product(tmp_path):
    db, vectors = tmp_path / "reviews.db", tmp_path / "vectors.json"
    load([meta("A"), meta("B")], [review("A")] * 3 + [review("B")] * 3, db, vectors, FAKE_EMBEDDINGS)

    results = search_reviews(open_store(vectors, FAKE_EMBEDDINGS), "moisturizing", parent_asin="A")

    assert [r["parent_asin"] for r in results] == ["A"] * 3
