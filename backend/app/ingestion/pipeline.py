"""
Orchestrates one full ingestion run: fetch RSS -> cluster -> generate a draft
with LLM #1 (Groq) -> run every ENABLED verification layer (as configured in
the verification_layers table - nothing here is hardcoded) -> decide
pending/approved -> store as Story + Citation rows.

Three settings control the overall strictness, all admin-editable, none
hardcoded:
  - skip_all_verification: if true, NOTHING is checked and every story
    auto-approves immediately. An explicit, deliberate admin choice.
  - require_human_approval_all: if true (default), even a story that passes
    every enabled layer still waits for a human click before publishing.
  - Per-layer is_enabled / is_blocking: full control over which checks run
    and whether a failure actually blocks publication or is just advisory.

Re-running this for the same day is safe: it replaces today's auto-generated
(not-yet-approved-and-locked) stories rather than duplicating them. Anything
an admin has already approved or pinned is left untouched.
"""
import datetime
import json
import logging
import time
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import SessionLocal
from ..seed import get_setting, set_setting
from .rss_fetcher import fetch_all_active_sources
from .clustering import cluster_articles
from .verification_layers import run_verification_pipeline
from ..llm.groq_client import summarize_cluster

logger = logging.getLogger("morning_brief.pipeline")


def run_ingestion(db: Session, test_mode: bool = False, max_clusters: int = None) -> dict:
    """
    test_mode: when True, generated stories are tagged is_test_content=True
    (never shown to real users regardless of approval status) and processing
    is capped to a small number of clusters, for fast, safe experimentation.
    Used by the developer sandbox (/api/v1/test/*) - never by the real
    scheduled/admin production ingestion.
    """
    today = datetime.date.today().isoformat()

    similarity_threshold = float(get_setting(db, "cluster_similarity_threshold", "0.35"))
    max_sentences = int(get_setting(db, "summary_max_sentences", "3"))
    require_human_approval_all = get_setting(db, "require_human_approval_all", "true").lower() == "true"
    skip_all_verification = get_setting(db, "skip_all_verification", "false").lower() == "true"
    bilingual_generation = get_setting(db, "bilingual_generation", "true").lower() == "true"
    blocked_domains = {
        d.strip().lower() for d in get_setting(db, "blocked_source_domains", "").split(",") if d.strip()
    }
    thresholds = {
        "near_verbatim_similarity_threshold": float(get_setting(db, "near_verbatim_similarity_threshold", "0.55")),
        "min_confidence_score": float(get_setting(db, "min_confidence_score", "0.55")),
    }

    category_slugs = [c.slug for c in db.query(models.Category).filter(models.Category.is_active.is_(True)).all()]
    if not category_slugs:
        category_slugs = ["general"]

    enabled_layers = db.query(models.VerificationLayer).filter(
        models.VerificationLayer.is_enabled.is_(True)
    ).order_by(models.VerificationLayer.sort_order).all()

    # 1. Fetch (blocked-domain safety net is enforced INSIDE fetch_all_active_sources,
    #    so a risky source never even gets its articles pulled, let alone summarized)
    try:
        articles = fetch_all_active_sources(db, blocked_domains=blocked_domains)
    except Exception as e:
        logger.error(f"Ingestion aborted - fetch stage failed entirely: {e}")
        return {"status": "error", "detail": str(e), "stories_created": 0}

    if not articles:
        return {"status": "ok", "detail": "No articles fetched (check source feeds)", "stories_created": 0}

    # 2. Cluster
    clusters = cluster_articles(articles, similarity_threshold=similarity_threshold)
    if test_mode:
        clusters = clusters[: (max_clusters or 3)]  # keep sandbox runs fast and cheap

    # 3. Remove today's PREVIOUSLY auto-generated, not-yet-approved stories before
    #    regenerating (anything already approved or pinned by an admin is left alone).
    #    Test-mode runs never touch real production rows at all.
    if not test_mode:
        db.query(models.Story).filter(
            models.Story.edition_date == today,
            models.Story.is_pinned.is_(False),
            models.Story.publication_status != "approved",
            models.Story.is_test_content.is_(False),
        ).delete(synchronize_session=False)
        db.commit()

    stories_created = 0
    for i, cluster in enumerate(clusters):
        snippets = [
            {"title": a.title, "summary": a.summary, "source": a.source_name}
            for a in cluster.articles
        ]
        try:
            draft = summarize_cluster(snippets, category_slugs, max_sentences=max_sentences, bilingual=bilingual_generation)
        except Exception as e:
            logger.error(f"Unexpected error summarizing a cluster, skipping it: {e}")
            continue

        original_snippets = [f"{a.title} {a.summary}" for a in cluster.articles]

        if skip_all_verification:
            # Explicit admin choice: publish immediately, no checks at all.
            # Still logged clearly so this is never a silent/accidental state.
            flags, publication_status, is_published = [], "approved", True
            max_similarity, verifier_report = 0.0, None
            logger.info(f"Story '{draft['headline'][:50]}...' auto-published - skip_all_verification is ON")
        else:
            context = {
                "cluster_articles": cluster.articles,
                "draft": draft,
                "original_snippets": original_snippets,
                "thresholds": thresholds,
                "blocked_domains": blocked_domains,
            }
            pipeline_result = run_verification_pipeline(enabled_layers, context)
            flags = pipeline_result["all_flags"]
            max_similarity = context.get("max_similarity", 0.0)
            verifier_report = context.get("verifier_report")

            if pipeline_result["must_hold"] or flags or require_human_approval_all:
                publication_status, is_published = "pending", False
            else:
                publication_status, is_published = "approved", True

        story = models.Story(
            edition_date=today,
            headline=draft["headline"],
            hook=draft["hook"],
            summary=draft["summary"],
            headline_hi=draft.get("headline_hi"),
            hook_hi=draft.get("hook_hi"),
            summary_hi=draft.get("summary_hi"),
            category_slug=draft["category_slug"],
            confidence_score=draft["confidence"],
            needs_review=bool(flags),
            is_published=is_published,
            is_test_content=test_mode,
            publication_status=publication_status,
            pipeline_stage="pending_human_review" if publication_status == "pending" else "published",
            verification_flags=json.dumps(flags) if flags else None,
            max_source_similarity=max_similarity,
            generator_model=f"groq:{settings.GROQ_MODEL}",
            verifier_model=f"gemini:{settings.GEMINI_MODEL}" if verifier_report else None,
            verifier_report=json.dumps(verifier_report) if verifier_report else None,
            contradiction_flag=bool(verifier_report and verifier_report.get("contradiction_found")),
            citation_complete=len(cluster.articles) > 0,
        )
        db.add(story)
        db.flush()  # get story.id before adding citations

        seen_urls = set()
        for article in cluster.articles:
            if article.link in seen_urls:
                continue
            seen_urls.add(article.link)
            db.add(models.Citation(
                story_id=story.id,
                source_name=article.source_name,
                title=article.title,
                url=article.link,
            ))

        stories_created += 1

        # Groq's free tier for gpt-oss models caps at 8,000 TOKENS per minute -
        # pacing at ~7s/call keeps us under that budget instead of bursting
        # into repeated 429s after only ~8 calls. Skipped in test mode since
        # those runs are intentionally tiny (a handful of clusters).
        if not test_mode and i < len(clusters) - 1:
            time.sleep(7)

    db.commit()
    logger.info(f"Ingestion complete for {today}: {stories_created} stories from {len(clusters)} clusters (test_mode={test_mode})")
    return {"status": "ok", "detail": f"Processed {len(clusters)} clusters", "stories_created": stories_created}


def run_ingestion_background():
    """
    Entry point for running PRODUCTION ingestion as a FastAPI background task,
    OUTSIDE the lifecycle of any single HTTP request - see the module docstring
    in the original version of this file for why (Groq pacing makes a full run
    take minutes, longer than most free hosts' own request timeout).

    Opens its OWN database session and writes progress to the settings table so
    the admin panel can poll for completion instead of holding a connection open.
    """
    db = SessionLocal()
    try:
        set_setting(db, "ingestion_status", "running", "Current background ingestion status")
        db.commit()

        result = run_ingestion(db, test_mode=False)

        set_setting(db, "ingestion_status", "idle")
        set_setting(db, "ingestion_last_result", json.dumps(result))
        db.commit()
    except Exception as e:
        logger.exception(f"Background ingestion run crashed: {e}")
        set_setting(db, "ingestion_status", "error")
        set_setting(db, "ingestion_last_result", json.dumps({"status": "error", "detail": str(e)[:500]}))
        db.commit()
    finally:
        db.close()
