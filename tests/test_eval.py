import json

from langchain_core.embeddings import DeterministicFakeEmbedding

from review_agent.eval.cases import load_cases
from review_agent.eval.harness import TurnResult, evaluate
from review_agent.eval.compare import compare
from review_agent.eval.judge import JudgeVerdict
from review_agent.eval.report import run_meta, save_run
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
        answer=answer, trajectory=[{"tool": t, "args": a} for t, a in calls],
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

    assert (result["cases"][0]["passed"], result["cases"][0]["total"]) == (2, 3)


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
    assert summary["total"] == 2
    assert summary["by_type"] == {"집계": {"passed": 1, "total": 2}}
    assert summary["question_seconds"] == {"median": 2.0, "max": 3.0}
    assert summary["module_ms"] == {"llm": 3700.0, "run_sql": 60.0}
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


def test_result_records_the_rendered_questions(tmp_path):
    db = loaded_db(tmp_path, [meta("TOP", "Cloud Whip")], [review("TOP")] * 3)
    cases = one_case(tmp_path, db, """
[placeholders."리뷰 수 1위 상품"]
sql = "SELECT products.title FROM products JOIN reviews USING (parent_asin) GROUP BY parent_asin ORDER BY COUNT(*) DESC LIMIT 1"

[[cases]]
id = "agg-count"
type = "집계"
turns = ["{리뷰 수 1위 상품}의 리뷰는 몇 건이야?"]
expected_sql = "SELECT COUNT(*) FROM reviews"
""")

    result = evaluate(cases, db, executor([turn("3건입니다.")]), runs=1)

    assert result["cases"][0]["turns"] == ["Cloud Whip의 리뷰는 몇 건이야?"]


def test_summary_reports_median_tokens_per_question_and_keeps_total_out_of_the_module_breakdown(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")] * 3)
    cases = one_case(tmp_path, db, COUNT_CASE)
    cheap = turn("3건입니다.", timings_ms={"total": [1000.0], "llm": [800.0]}, tokens={"input": 100, "output": 20})
    dear = turn("3건입니다.", timings_ms={"total": [3000.0], "llm": [2900.0]}, tokens={"input": 300, "output": 80})

    summary = evaluate(cases, db, executor([cheap], [dear]), runs=2)["summary"]

    assert summary["question_tokens"] == {"median": 250.0, "total": 500}
    assert summary["module_ms"] == {"llm": 3700.0}


def test_expected_value_of_null_fails_the_case_instead_of_passing_unchecked(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")])
    cases = one_case(tmp_path, db, """
[[cases]]
id = "agg-price"
type = "집계"
turns = ["가격이 얼마야?"]
expected_sql = "SELECT price FROM products"
""")

    result = evaluate(cases, db, executor([turn("가격은 비어 있습니다.")]), runs=1)

    assert result["cases"][0]["passed"] == 0
    assert "NULL" in result["cases"][0]["runs"][0]["fail_reason"]


def test_a_number_matches_at_whatever_precision_the_answer_states(tmp_path):
    ratings = [review("A", rating=4.0), review("A", rating=5.0), review("A", rating=5.0)]
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], ratings)
    cases = one_case(tmp_path, db, """
[[cases]]
id = "agg-average"
type = "집계"
turns = ["평균 별점은?"]
expected_sql = "SELECT ROUND(AVG(rating), 2) FROM reviews"
""")

    exact = evaluate(cases, db, executor([turn("평균 별점은 4.67입니다.")]), runs=1)
    coarser = evaluate(cases, db, executor([turn("평균 별점은 4.7입니다.")]), runs=1)
    finer = evaluate(cases, db, executor([turn("평균 별점은 4.667입니다.")]), runs=1)
    wrong = evaluate(cases, db, executor([turn("평균 별점은 4.5입니다.")]), runs=1)

    assert exact["cases"][0]["passed"] == 1
    assert coarser["cases"][0]["passed"] == 1
    assert finer["cases"][0]["passed"] == 1
    assert wrong["cases"][0]["passed"] == 0


def test_run_meta_carries_the_scale_label_and_the_load_metrics(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")] * 3)

    info = run_meta(db, model="gpt-5.4-mini", judge_model=None, prompt_hash="abc123", vector_store_open_ms=21300.0)

    assert info["scale"] == {"label": "n1", "products": 1, "reviews": 3}
    assert info["run_id"].startswith("n1-")
    assert info["model"] == "gpt-5.4-mini"
    assert info["vector_store_open_ms"] == 21300.0
    assert info["load_metrics"]["reviews"] == 3


def test_run_meta_says_when_the_load_metrics_are_missing(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")] * 3)
    db.with_suffix(".metrics.json").unlink()

    info = run_meta(db, model="gpt-5.4-mini", judge_model=None, prompt_hash="abc123", vector_store_open_ms=0.0)

    assert info["load_metrics"] is None
    assert info["scale"] == {"label": "n1", "products": 1, "reviews": 3}


def verdicts(*passes):
    """정해진 판정을 순서대로 내놓는 가짜 심판."""
    remaining = list(passes)

    def judge(rubric, question, answer):
        return JudgeVerdict(passed=remaining.pop(0), reason="가짜 판정", tokens={"input": 50, "output": 10})

    return judge


RUBRIC_CASE = """
[[cases]]
id = "topic-stickiness"
type = "주제"
turns = ["사람들이 끈적임에 대해 뭐라고 해?"]
rubric = "끈적임에 대한 반복되는 반응을 들고 review_id와 원문 인용을 붙인다."
"""


def test_judge_verdict_decides_a_rubric_case(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")])
    cases = one_case(tmp_path, db, RUBRIC_CASE)

    failed = evaluate(cases, db, executor([turn("끈적인다는 말이 많습니다.")]), judge=verdicts(False), runs=1)
    passed = evaluate(cases, db, executor([turn("끈적인다는 말이 많습니다.")]), judge=verdicts(True), runs=1)

    assert failed["cases"][0]["passed"] == 0
    assert "가짜 판정" in failed["cases"][0]["runs"][0]["fail_reason"]
    assert passed["cases"][0]["passed"] == 1


def test_a_quoted_review_id_that_does_not_exist_fails_the_run(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")])
    cases = one_case(tmp_path, db, RUBRIC_CASE)
    real, fake = '#1 "sticky"', '#9999 "sticky"'

    quoted_real = evaluate(cases, db, executor([turn(f"끈적인다는 말이 많습니다. {real}")]), judge=verdicts(True), runs=1)
    quoted_fake = evaluate(cases, db, executor([turn(f"끈적인다는 말이 많습니다. {fake}")]), judge=verdicts(True), runs=1)

    assert quoted_real["cases"][0]["passed"] == 1
    assert quoted_fake["cases"][0]["passed"] == 0
    assert "9999" in quoted_fake["cases"][0]["runs"][0]["fail_reason"]


def test_a_sql_in_the_answer_that_disagrees_with_the_stated_number_fails_the_run(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")] * 3)
    cases = one_case(tmp_path, db, RUBRIC_CASE)
    agrees = "리뷰는 3건입니다. 근거: `SELECT COUNT(*) FROM reviews` → 3"
    disagrees = "리뷰는 7건입니다. 근거: `SELECT COUNT(*) FROM reviews` → 7"

    right = evaluate(cases, db, executor([turn(agrees)]), judge=verdicts(True), runs=1)
    wrong = evaluate(cases, db, executor([turn(disagrees)]), judge=verdicts(True), runs=1)

    assert right["cases"][0]["passed"] == 1
    assert wrong["cases"][0]["passed"] == 0
    assert "SQL" in wrong["cases"][0]["runs"][0]["fail_reason"]


def test_summary_reports_judge_agreement_with_the_human_labels(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")])
    cases = one_case(tmp_path, db, """
[[cases]]
id = "topic-stickiness"
type = "주제"
turns = ["사람들이 끈적임에 대해 뭐라고 해?"]
rubric = "끈적임에 대한 반복되는 반응을 든다."
human_label = "pass"
""")

    summary = evaluate(cases, db, executor([turn("끈적임 이야기가 많습니다.")], [turn("끈적임 이야기가 많습니다.")]),
                       judge=verdicts(True, False), runs=2)["summary"]

    assert summary["judge_agreement"] == {"matched": 1, "of": 2}


def test_judge_tokens_are_counted_apart_from_the_agent_tokens(tmp_path):
    db = loaded_db(tmp_path, [meta("A", "Cloud Whip")], [review("A")])
    cases = one_case(tmp_path, db, RUBRIC_CASE)
    answered = turn("끈적임 이야기가 많습니다.", tokens={"input": 900, "output": 100})

    summary = evaluate(cases, db, executor([answered]), judge=verdicts(True), runs=1)["summary"]

    assert summary["tokens"] == {"input": 900, "output": 100}
    assert summary["judge_tokens"] == {"input": 50, "output": 10}


def run_document(label="n20", cases=(), seconds=2.0, tokens=1000, commit="aaa1111", prompt_hash="p1"):
    """비교에 넣을 평가 결과 하나. (케이스 id, 통과 횟수, 실행 횟수, 유형) 목록으로 만든다."""
    return {
        "run_id": f"{label}-{commit}-000001",
        "scale": {"label": label, "products": 20, "reviews": 4744},
        "load_metrics": {"load_seconds": 60.0, "embedding_seconds": 10.0, "db_bytes": 1, "vectors_bytes": 2},
        "model": "gpt-5.4-mini", "judge_model": "gpt-5.4", "prompt_hash": prompt_hash, "commit": commit,
        "vector_store_open_ms": 13000.0,
        "cases": [
            {"id": i, "type": t, "passed": p, "total": n, "turns": ["질문"], "resolved": {}, "human_label": None,
             "runs": [{"fail_reason": None if p else "실패"}]}
            for i, p, n, t in cases
        ],
        "summary": {
            "passed": sum(p for _, p, _, _ in cases), "total": sum(n for _, _, n, _ in cases),
            "by_type": {}, "question_seconds": {"median": seconds, "max": seconds * 2},
            "module_ms": {"llm": 1000.0}, "tokens": {"input": tokens, "output": 100},
            "judge_tokens": {"input": 50, "output": 10}, "judge_agreement": {"matched": 2, "of": 2},
            "question_tokens": {"median": tokens / 2, "total": tokens}, "embedding_calls": 4,
        },
    }


def test_a_case_that_fell_from_every_run_passing_to_one_is_a_regression(tmp_path):
    baseline = run_document(cases=[("agg", 3, 3, "집계"), ("refuse", 2, 3, "거절")])
    current = run_document(cases=[("agg", 1, 3, "집계"), ("refuse", 3, 3, "거절")], commit="bbb2222")

    comparison = compare(current, baseline)

    assert comparison.verdict == "회귀"
    assert comparison.regressed == ["agg"]
    assert comparison.newly_passing == ["refuse"]


def test_the_same_overall_pass_rate_does_not_hide_a_regression(tmp_path):
    baseline = run_document(cases=[("agg", 3, 3, "집계"), ("topic", 1, 3, "주제")])
    current = run_document(cases=[("agg", 1, 3, "집계"), ("topic", 3, 3, "주제")], commit="bbb2222")

    comparison = compare(current, baseline)

    assert (comparison.verdict, comparison.regressed) == ("회귀", ["agg"])
    assert current["summary"]["passed"] == baseline["summary"]["passed"]


def test_a_case_that_only_fell_to_two_of_three_is_not_a_regression(tmp_path):
    baseline = run_document(cases=[("agg", 3, 3, "집계")])
    current = run_document(cases=[("agg", 2, 3, "집계")], commit="bbb2222")

    comparison = compare(current, baseline)

    assert comparison.verdict == "이상 없음"
    assert comparison.regressed == []


def test_quality_is_not_compared_across_different_scales(tmp_path):
    baseline = run_document(label="n20", cases=[("agg", 3, 3, "집계")], seconds=2.0)
    current = run_document(label="n200", cases=[("agg", 0, 3, "집계")], seconds=9.0, commit="bbb2222")

    comparison = compare(current, baseline)

    assert comparison.verdict == "규모 다름"
    assert comparison.regressed == []
    assert "품질은 비교하지 않" in comparison.markdown
    assert "9.0" in comparison.markdown


def test_without_a_baseline_a_single_result_report_comes_out(tmp_path):
    current = run_document(cases=[("agg", 3, 3, "집계"), ("topic", 2, 3, "주제")])

    comparison = compare(current, None)

    assert comparison.verdict == "기준선 없음"
    assert "기준선이 됩니다" in comparison.markdown
    for expected in ["5/6", "집계", "llm", "심판", "적재"]:
        assert expected in comparison.markdown


def test_comparison_report_shows_the_changes_and_the_conditions(tmp_path):
    baseline = run_document(cases=[("agg", 3, 3, "집계")], seconds=2.0, tokens=1000)
    current = run_document(cases=[("agg", 1, 3, "집계")], seconds=3.0, tokens=1400, commit="bbb2222",
                           prompt_hash="p2")

    markdown = compare(current, baseline).markdown

    for expected in ["회귀", "agg", "3/3", "1/3", "2.0", "3.0", "1000", "1400", "p1", "p2", "bbb2222"]:
        assert expected in markdown
