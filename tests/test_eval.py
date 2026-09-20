import json

from langchain_core.embeddings import DeterministicFakeEmbedding

from review_agent.eval.cases import load_cases
from review_agent.eval.harness import TurnResult, evaluate
from review_agent.eval.report import save_run
from review_agent.loader import load

FACE = ["Beauty & Personal Care", "Skin Care", "Face", "Creams & Moisturizers"]
FAKE_EMBEDDINGS = DeterministicFakeEmbedding(size=8)


def write_cases(tmp_path, body):
    path = tmp_path / "cases.toml"
    path.write_text(body, encoding="utf-8")
    return path


def meta(parent_asin, title):
    return json.dumps({
        "title": title, "average_rating": 4.2, "rating_number": 15, "features": [], "price": None,
        "store": "Bissport", "categories": FACE, "details": {}, "parent_asin": parent_asin,
    })


def review(parent_asin, rating=5.0, text="Lovely."):
    return json.dumps({
        "rating": rating, "title": "Nice", "text": text, "asin": parent_asin + "-V", "parent_asin": parent_asin,
        "user_id": "AGKHLEW2SOWHNMFQIJGBECAF7INQ", "timestamp": 1683295728923, "helpful_vote": 0,
        "verified_purchase": True,
    })


def loaded_db(tmp_path, metas, reviews):
    """픽스처를 적재한 적재 데이터의 SQLite 경로."""
    db = tmp_path / "reviews.db"
    load(metas, reviews, db, tmp_path / "vectors.json", FAKE_EMBEDDINGS)
    return db


def test_load_cases_reads_id_type_and_turns(tmp_path):
    path = write_cases(tmp_path, """
[[cases]]
id = "agg-top3"
type = "집계"
turns = ["리뷰가 가장 많은 상품 3개는?"]
""")

    cases = load_cases(path)

    assert [(c.id, c.type, c.turns) for c in cases] == [("agg-top3", "집계", ["리뷰가 가장 많은 상품 3개는?"])]


def test_placeholder_is_rendered_with_the_real_product_from_the_loaded_data(tmp_path):
    db = loaded_db(tmp_path, [meta("TOP", "Cloud Whip"), meta("LOW", "Snail Cream")], [review("TOP")] * 3 + [review("LOW")])
    path = write_cases(tmp_path, """
[placeholders."리뷰 수 1위 상품"]
sql = "SELECT products.title, parent_asin FROM products JOIN reviews USING (parent_asin) GROUP BY parent_asin ORDER BY COUNT(*) DESC LIMIT 1"

[[cases]]
id = "mix-complaints"
type = "혼합"
turns = ["{리뷰 수 1위 상품}의 불만은?", "{리뷰 수 1위 상품:parent_asin} 말이야"]
""")

    case = load_cases(path, db)[0]

    assert case.turns == ["Cloud Whip의 불만은?", "TOP 말이야"]
    assert case.resolved == {"리뷰 수 1위 상품": "Cloud Whip", "리뷰 수 1위 상품:parent_asin": "TOP"}


def executor(*turns_per_run):
    """미리 정한 턴 결과를 돌려주는 가짜 실행기. 실행 횟수만큼 순서대로 쓴다."""
    runs = list(turns_per_run)

    def execute(questions):
        return runs.pop(0)

    return execute


def turn(answer, calls=(), timings_ms=None, tokens=None):
    return TurnResult(
        answer=answer, calls=[{"tool": t, "args": a} for t, a in calls],
        timings_ms=timings_ms or {}, tokens=tokens or {},
    )


def test_case_passes_only_when_the_answer_contains_the_number_the_expected_sql_computes(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")] * 3)
    path = write_cases(tmp_path, """
[[cases]]
id = "agg-count"
type = "집계"
turns = ["리뷰가 몇 건이야?"]
expected_sql = "SELECT COUNT(*) FROM reviews"
""")
    cases = load_cases(path, db)

    right = evaluate(cases, db, executor([turn("적재된 리뷰는 3건입니다.")]), runs=1)
    wrong = evaluate(cases, db, executor([turn("적재된 리뷰는 5건입니다.")]), runs=1)

    assert right["cases"][0]["passed"] == 1
    assert wrong["cases"][0]["passed"] == 0


def one_case(tmp_path, db, body):
    return load_cases(write_cases(tmp_path, body), db)


def test_refusal_case_passes_only_when_the_agent_refuses(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")])
    cases = one_case(tmp_path, db, """
[[cases]]
id = "refuse-sales"
type = "거절"
turns = ["한국 매출은?"]
must_refuse = true
""")

    refused = evaluate(cases, db, executor([turn("적재 데이터로는 답할 수 없습니다.")]), runs=1)
    refused_otherwise = evaluate(cases, db, executor([turn("적재 데이터로는 한국 매출을 알 수 없습니다.")]), runs=1)
    made_up = evaluate(cases, db, executor([turn("한국 매출은 약 3억 원입니다.")]), runs=1)

    assert refused["cases"][0]["passed"] == 1
    assert refused_otherwise["cases"][0]["passed"] == 1
    assert made_up["cases"][0]["passed"] == 0


MIX_CASE = """
[[cases]]
id = "mix-complaints"
type = "혼합"
turns = ["Cloud Whip의 1~2점 불만은?"]
expected_sql = "SELECT COUNT(*) FROM reviews"

[[cases.expected_trajectory]]
tool = "run_sql"
args_match = { sql = "products.+title.+LIKE" }

[[cases.expected_trajectory]]
tool = "search_reviews"
args_match = { parent_asin = "A", max_rating = "<=2" }

[[cases.forbidden]]
tool = "search_reviews"
args_missing = ["parent_asin"]
"""

FIND_PRODUCT = ("run_sql", {"sql": "SELECT parent_asin FROM products WHERE title LIKE '%Cloud%'"})
COUNT_ROWS = ("run_sql", {"sql": "SELECT COUNT(*) FROM reviews WHERE rating <= 2"})
SEARCH_COMPLAINTS = ("search_reviews", {"query": "complaints", "parent_asin": "A", "max_rating": 2})


def test_trajectory_passes_when_extra_calls_sit_between_the_expected_ones(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")])
    cases = one_case(tmp_path, db, MIX_CASE)
    calls = [FIND_PRODUCT, COUNT_ROWS, SEARCH_COMPLAINTS, SEARCH_COMPLAINTS]

    result = evaluate(cases, db, executor([turn("1건 있고 불만은 끈적임입니다.", calls)]), runs=1)

    assert result["cases"][0]["passed"] == 1


def test_trajectory_fails_when_the_expected_order_is_reversed(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")])
    cases = one_case(tmp_path, db, MIX_CASE)
    calls = [SEARCH_COMPLAINTS, FIND_PRODUCT]

    result = evaluate(cases, db, executor([turn("1건 있고 불만은 끈적임입니다.", calls)]), runs=1)

    assert result["cases"][0]["passed"] == 0
    assert "순서" in result["cases"][0]["runs"][0]["fail_reason"]


def test_trajectory_fails_when_an_argument_condition_is_broken(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")])
    cases = one_case(tmp_path, db, MIX_CASE)
    too_wide = ("search_reviews", {"query": "complaints", "parent_asin": "A", "max_rating": 4})

    result = evaluate(cases, db, executor([turn("1건 있고 불만은 끈적임입니다.", [FIND_PRODUCT, too_wide])]), runs=1)

    assert result["cases"][0]["passed"] == 0


def test_forbidden_pattern_fails_the_run_even_when_everything_else_is_right(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")])
    cases = one_case(tmp_path, db, MIX_CASE)
    unfiltered = ("search_reviews", {"query": "complaints"})
    calls = [FIND_PRODUCT, SEARCH_COMPLAINTS, unfiltered]

    result = evaluate(cases, db, executor([turn("1건 있고 불만은 끈적임입니다.", calls)]), runs=1)

    assert result["cases"][0]["passed"] == 0
    assert "금지 패턴" in result["cases"][0]["runs"][0]["fail_reason"]


def test_only_the_last_turn_is_scored(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")])
    cases = one_case(tmp_path, db, MIX_CASE)
    first = turn("먼저 찾습니다.", [("search_reviews", {"query": "anything"})])
    last = turn("1건 있고 불만은 끈적임입니다.", [FIND_PRODUCT, SEARCH_COMPLAINTS])

    result = evaluate(cases, db, executor([first, last]), runs=1)

    assert result["cases"][0]["passed"] == 1


def test_case_result_counts_how_many_of_the_runs_passed(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")] * 3)
    cases = one_case(tmp_path, db, """
[[cases]]
id = "agg-count"
type = "집계"
turns = ["리뷰가 몇 건이야?"]
expected_sql = "SELECT COUNT(*) FROM reviews"
""")

    result = evaluate(
        cases, db,
        executor([turn("3건입니다.")], [turn("5건입니다.")], [turn("3건입니다.")]),
        runs=3,
    )

    assert (result["cases"][0]["passed"], result["cases"][0]["of"]) == (2, 3)


COUNT_CASE = """
[[cases]]
id = "agg-count"
type = "집계"
turns = ["리뷰가 몇 건이야?"]
expected_sql = "SELECT COUNT(*) FROM reviews"
"""


def test_summary_reports_pass_rate_module_times_and_tokens(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")] * 3)
    cases = one_case(tmp_path, db, COUNT_CASE)
    fast = turn("3건입니다.", timings_ms={"total": [1000.0], "llm": [800.0], "run_sql": [20.0]},
                tokens={"input": 100, "output": 30})
    slow = turn("5건입니다.", timings_ms={"total": [3000.0], "llm": [2900.0], "run_sql": [40.0]},
                tokens={"input": 120, "output": 50})

    summary = evaluate(cases, db, executor([fast], [slow]), runs=2)["summary"]

    assert summary["passed"] == 1
    assert summary["of"] == 2
    assert summary["by_type"] == {"집계": {"passed": 1, "of": 2}}
    assert summary["question_seconds"] == {"median": 2.0, "max": 3.0}
    assert summary["module_ms"] == {"total": 4000.0, "llm": 3700.0, "run_sql": 60.0}
    assert summary["tokens"] == {"input": 220, "output": 80}


def test_committed_result_holds_no_answer_text_and_details_do(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")] * 3)
    cases = one_case(tmp_path, db, COUNT_CASE)
    result = evaluate(cases, db, executor([turn("적재된 리뷰는 3건입니다.")]), runs=1)

    run_path, details_path = save_run(result, tmp_path / "runs", tmp_path / "details", {"run_id": "n1-abcdef0"})

    committed = run_path.read_text(encoding="utf-8")
    assert "적재된 리뷰는 3건입니다." not in committed
    assert json.loads(committed)["run_id"] == "n1-abcdef0"
    assert json.loads(committed)["cases"][0]["passed"] == 1
    details = json.loads(details_path.read_text(encoding="utf-8"))
    assert details["cases"][0]["runs"][0]["answer"] == "적재된 리뷰는 3건입니다."


def test_embedding_call_counts_are_recorded_and_summed(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")] * 3)
    cases = one_case(tmp_path, db, COUNT_CASE)
    searched = TurnResult(answer="3건입니다.", embedding_calls=2)
    searched_more = TurnResult(answer="3건입니다.", embedding_calls=3)

    result = evaluate(cases, db, executor([searched], [searched_more]), runs=2)

    assert [a["embedding_calls"] for a in result["cases"][0]["runs"]] == [2, 3]
    assert result["summary"]["embedding_calls"] == 5
