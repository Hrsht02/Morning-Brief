"""Read-only diagnostics and explicitly safe test controls.

Designed as a narrow interface for an external operator such as a private
ChatGPT integration. Never expose secrets or arbitrary database operations.
"""
from __future__ import annotations

import datetime
import zoneinfo
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..seed import get_setting
from .. import models
from ..email_service.sender import _get_approved_stories_for_edition, _get_latest_approved_edition_date
from ..services.test_scheduler import schedule_test_email, get_test_schedule, cancel_test_email

router = APIRouter(prefix="/admin/diagnostics", tags=["diagnostics"])


def _guard(x_admin_diagnostics_key: str | None = Header(default=None)):
    expected = getattr(settings, "ADMIN_DIAGNOSTICS_KEY", None)
    if not expected or not x_admin_diagnostics_key or x_admin_diagnostics_key != expected:
        raise HTTPException(status_code=401, detail="Diagnostics authentication required")


class ScheduleRequest(BaseModel):
    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)


@router.get("/health", dependencies=[Depends(_guard)])
def diagnostic_health(db: Session = Depends(get_db)):
    db_ok = True
    try:
        db.execute(models.select_one()) if hasattr(models, "select_one") else db.query(models.User).limit(1).all()
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "brevo_configured": bool(settings.BREVO_API_KEY and settings.EMAIL_FROM_ADDRESS),
        "frontend_configured": bool(settings.FRONTEND_URL),
        "scheduler_mode": get_setting(db, "scheduling_mode", "auto"),
    }


@router.get("/email", dependencies=[Depends(_guard)])
def diagnostic_email(db: Session = Depends(get_db)):
    today = datetime.date.today()
    latest = _get_latest_approved_edition_date(db, today)
    stories = _get_approved_stories_for_edition(db, latest) if latest else []
    return {
        "brevo_configured": bool(settings.BREVO_API_KEY and settings.EMAIL_FROM_ADDRESS),
        "test_recipient_configured": bool(get_setting(db, "developer_test_email", "").strip()),
        "latest_approved_edition": latest,
        "approved_story_count": len(stories),
        "stories_per_edition": int(get_setting(db, "stories_per_edition", "8")),
        "scheduled_test": get_test_schedule(db),
    }


@router.get("/scheduler", dependencies=[Depends(_guard)])
def diagnostic_scheduler(db: Session = Depends(get_db)):
    return {
        "mode": get_setting(db, "scheduling_mode", "auto"),
        "scheduled_test": get_test_schedule(db),
        "workflow_expected_frequency": "5 minutes",
    }


@router.post("/test-email/schedule", dependencies=[Depends(_guard)])
def schedule_test(request: ScheduleRequest, db: Session = Depends(get_db)):
    return schedule_test_email(db, request.hour, request.minute)


@router.post("/test-email/cancel", dependencies=[Depends(_guard)])
def cancel_test(db: Session = Depends(get_db)):
    return cancel_test_email(db)


@router.get("/test-email", dependencies=[Depends(_guard)])
def scheduled_test_status(db: Session = Depends(get_db)):
    return get_test_schedule(db)
