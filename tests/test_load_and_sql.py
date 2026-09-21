import json

import pytest

from langchain_core.embeddings import DeterministicFakeEmbedding

from review_agent.loader import load
from review_agent.search_tool import open_store, search_reviews
from review_agent.sql_tool import run_sql

FACE = ["Beauty & Personal Care", "Skin Care", "Face", "Creams & Moisturizers", "Face Moisturizers"]
BODY = ["Beauty & Personal Care", "Skin Care", "Body", "Moisturizers", "Lotions"]
LIP = ["Beauty & Personal Care", "Skin Care", "Lip Care", "Balms & Moisturizers"]
HAIR = ["Beauty & Personal Care", "Hair Care", "Styling Products", "Creams"]
FAKE_EMBEDDINGS = DeterministicFakeEmbedding(size=8)


def meta(parent_asin, categories=FACE, title="Hydra Cream"):
    return json.dumps({
        "main_category": "All Beauty", "title": title, "average_rating": 4.2, "rating_number": 15,
        "features": ["Formulation: Cream"], "description": [], "price": None, "images": [], "videos": [],
        "store": "Bissport", "categories": categories, "details": {"Brand": "Bissport"},
        "parent_asin": parent_asin, "bought_together": None,
    })


def review(parent_asin, timestamp=1683295728923, rating=5.0, text="Lovely.", verified=True):
    return json.dumps({
        "rating": rating, "title": "Nice", "text": text, "images": [], "asin": parent_asin + "-V",
        "parent_asin": parent_asin, "user_id": "AGKHLEW2SOWHNMFQIJGBECAF7INQ", "timestamp": timestamp,
        "helpful_vote": 0, "verified_purchase": verified,
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


def test_scope_argument_loads_only_products_under_that_category_path(tmp_path):
    db = tmp_path / "reviews.db"
    metas = [meta("FACE1"), meta("BODY1", BODY), meta("HAIR1", HAIR)]
    reviews = [review("FACE1"), review("BODY1"), review("HAIR1")]

    load(metas, reviews, db, tmp_path / "vectors.json", FAKE_EMBEDDINGS, scope=["Skin Care"])

    assert rows(db, "SELECT parent_asin FROM products ORDER BY parent_asin") == [["BODY1"], ["FACE1"]]
    assert rows(db, "SELECT DISTINCT parent_asin FROM reviews ORDER BY parent_asin") == [["BODY1"], ["FACE1"]]


def test_a_wider_scope_still_loads_only_2023_reviews(tmp_path):
    db = tmp_path / "reviews.db"
    end_of_2022 = 1672531199999  # 2022-12-31T23:59:59.999Z
    metas = [meta("FACE1"), meta("BODY1", BODY)]
    reviews = [review("FACE1", timestamp=end_of_2022), review("BODY1", timestamp=end_of_2022), review("BODY1")]

    load(metas, reviews, db, tmp_path / "vectors.json", FAKE_EMBEDDINGS, scope=["Skin Care"])

    assert rows(db, "SELECT parent_asin, date(reviewed_at) FROM reviews") == [["BODY1", "2023-05-05"]]
    assert rows(db, "SELECT parent_asin FROM products") == [["BODY1"]]


def test_top_n_none_loads_every_product_in_scope_that_has_a_2023_review(tmp_path):
    db = tmp_path / "reviews.db"
    metas = [meta("A"), meta("B"), meta("C"), meta("NO_2023"), meta("BODY1", BODY)]
    reviews = [review("A")] * 3 + [review("B")] * 2 + [review("C")] + [review("BODY1")] * 5

    assert load(metas, reviews, db, tmp_path / "vectors.json", FAKE_EMBEDDINGS, top_n=None) == (3, 6)
    assert rows(db, "SELECT parent_asin FROM products ORDER BY parent_asin") == [["A"], ["B"], ["C"]]


def test_the_load_scope_is_recorded_beside_the_loaded_data(tmp_path):
    db = tmp_path / "reviews.db"

    load([meta("A")], [review("A")], db, tmp_path / "vectors.json", FAKE_EMBEDDINGS, top_n=None, scope=["Skin Care"])

    metrics = json.loads((tmp_path / "reviews.metrics.json").read_text(encoding="utf-8"))
    assert (metrics["scope"], metrics["top_n"]) == (["Skin Care"], None)


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


def test_search_reviews_returns_only_reviews_within_the_rating_range(tmp_path):
    db, vectors = tmp_path / "reviews.db", tmp_path / "vectors.json"
    load([meta("A")], [review("A", rating=r) for r in [1.0, 2.0, 3.0, 4.0, 5.0]], db, vectors, FAKE_EMBEDDINGS)

    results = search_reviews(open_store(vectors, FAKE_EMBEDDINGS), "sticky", min_rating=2, max_rating=4)

    assert sorted(r["rating"] for r in results) == [2.0, 3.0, 4.0]


def test_search_reviews_returns_only_verified_purchases_when_asked(tmp_path):
    db, vectors = tmp_path / "reviews.db", tmp_path / "vectors.json"
    reviews = [review("A", text="verified"), review("A", text="unverified", verified=False)]
    load([meta("A")], reviews, db, vectors, FAKE_EMBEDDINGS)

    results = search_reviews(open_store(vectors, FAKE_EMBEDDINGS), "sticky", verified_only=True)

    assert [r["text"] for r in results] == ["verified"]


def test_search_reviews_result_is_the_same_review_in_run_sql(tmp_path):
    db, vectors = tmp_path / "reviews.db", tmp_path / "vectors.json"
    reviews = [review("A", rating=r, text=f"Text {r}") for r in [1.0, 3.0, 5.0]] + [review("B", text="Other")]
    load([meta("A"), meta("B")], reviews, db, vectors, FAKE_EMBEDDINGS)

    results = search_reviews(open_store(vectors, FAKE_EMBEDDINGS), "sticky")

    assert len(results) == 4
    for r in results:
        assert rows(db, f"SELECT parent_asin, rating, title, text FROM reviews WHERE review_id = {r['review_id']}") == [
            [r["parent_asin"], r["rating"], r["title"], r["text"]],
        ]


def test_reloading_leaves_no_previous_reviews_in_search(tmp_path):
    db, vectors = tmp_path / "reviews.db", tmp_path / "vectors.json"
    load([meta("OLD")], [review("OLD")] * 3, db, vectors, FAKE_EMBEDDINGS)

    load([meta("NEW")], [review("NEW")], db, vectors, FAKE_EMBEDDINGS)

    assert [r["parent_asin"] for r in search_reviews(open_store(vectors, FAKE_EMBEDDINGS), "sticky")] == ["NEW"]


def test_failed_reload_leaves_no_previous_reviews_for_search(tmp_path):
    class FailingEmbeddings(DeterministicFakeEmbedding):
        def embed_documents(self, texts):
            raise RuntimeError("embedding failed")

    db, vectors = tmp_path / "reviews.db", tmp_path / "vectors.json"
    load([meta("OLD")], [review("OLD")], db, vectors, FAKE_EMBEDDINGS)

    with pytest.raises(RuntimeError):
        load([meta("NEW")], [review("NEW")], db, vectors, FailingEmbeddings(size=8))

    assert not vectors.exists()


def test_load_writes_its_own_metrics_next_to_the_database(tmp_path):
    db = tmp_path / "reviews.db"
    metas, reviews = [meta("A"), meta("B")], [review("A")] * 3 + [review("B")]

    load(metas, reviews, db, tmp_path / "vectors.json", FAKE_EMBEDDINGS)

    metrics = json.loads((tmp_path / "reviews.metrics.json").read_text(encoding="utf-8"))
    assert (metrics["products"], metrics["reviews"]) == (2, 4)
    assert metrics["load_seconds"] > 0
    assert metrics["embedding_seconds"] >= 0
    assert metrics["db_bytes"] > 0
    assert metrics["vectors_bytes"] > 0


def test_discarded_reviews_do_not_leave_their_space_in_the_database(tmp_path):
    kept = [review("A")] * 400
    lean, fat = tmp_path / "lean.db", tmp_path / "fat.db"
    load([meta("A")], kept, lean, tmp_path / "lean.json", FAKE_EMBEDDINGS, top_n=1)

    load([meta("A"), meta("B")], kept + [review("B")] * 200, fat, tmp_path / "fat.json", FAKE_EMBEDDINGS, top_n=1)

    assert rows(fat, "SELECT parent_asin FROM products") == [["A"]]
    assert fat.stat().st_size == lean.stat().st_size
