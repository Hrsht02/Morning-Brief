from app.ingestion.verification import compute_max_similarity


def test_short_summary_is_not_automatically_100_percent_similar():
    source = "Reports of dwindling US weapons stocks have triggered an unusually sweeping hunt for leakers inside the Pentagon and officials are investigating the source of the leaks."
    summary = "Reports of dwindling US weapons stocks have triggered an unusually sweeping hunt for leakers inside the Pentagon."
    score = compute_max_similarity(summary, [source])
    assert score < 1.0
    assert score > 0.5


def test_exact_copy_is_still_high_similarity():
    source = "The central bank kept its benchmark interest rate unchanged on Tuesday."
    assert compute_max_similarity(source, [source]) == 1.0


def test_different_wording_has_lower_similarity():
    source = "The central bank kept its benchmark interest rate unchanged on Tuesday."
    summary = "Officials left borrowing costs unchanged at the latest policy meeting."
    assert compute_max_similarity(summary, [source]) < 0.5
