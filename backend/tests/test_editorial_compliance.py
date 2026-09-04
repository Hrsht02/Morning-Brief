from app.services.editorial_compliance import mandatory_human_review, sensitive_flags


def test_similarity_is_not_enough_for_sensitive_story():
    required, flags = mandatory_human_review(
        "Police arrested John Smith over an alleged fraud case.",
        source_count=3,
        verifier_report={"available": True, "overall_verdict": "SUPPORTED", "contradiction_found": False},
        max_similarity=0.10,
        auto_threshold=0.30,
    )
    assert required is True
    assert "sensitive_crime_corruption_wrongdoing" in flags
    assert "named_entity_sensitive_context" in flags


def test_single_source_is_advisory_not_hard_block():
    required, flags = mandatory_human_review(
        "The company launched a new product.",
        source_count=1,
        verifier_report={"available": True, "overall_verdict": "SUPPORTED", "contradiction_found": False},
        max_similarity=0.10,
        auto_threshold=0.30,
    )
    assert required is False
    assert "single_source_story" in flags


def test_unavailable_verifier_requires_review():
    required, flags = mandatory_human_review(
        "A major policy was announced today.",
        source_count=2,
        verifier_report={"available": False},
        max_similarity=0.05,
        auto_threshold=0.30,
    )
    assert required is True
    assert "verifier_unavailable" in flags


def test_routine_political_story_does_not_require_review():
    required, flags = mandatory_human_review(
        "The Prime Minister announced a new infrastructure policy ahead of Parliament.",
        source_count=3,
        verifier_report={"available": True, "overall_verdict": "SUPPORTED", "contradiction_found": False},
        max_similarity=0.10,
        auto_threshold=0.30,
    )
    assert required is False
    assert not any(flag.startswith("sensitive_election") for flag in flags)


def test_sensitive_election_story_requires_review():
    required, flags = mandatory_human_review(
        "The opposition alleged vote rigging and election fraud in the constituency.",
        source_count=3,
        verifier_report={"available": True, "overall_verdict": "SUPPORTED", "contradiction_found": False},
        max_similarity=0.10,
        auto_threshold=0.30,
    )
    assert required is True
    assert "sensitive_sensitive_election" in flags
