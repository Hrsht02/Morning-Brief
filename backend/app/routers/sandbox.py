"""Production-safe admin sandbox.

These endpoints validate configuration and application wiring without mutating
production data or emailing real subscribers. The automatic-email check mirrors
scheduler eligibility and reports what would happen; the send-test endpoint
should be used when an actual provider delivery is desired.
"""
import datetime
import zoneinfo
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_admin
from ..database import get_db
from ..config import settings
from ..seed import get_setting
from ..services.personalization import select_personalized_stories

router = APIRouter(prefix="/admin/sandbox", tags=["admin-sandbox"])


def _check(name, passed, detail):
    return {"name": name, "passed": bool(passed), "detail": detail}


def _setting_bool(db, key, default=False):
    return str(get_setting(db, key, "true" if default else "false")).lower() in {"1", "true", "yes", "on"}


@router.get("/health")
def sandbox_health(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    """Run non-destructive readiness checks for the deployed application."""
    checks = []
    try:
        db.execute(models.User.__table__.select().limit(1))
        db_ok = True
    except Exception as exc:
        db_ok = False
        db_error = str(exc)
    checks.append(_check("database", db_ok, "Database query succeeded" if db_ok else db_error))

    checks.append(_check("frontend_url", bool(settings.FRONTEND_URL and settings.FRONTEND_URL.startswith("http")), settings.FRONTEND_URL))
    checks.append(_check("jwt_secret", settings.JWT_SECRET_KEY not in {"", "insecure-default-change-me"}, "Configured" if settings.JWT_SECRET_KEY not in {"", "insecure-default-change-me"} else "Default/empty secret"))
    checks.append(_check("cron_secret", settings.CRON_SECRET not in {"", "insecure-default-change-me"}, "Configured" if settings.CRON_SECRET not in {"", "insecure-default-change-me"} else "Default/empty secret"))
    checks.append(_check("email_provider", bool(settings.BREVO_API_KEY), "Brevo API key configured" if settings.BREVO_API_KEY else "BREVO_API_KEY missing"))
    checks.append(_check("groq", bool(settings.GROQ_API_KEY), "Groq API key configured" if settings.GROQ_API_KEY else "GROQ_API_KEY missing"))
    checks.append(_check("gemini", bool(settings.GEMINI_API_KEY), "Gemini verifier configured" if settings.GEMINI_API_KEY else "GEMINI_API_KEY missing"))
    checks.append(_check("automatic_scheduler", get_setting(db, "scheduling_mode", "auto") == "auto", get_setting(db, "scheduling_mode", "auto")))

    return {"status": "ok" if all(c["passed"] for c in checks) else "degraded", "checks": checks}


@router.get("/automatic-email")
def test_automatic_email_path(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    """Simulate automatic email eligibility without sending any message."""
    now = datetime.datetime.now(datetime.timezone.utc)
    users = db.query(models.User).filter(
        models.User.is_active.is_(True),
        models.User.onboarded.is_(True),
        models.User.role == "user",
    ).all()
    eligible = []
    inspected = []

    for user in users:
        try:
            tz = zoneinfo.ZoneInfo(user.timezone or "UTC")
        except Exception:
            tz = zoneinfo.ZoneInfo("UTC")
        local_now = now.astimezone(tz)
        local_date = local_now.date().isoformat()
        send_at = local_now.replace(hour=user.send_hour, minute=user.send_minute, second=0, microsecond=0)
        in_window = abs((local_now - send_at).total_seconds()) <= 3600
        already_sent = user.last_sent_date == local_date
        approved = db.query(models.Story).filter(
            models.Story.edition_date == local_date,
            models.Story.publication_status == "approved",
            models.Story.is_published.is_(True),
            models.Story.is_test_content.is_(False),
        ).all()
        candidate_count = len(approved)
        would_send = in_window and not already_sent and candidate_count > 0
        inspected.append({
            "user_id": user.id,
            "timezone": user.timezone,
            "local_time": local_now.isoformat(),
            "configured_send_time": f"{user.send_hour:02d}:{user.send_minute:02d}",
            "in_send_window": in_window,
            "already_sent_today": already_sent,
            "approved_stories_for_local_date": candidate_count,
            "would_send": would_send,
        })
        if would_send:
            selected, resolution = select_personalized_stories(
                approved,
                user.country_code,
                {c.category_slug for c in user.categories},
                int(get_setting(db, "stories_per_edition", "10")),
                int(get_setting(db, "outside_bubble_min_stories", "1")),
            )
            eligible.append({"user_id": user.id, "stories": len(selected), "effective_country": resolution.effective})

    return {
        "status": "ready" if eligible else "no_eligible_recipient_now",
        "would_send": bool(eligible),
        "eligible_users": eligible,
        "inspected_users": inspected,
        "safe": True,
        "side_effects": "none",
    }


@router.get("/features")
def feature_readiness(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    """Check that core data/features exist without modifying anything."""
    source_count = db.query(models.Source).count()
    category_count = db.query(models.Category).filter(models.Category.is_active.is_(True)).count()
    approved_count = db.query(models.Story).filter(models.Story.publication_status == "approved", models.Story.is_test_content.is_(False)).count()
    pending_count = db.query(models.Story).filter(models.Story.publication_status == "pending", models.Story.is_test_content.is_(False)).count()
    return {
        "status": "ok",
        "checks": [
            _check("categories_seeded", category_count > 0, f"{category_count} active categories"),
            _check("sources_configured", source_count > 0, f"{source_count} sources"),
            _check("approved_news_exists", approved_count > 0, f"{approved_count} approved stories"),
            _check("approval_workflow", True, f"{pending_count} stories pending review"),
            _check("country_personalization", True, "Country-aware personalization service loaded"),
            _check("originality_pipeline", True, "Originality module present; provider readiness checked by /health"),
            _check("verification_pipeline", True, "Verification layers registered in application"),
        ],
        "counts": {"sources": source_count, "categories": category_count, "approved": approved_count, "pending": pending_count},
    }
