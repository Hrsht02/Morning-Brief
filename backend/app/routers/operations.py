"""Read-only operational and editorial management endpoints."""
import datetime
import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from .. import models, schemas
from ..auth import get_current_admin, get_current_developer_or_admin
from ..database import get_db
from ..seed import get_setting
from ..services.personalization import SUPPORTED_COUNTRIES

router = APIRouter(prefix="/admin", tags=["admin/operations"])


@router.get("/stories/approved", response_model=list[schemas.StoryOut])
def approved_stories(limit: int = 200, db: Session = Depends(get_db), _=Depends(get_current_developer_or_admin)):
    """All approved production news, not only today's queue."""
    limit = max(1, min(limit, 1000))
    return db.query(models.Story).options(joinedload(models.Story.citations)).filter(
        models.Story.publication_status == "approved", models.Story.is_published.is_(True), models.Story.is_test_content.is_(False)
    ).order_by(models.Story.edition_date.desc(), models.Story.is_pinned.desc(), models.Story.created_at.desc()).limit(limit).all()


@router.get("/countries", response_model=dict)
def countries(db: Session = Depends(get_db), _=Depends(get_current_developer_or_admin)):
    users = db.query(models.User).filter(models.User.role == "user").all()
    stories = db.query(models.Story).filter(models.Story.is_test_content.is_(False)).all()
    return {
        "supported": [{"code": c, "name": n} for c, n in SUPPORTED_COUNTRIES.items() if c != "GLOBAL"],
        "fallback": "GLOBAL",
        "default": "IN",
        "users_by_country": {c: sum(1 for u in users if u.country_code == c) for c in SUPPORTED_COUNTRIES if c != "GLOBAL"},
        "stories_by_country": {c: sum(1 for s in stories if s.country_code == c) for c in SUPPORTED_COUNTRIES},
    }


@router.get("/jobs", response_model=dict)
def job_status(db: Session = Depends(get_db), _=Depends(get_current_developer_or_admin)):
    raw = get_setting(db, "ingestion_last_result", "")
    try: last_result = json.loads(raw) if raw else None
    except json.JSONDecodeError: last_result = None
    return {
        "ingestion": {
            "status": get_setting(db, "ingestion_status", "idle"),
            "started_at": get_setting(db, "ingestion_started_at", ""),
            "completed_at": get_setting(db, "ingestion_completed_at", ""),
            "last_result": last_result,
        },
        "schedule": {
            "mode": get_setting(db, "scheduling_mode", "auto"),
            "admin_timezone": get_setting(db, "admin_timezone", "Asia/Kolkata"),
            "email_window": [get_setting(db, "email_send_window_start", "06:00"), get_setting(db, "email_send_window_end", "07:00")],
        },
    }


@router.get("/health/details", response_model=dict)
def detailed_health(db: Session = Depends(get_db), _=Depends(get_current_developer_or_admin)):
    now = datetime.datetime.utcnow().isoformat()
    return {
        "status": "ok",
        "checked_at": now,
        "database": "ok",
        "groq_configured": bool(__import__("app.config", fromlist=["settings"]).settings.GROQ_API_KEY),
        "gemini_configured": bool(__import__("app.config", fromlist=["settings"]).settings.GEMINI_API_KEY),
        "brevo_configured": bool(__import__("app.config", fromlist=["settings"]).settings.BREVO_API_KEY),
    }
