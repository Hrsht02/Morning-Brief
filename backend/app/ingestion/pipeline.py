"""Full production ingestion: fetch -> cluster -> Groq draft -> originality -> verification -> publication gate."""
import datetime
import json
import logging
import time
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import SessionLocal
from ..seed import get_setting, set_setting
from .rss_fetcher import fetch_all_active_sources
from .clustering import cluster_articles
from .verification_layers import run_verification_pipeline
from ..llm.groq_client import summarize_cluster
from ..llm.originality import rewrite_for_originality

logger = logging.getLogger("morning_brief.pipeline")


def _edition_date(db: Session) -> str:
    tz_name = get_setting(db, "admin_timezone", "Asia/Kolkata")
    try: tz = ZoneInfo(tz_name)
    except Exception: tz = ZoneInfo("Asia/Kolkata")
    return datetime.datetime.now(tz).date().isoformat()


def run_ingestion(db: Session, test_mode: bool = False, max_clusters: int = None) -> dict:
    today = _edition_date(db)
    similarity_threshold = float(get_setting(db, "cluster_similarity_threshold", "0.35"))
    max_sentences = int(get_setting(db, "summary_max_sentences", "3"))
    require_human_approval_all = get_setting(db, "require_human_approval_all", "true").lower() == "true"
    skip_all_verification = get_setting(db, "skip_all_verification", "false").lower() == "true"
    bilingual_generation = get_setting(db, "bilingual_generation", "true").lower() == "true"
    blocked_domains = {d.strip().lower() for d in get_setting(db, "blocked_source_domains", "").split(",") if d.strip()}
    thresholds = {
        "near_verbatim_similarity_threshold": float(get_setting(db, "near_verbatim_similarity_threshold", "0.55")),
        "long_phrase_overlap_threshold": float(get_setting(db, "long_phrase_overlap_threshold", "0.20")),
        "long_phrase_words": int(get_setting(db, "long_phrase_words", "6")),
        "min_confidence_score": float(get_setting(db, "min_confidence_score", "0.55")),
    }
    category_slugs = [c.slug for c in db.query(models.Category).filter(models.Category.is_active.is_(True)).all()] or ["general"]
    enabled_layers = db.query(models.VerificationLayer).filter(models.VerificationLayer.is_enabled.is_(True)).order_by(models.VerificationLayer.sort_order).all()

    try:
        articles = fetch_all_active_sources(db, blocked_domains=blocked_domains)
    except Exception as exc:
        logger.exception("Fetch stage failed: %s", exc)
        return {"status": "error", "detail": str(exc), "stories_created": 0}
    if not articles:
        return {"status": "ok", "detail": "No articles fetched (check source feeds)", "stories_created": 0}

    clusters = cluster_articles(articles, similarity_threshold=similarity_threshold)
    if test_mode: clusters = clusters[: (max_clusters or 3)]

    if not test_mode:
        db.query(models.Story).filter(
            models.Story.edition_date == today,
            models.Story.is_pinned.is_(False),
            models.Story.publication_status != "approved",
            models.Story.is_test_content.is_(False),
        ).delete(synchronize_session=False)
        db.commit()

    stories_created = 0
    rewrite_threshold = float(get_setting(db, "originality_rewrite_trigger_threshold", "0.35"))
    for i, cluster in enumerate(clusters):
        snippets = [{"title": a.title, "summary": a.summary, "source": a.source_name} for a in cluster.articles]
        try:
            draft = summarize_cluster(snippets, category_slugs, max_sentences=max_sentences, bilingual=bilingual_generation)
        except Exception as exc:
            logger.exception("Summarization failed; skipping cluster: %s", exc)
            continue

        original_snippets = [f"{a.title} {a.summary}" for a in cluster.articles]
        rewrite_applied = False
        try:
            # Rewrite only when deterministic similarity indicates meaningful
            # overlap. This keeps normal ingestion within the free-tier budget.
            from .verification import compute_max_similarity
            initial_similarity = compute_max_similarity(draft["summary"], original_snippets)
            if initial_similarity >= rewrite_threshold and not skip_all_verification:
                rewritten = rewrite_for_originality(draft["summary"], original_snippets, max_sentences)
                if rewritten and rewritten != draft["summary"]:
                    draft["summary"] = rewritten
                    rewrite_applied = True
        except Exception as exc:
            logger.warning("Originality pre-check failed: %s", exc)

        if skip_all_verification:
            flags, publication_status, is_published = [], "approved", True
            max_similarity, max_long_phrase, verifier_report = 0.0, 0.0, None
        else:
            context = {"cluster_articles": cluster.articles, "draft": draft, "original_snippets": original_snippets,
                       "thresholds": thresholds, "blocked_domains": blocked_domains}
            result = run_verification_pipeline(enabled_layers, context)
            flags = result["all_flags"]
            max_similarity = context.get("max_similarity", 0.0)
            max_long_phrase = context.get("max_long_phrase_overlap", 0.0)
            verifier_report = context.get("verifier_report")
            if result["must_hold"] or flags or require_human_approval_all:
                publication_status, is_published = "pending", False
            else:
                publication_status, is_published = "approved", True

        # A cluster with mixed sources is classified GLOBAL; a single-country
        # cluster inherits that source country. This is conservative and avoids
        # incorrectly labeling an international story as local.
        countries = {getattr(a, "country_code", "GLOBAL") for a in cluster.articles}
        country_code = next(iter(countries)) if len(countries) == 1 else "GLOBAL"
        story = models.Story(
            edition_date=today, headline=draft["headline"], hook=draft["hook"], summary=draft["summary"],
            headline_hi=draft.get("headline_hi"), hook_hi=draft.get("hook_hi"), summary_hi=draft.get("summary_hi"),
            category_slug=draft["category_slug"], country_code=country_code, confidence_score=draft["confidence"],
            needs_review=bool(flags), is_published=is_published, is_test_content=test_mode,
            publication_status=publication_status,
            pipeline_stage="pending_human_review" if publication_status == "pending" else "published",
            verification_flags=json.dumps(flags) if flags else None, max_source_similarity=max_similarity,
            max_long_phrase_overlap=max_long_phrase, originality_rewrite_applied=rewrite_applied,
            generator_model=f"groq:{settings.GROQ_MODEL}",
            verifier_model=f"gemini:{settings.GEMINI_MODEL}" if verifier_report else None,
            verifier_report=json.dumps(verifier_report) if verifier_report else None,
            contradiction_flag=bool(verifier_report and verifier_report.get("contradiction_found")),
            citation_complete=len(cluster.articles) > 0,
        )
        db.add(story); db.flush()
        seen_urls = set()
        for article in cluster.articles:
            if article.link in seen_urls: continue
            seen_urls.add(article.link)
            db.add(models.Citation(story_id=story.id, source_name=article.source_name, title=article.title, url=article.link))
        stories_created += 1
        if not test_mode and i < len(clusters) - 1: time.sleep(7)

    db.commit()
    return {"status": "ok", "detail": f"Processed {len(clusters)} clusters", "stories_created": stories_created}


def run_ingestion_background():
    db = SessionLocal()
    try:
        if get_setting(db, "ingestion_status", "idle") == "running":
            return
        set_setting(db, "ingestion_status", "running", "Current background ingestion status")
        set_setting(db, "ingestion_started_at", datetime.datetime.utcnow().isoformat())
        db.commit()
        result = run_ingestion(db, test_mode=False)
        set_setting(db, "ingestion_status", "idle")
        set_setting(db, "ingestion_last_result", json.dumps(result))
        set_setting(db, "ingestion_completed_at", datetime.datetime.utcnow().isoformat())
        db.commit()
    except Exception as exc:
        logger.exception("Background ingestion crashed: %s", exc)
        set_setting(db, "ingestion_status", "error")
        set_setting(db, "ingestion_last_result", json.dumps({"status":"error","detail":str(exc)[:500]}))
        db.commit()
    finally:
        db.close()
