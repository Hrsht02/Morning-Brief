"""Configurable quality benchmark used for automatic publication and filtering."""
import json
from datetime import datetime
from sqlalchemy.orm import Session
from .. import models
from ..seed import get_setting, set_setting

DEFAULT_MIN_CONFIDENCE = 0.55
DEFAULT_MAX_SIMILARITY = 0.20
VALID_MODES = {"upcoming", "current", "current_and_upcoming"}


def get_benchmark(db: Session) -> dict:
    try:
        min_confidence = float(get_setting(db, "quality_benchmark_min_confidence", str(DEFAULT_MIN_CONFIDENCE)))
    except ValueError:
        min_confidence = DEFAULT_MIN_CONFIDENCE
    try:
        max_similarity = float(get_setting(db, "quality_benchmark_max_similarity", str(DEFAULT_MAX_SIMILARITY)))
    except ValueError:
        max_similarity = DEFAULT_MAX_SIMILARITY
    mode = get_setting(db, "quality_benchmark_apply_mode", "upcoming")
    if mode not in VALID_MODES:
        mode = "upcoming"
    return {
        "min_confidence": max(0.0, min(1.0, min_confidence)),
        "max_similarity": max(0.0, min(1.0, max_similarity)),
        "apply_mode": mode,
    }


def _flag_list(story: models.Story) -> list[str]:
    try:
        raw = json.loads(story.verification_flags or "[]")
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def story_meets_benchmark(story: models.Story, benchmark: dict) -> bool:
    return (
        float(story.confidence_score or 0.0) >= float(benchmark["min_confidence"])
        and float(story.max_source_similarity or 0.0) <= float(benchmark["max_similarity"])
    )


def story_has_safety_block(story: models.Story) -> bool:
    """Never let the quality benchmark bypass a safety/editorial blocking flag."""
    flags = _flag_list(story)
    blocked_prefixes = (
        "blocking_layer:",
        "high_risk_source",
        "near_verbatim_risk",
        "long_phrase_copy_risk",
        "no_citations",
        "low_confidence",
        "sensitive_",
        "compliance_",
        "contradiction",
    )
    return any(str(flag).lower().startswith(blocked_prefixes) for flag in flags) or bool(story.contradiction_flag)


def apply_benchmark_to_current_edition(db: Session, benchmark: dict, edition_date: str) -> dict:
    """Re-evaluate today's already-created stories using stored quality metrics.

    This does not regenerate stories. It only changes publication state when the
    stored confidence/similarity metrics meet the benchmark and no safety block
    is present. Stories that fail remain pending/rejected rather than being
    silently published.
    """
    rows = db.query(models.Story).filter(
        models.Story.edition_date == edition_date,
        models.Story.is_test_content.is_(False),
        models.Story.publication_status.in_(["pending", "approved"]),
    ).all()
    approved = 0
    held = 0
    for story in rows:
        if story_meets_benchmark(story, benchmark) and not story_has_safety_block(story):
            if story.publication_status != "approved":
                story.publication_status = "approved"
                story.is_published = True
                story.needs_review = False
                story.pipeline_stage = "published"
                approved += 1
        elif story.publication_status == "approved":
            # Tightening a benchmark must not silently unpublish already approved
            # editorial decisions. Only pending stories are changed by this action.
            continue
        else:
            story.publication_status = "pending"
            story.is_published = False
            story.needs_review = True
            held += 1
    db.commit()
    return {"edition_date": edition_date, "reviewed": len(rows), "approved": approved, "held_for_review": held}


def save_benchmark(db: Session, min_confidence: float, max_similarity: float, apply_mode: str, edition_date: str | None = None) -> dict:
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("Minimum confidence must be between 0 and 1")
    if not 0.0 <= max_similarity <= 1.0:
        raise ValueError("Maximum similarity must be between 0 and 1")
    if apply_mode not in VALID_MODES:
        raise ValueError("apply_mode must be upcoming, current, or current_and_upcoming")

    set_setting(db, "quality_benchmark_min_confidence", f"{min_confidence:.3f}", "Minimum confidence for automatic publication")
    set_setting(db, "quality_benchmark_max_similarity", f"{max_similarity:.3f}", "Maximum source similarity for automatic publication")
    set_setting(db, "quality_benchmark_apply_mode", apply_mode, "Whether quality benchmark applies to upcoming ingestion, current edition, or both")
    db.commit()

    result = get_benchmark(db)
    if apply_mode in {"current", "current_and_upcoming"} and edition_date:
        result["current_edition"] = apply_benchmark_to_current_edition(db, result, edition_date)
    return result
