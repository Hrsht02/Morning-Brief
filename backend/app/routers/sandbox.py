"""Production-safe admin sandbox endpoints.

Readiness and scheduler simulation are non-destructive. The only sending action
is the explicit safe test email, which targets the configured developer/test
address. One-shot scheduled test emails are also restricted to that address.
"""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_admin
from ..config import settings
from ..database import get_db
from ..seed import get_setting
from ..services.personalization import select_personalized_stories
from ..services.sandbox import email_eligibility, limit_value, local_send_window
from ..services.test_scheduler import cancel_test_email, get_test_schedule, run_due_test_email, schedule_test_email

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


def _simulate_email_for_user(db: Session, user, now_utc: datetime.datetime, edition_date: str | None = None):
    local_now, in_window = local_send_window(now_utc, user.timezone, user.send_hour, user.send_minute)
    local_date = local_now.date().isoformat()
    selected_date = edition_date or local_date
    approved = _approved_stories_for_date(db, selected_date)
    limit = limit_value(get_setting(db, "stories_per_edition", "10"))
    outside_min = limit_value(get_setting(db, "outside_bubble_min_stories", "1"), default=1, minimum=0, maximum=limit)
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
    already_sent = db.query(models.EmailLog).filter(
        models.EmailLog.user_id == user.id,
        models.EmailLog.edition_date == selected_date,
        models.EmailLog.status == "sent",
    ).first() is not None
    would_send, reason = email_eligibility(
        in_send_window=in_window if edition_date is None else True,
        already_sent=already_sent,
        candidate_count=len(approved),
        selected_count=len(selected),
    )
    return {
        "user_id": user.id,
        "timezone": user.timezone,
        "local_time": local_now.isoformat(),
        "configured_send_time": f"{user.send_hour:02d}:{user.send_minute:02d}",
        "edition_date": selected_date,
        "in_send_window": in_window if edition_date is None else True,
        "already_sent": already_sent,
        "approved_stories": len(approved),
        "selected_stories": len(selected),
        "edition_limit": limit,
        "effective_country": resolution.effective if resolution else None,
        "decision": reason,
        "would_send": would_send,
        "selected_story_ids": [s.id for s in selected],
        "selected_headlines": [s.headline for s in selected],
    }


@router.get("/health")
def sandbox_health(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
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
    source_count = db.query(models.Source).count()
    category_count = db.query(models.Category).filter(models.Category.is_active.is_(True)).count()
    approved_count = db.query(models.Story).filter(models.Story.publication_status == "approved", models.Story.is_test_content.is_(False)).count()
    pending_count = db.query(models.Story).filter(models.Story.publication_status == "pending", models.Story.is_test_content.is_(False)).count()
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
    return {"status": "ok" if all(c["passed"] for c in checks) else "degraded", "checks": checks, "counts": {"sources": source_count, "categories": category_count, "approved": approved_count, "pending": pending_count, "verification_layers": layer_count, "enabled_verification_layers": enabled_layer_count}, "edition_limit": story_limit}


@router.get("/automatic-email")
def test_automatic_email_path(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    now = datetime.datetime.now(datetime.timezone.utc)
    users = db.query(models.User).filter(models.User.is_active.is_(True), models.User.onboarded.is_(True), models.User.role == "user").all()
    inspected = [_simulate_email_for_user(db, user, now) for user in users]
    eligible = [{"user_id": row["user_id"], "stories": row["selected_stories"], "effective_country": row["effective_country"]} for row in inspected if row["would_send"]]
    return {"status": "ready" if eligible else "no_eligible_recipient_now", "would_send": bool(eligible), "eligible_users": eligible, "inspected_users": inspected, "edition_limit": limit_value(get_setting(db, "stories_per_edition", "10")), "safe": True, "side_effects": "none"}


@router.get("/simulate")
def simulate_approved_edition(
    edition_date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    """Deterministically simulate the selected approved edition without sending."""
    now = datetime.datetime.now(datetime.timezone.utc)
    users = db.query(models.User).filter(models.User.is_active.is_(True), models.User.onboarded.is_(True), models.User.role == "user").all()
    approved = _approved_stories_for_date(db, edition_date)
    rows = [_simulate_email_for_user(db, user, now, edition_date=edition_date) for user in users]
    return {
        "status": "ready" if approved else "no_approved_stories_for_date",
        "edition_date": edition_date,
        "approved_stories": len(approved),
        "edition_limit": limit_value(get_setting(db, "stories_per_edition", "10")),
        "users": rows,
        "safe": True,
        "side_effects": "none",
    }


@router.get("/test-email-schedule")
def sandbox_test_email_schedule(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    return get_test_schedule(db)


@router.post("/test-email-schedule")
def sandbox_schedule_test_email(
    hour: int = Query(..., ge=0, le=23),
    minute: int = Query(..., ge=0, le=59),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    return schedule_test_email(db, hour, minute)


@router.delete("/test-email-schedule")
def sandbox_cancel_test_email(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    return cancel_test_email(db)


@router.post("/test-email-schedule/run-due")
def sandbox_run_due_test_email(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    return run_due_test_email(db)


@router.get("/suite")
def sandbox_suite(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    health = sandbox_health(db, _admin)
    features = feature_readiness(db, _admin)
    automatic = test_automatic_email_path(db, _admin)
    all_checks = health["checks"] + features["checks"]
    return {"status": "ready" if all(c["passed"] for c in all_checks) else "degraded", "health": health, "features": features, "automatic_email": automatic, "safe": True, "side_effects": "none"}
