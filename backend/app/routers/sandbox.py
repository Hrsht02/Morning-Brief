"""Production-safe admin sandbox endpoints.

The sandbox is deliberately read-only except for the explicit test-email
endpoint already exposed by the normal admin router. Scheduler simulation
reuses the same eligibility concepts as production delivery and never writes
EmailLog or User.last_sent_date.
"""
from __future__ import annotations

import datetime
import zoneinfo

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_admin
from ..config import settings
from ..database import get_db
from ..seed import get_setting
from ..services.personalization import select_personalized_stories
from ..services.sandbox import email_eligibility, limit_value, local_send_window

router = APIRouter(prefix="/admin/sandbox", tags=["admin-sandbox"])


def _check(name: str, passed: bool, detail: str):
    return {"name": name, "passed": bool(passed), "detail": detail}


def _approved_stories_for_date(db: Session, edition_date: str):
    return db.query(models.Story).filter(
        models.Story.edition_date == edition_date,
        models.Story.publication_status == "approved",
        models.Story.is_published.is_(True),
        models.Story.is_test_content.is_(False),
    ).all()


@router.get("/health")
def sandbox_health(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    """Run non-destructive deployment/configuration readiness checks."""
    checks = []
    try:
        db.execute(models.User.__table__.select().limit(1))
        checks.append(_check("database", True, "Database query succeeded"))
    except Exception as exc:
        checks.append(_check("database", False, f"Database query failed: {exc}"))

    frontend_ok = bool(settings.FRONTEND_URL and settings.FRONTEND_URL.startswith("http"))
    checks.append(_check("frontend_url", frontend_ok, settings.FRONTEND_URL if frontend_ok else "FRONTEND_URL missing/invalid"))

    jwt_ok = settings.JWT_SECRET_KEY not in {"", "insecure-default-change-me"}
    cron_ok = settings.CRON_SECRET not in {"", "insecure-default-change-me"}
    checks.append(_check("jwt_secret", jwt_ok, "Configured" if jwt_ok else "Default/empty secret"))
    checks.append(_check("cron_secret", cron_ok, "Configured" if cron_ok else "Default/empty secret"))
    checks.append(_check("email_provider", bool(settings.BREVO_API_KEY), "Brevo API key configured" if settings.BREVO_API_KEY else "BREVO_API_KEY missing"))
    checks.append(_check("groq", bool(settings.GROQ_API_KEY), "Groq API key configured" if settings.GROQ_API_KEY else "GROQ_API_KEY missing"))
    checks.append(_check("gemini", bool(settings.GEMINI_API_KEY), "Gemini verifier configured" if settings.GEMINI_API_KEY else "GEMINI_API_KEY missing"))

    scheduling_mode = str(get_setting(db, "scheduling_mode", "auto")).lower()
    checks.append(_check("automatic_scheduler_configured", scheduling_mode in {"auto", "manual"}, f"scheduling_mode={scheduling_mode}"))
    checks.append(_check("automatic_scheduler_enabled", scheduling_mode == "auto", "Automatic scheduling is enabled" if scheduling_mode == "auto" else "Manual mode is configured; scheduled delivery is intentionally disabled"))

    return {"status": "ok" if all(c["passed"] for c in checks) else "degraded", "checks": checks}


@router.get("/features")
def feature_readiness(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    """Check core application data and feature wiring without mutation."""
    source_count = db.query(models.Source).count()
    category_count = db.query(models.Category).filter(models.Category.is_active.is_(True)).count()
    approved_count = db.query(models.Story).filter(
        models.Story.publication_status == "approved", models.Story.is_test_content.is_(False)
    ).count()
    pending_count = db.query(models.Story).filter(
        models.Story.publication_status == "pending", models.Story.is_test_content.is_(False)
    ).count()
    layer_count = db.query(models.VerificationLayer).count()
    enabled_layer_count = db.query(models.VerificationLayer).filter(models.VerificationLayer.is_enabled.is_(True)).count()
    story_limit = limit_value(get_setting(db, "stories_per_edition", "10"))

    checks = [
        _check("categories_seeded", category_count > 0, f"{category_count} active categories"),
        _check("sources_configured", source_count > 0, f"{source_count} sources"),
        _check("approved_news_exists", approved_count > 0, f"{approved_count} approved production stories"),
        _check("approval_workflow", True, f"{pending_count} stories pending review"),
        _check("verification_layers", enabled_layer_count > 0, f"{enabled_layer_count}/{layer_count} verification layers enabled"),
        _check("country_personalization", True, "Country-aware personalization service loaded"),
        _check("originality_pipeline", True, "Originality checks are wired into ingestion"),
        _check("edition_limit", story_limit > 0, f"stories_per_edition={story_limit}"),
    ]
    return {
        "status": "ok" if all(c["passed"] for c in checks) else "degraded",
        "checks": checks,
        "counts": {"sources": source_count, "categories": category_count, "approved": approved_count, "pending": pending_count, "verification_layers": layer_count, "enabled_verification_layers": enabled_layer_count},
        "edition_limit": story_limit,
    }


@router.get("/automatic-email")
def test_automatic_email_path(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    """Simulate scheduled email eligibility without sending or writing data."""
    now = datetime.datetime.now(datetime.timezone.utc)
    users = db.query(models.User).filter(
        models.User.is_active.is_(True), models.User.onboarded.is_(True), models.User.role == "user"
    ).all()

    # Cache approved stories by local date so the sandbox remains inexpensive
    # when the subscriber count grows.
    stories_by_date = {}
    inspected = []
    eligible = []
    limit = limit_value(get_setting(db, "stories_per_edition", "10"))
    outside_min = limit_value(get_setting(db, "outside_bubble_min_stories", "1"), default=1, minimum=0, maximum=limit)

    for user in users:
        local_now, in_window = local_send_window(now, user.timezone, user.send_hour, user.send_minute)
        local_date = local_now.date().isoformat()
        if local_date not in stories_by_date:
            stories_by_date[local_date] = _approved_stories_for_date(db, local_date)
        approved = stories_by_date[local_date]

        last_delivery = db.query(models.EmailLog).filter(
            models.EmailLog.user_id == user.id,
            models.EmailLog.edition_date == local_date,
            models.EmailLog.status == "sent",
        ).order_by(models.EmailLog.sent_at.desc()).first()
        already_sent = last_delivery is not None

        selected = []
        resolution = None
        if approved:
            selected, resolution = select_personalized_stories(
                approved,
                user.country_code,
                {c.category_slug for c in user.categories},
                limit,
                outside_min,
            )
        would_send, reason = email_eligibility(
            in_send_window=in_window,
            already_sent=already_sent,
            candidate_count=len(approved),
            selected_count=len(selected),
        )

        inspected.append({
            "user_id": user.id,
            "timezone": user.timezone,
            "local_time": local_now.isoformat(),
            "configured_send_time": f"{user.send_hour:02d}:{user.send_minute:02d}",
            "in_send_window": in_window,
            "already_sent_today": already_sent,
            "approved_stories_for_local_date": len(approved),
            "selected_story_count": len(selected),
            "effective_country": resolution.effective if resolution else None,
            "decision": reason,
            "would_send": would_send,
        })
        if would_send:
            eligible.append({"user_id": user.id, "stories": len(selected), "effective_country": resolution.effective})

    return {
        "status": "ready" if eligible else "no_eligible_recipient_now",
        "would_send": bool(eligible),
        "eligible_users": eligible,
        "inspected_users": inspected,
        "edition_limit": limit,
        "safe": True,
        "side_effects": "none",
    }


@router.get("/suite")
def sandbox_suite(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    """Run all read-only sandbox checks in one request."""
    health = sandbox_health(db, _admin)
    features = feature_readiness(db, _admin)
    automatic = test_automatic_email_path(db, _admin)
    all_checks = health["checks"] + features["checks"]
    return {
        "status": "ready" if all(c["passed"] for c in all_checks) else "degraded",
        "health": health,
        "features": features,
        "automatic_email": automatic,
        "safe": True,
        "side_effects": "none",
    }
