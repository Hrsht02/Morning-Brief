"""One-shot safe email scheduler used only by the production sandbox."""
from __future__ import annotations
import datetime
import zoneinfo
from sqlalchemy.orm import Session
from ..seed import get_setting, set_setting
from ..email_service.sender import send_test_email

SCHEDULED_AT_KEY = "sandbox_test_email_scheduled_at"
SCHEDULED_ENABLED_KEY = "sandbox_test_email_enabled"
LAST_RESULT_KEY = "sandbox_test_email_last_result"


def _parse_target(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        target = datetime.datetime.fromisoformat(value)
        if target.tzinfo is None:
            target = target.replace(tzinfo=datetime.timezone.utc)
        return target.astimezone(datetime.timezone.utc)
    except ValueError:
        return None


def schedule_test_email(db: Session, hour: int, minute: int) -> dict:
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Time must be in 24-hour HH:MM format")
    recipient = get_setting(db, "developer_test_email", "").strip()
    if not recipient:
        return {"status": "failed", "detail": "developer_test_email is not configured", "safe": True}
    timezone_name = get_setting(db, "admin_timezone", "Asia/Kolkata")
    try:
        tz = zoneinfo.ZoneInfo(timezone_name)
    except Exception:
        timezone_name = "Asia/Kolkata"
        tz = zoneinfo.ZoneInfo(timezone_name)
    now = datetime.datetime.now(tz)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    target_utc = target.astimezone(datetime.timezone.utc)
    set_setting(db, SCHEDULED_AT_KEY, target_utc.isoformat())
    set_setting(db, SCHEDULED_ENABLED_KEY, "true")
    set_setting(db, LAST_RESULT_KEY, "")
    db.commit()
    return {"status": "scheduled", "scheduled_at": target.isoformat(), "scheduled_at_utc": target_utc.isoformat(), "timezone": timezone_name, "recipient": recipient, "safe": True, "one_shot": True}


def get_test_schedule(db: Session) -> dict:
    return {"enabled": get_setting(db, SCHEDULED_ENABLED_KEY, "false").lower() == "true", "scheduled_at": get_setting(db, SCHEDULED_AT_KEY, "") or None, "last_result": get_setting(db, LAST_RESULT_KEY, "") or None, "recipient_configured": bool(get_setting(db, "developer_test_email", "").strip()), "safe": True, "one_shot": True}


def cancel_test_email(db: Session) -> dict:
    set_setting(db, SCHEDULED_ENABLED_KEY, "false")
    set_setting(db, SCHEDULED_AT_KEY, "")
    db.commit()
    return {"status": "cancelled", "safe": True}


def run_due_test_email(db: Session, now_utc: datetime.datetime | None = None) -> dict:
    if get_setting(db, SCHEDULED_ENABLED_KEY, "false").lower() != "true":
        return {"status": "idle", "sent": False, "safe": True}
    target = _parse_target(get_setting(db, SCHEDULED_AT_KEY, ""))
    if target is None:
        return {"status": "failed", "sent": False, "detail": "Invalid scheduled test-email time", "safe": True}
    now = now_utc or datetime.datetime.now(datetime.timezone.utc)
    if now < target:
        return {"status": "waiting", "sent": False, "scheduled_at": target.isoformat(), "safe": True}
    recipient = get_setting(db, "developer_test_email", "").strip()
    if not recipient:
        set_setting(db, SCHEDULED_ENABLED_KEY, "false")
        set_setting(db, SCHEDULED_AT_KEY, "")
        set_setting(db, LAST_RESULT_KEY, "failed: developer_test_email is not configured")
        db.commit()
        return {"status": "failed", "sent": False, "detail": "developer_test_email is not configured", "safe": True}
    try:
        result = send_test_email(db, recipient)
        success = result.get("status") == "completed"
        final_status = "completed" if success else "failed"
        set_setting(db, SCHEDULED_ENABLED_KEY, "false")
        set_setting(db, SCHEDULED_AT_KEY, "")
        set_setting(db, LAST_RESULT_KEY, f"{final_status}: {result.get('detail', '')}")
        db.commit()
        return {"status": final_status, "sent": success, "result": result, "safe": True, "one_shot": True}
    except Exception as exc:
        set_setting(db, SCHEDULED_ENABLED_KEY, "false")
        set_setting(db, SCHEDULED_AT_KEY, "")
        set_setting(db, LAST_RESULT_KEY, f"failed: {str(exc)[:500]}")
        db.commit()
        return {"status": "failed", "sent": False, "detail": str(exc)[:500], "safe": True}
