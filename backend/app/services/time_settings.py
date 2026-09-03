"""Centralized timezone and schedule helpers."""
import datetime
import json
import zoneinfo
from sqlalchemy.orm import Session
from ..seed import get_setting

DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_EMAIL_TIME = "06:00"


def parse_hhmm(value: str, default: str = DEFAULT_EMAIL_TIME) -> tuple[int, int]:
    try:
        hour, minute = (int(part) for part in str(value).strip().split(":", 1))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except (TypeError, ValueError):
        pass
    hour, minute = (int(part) for part in default.split(":", 1))
    return hour, minute


def admin_timezone(db: Session):
    name = get_setting(db, "admin_timezone", DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE
    try:
        return zoneinfo.ZoneInfo(name)
    except Exception:
        return zoneinfo.ZoneInfo(DEFAULT_TIMEZONE)


def configured_email_time(db: Session) -> tuple[int, int]:
    """Return the production schedule time; legacy settings are fallback only."""
    raw = get_setting(db, "production_email_schedule", "")
    if raw:
        try:
            schedule = json.loads(raw)
            return parse_hhmm(schedule.get("time", DEFAULT_EMAIL_TIME))
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return parse_hhmm(get_setting(db, "email_send_time", DEFAULT_EMAIL_TIME))


def is_exact_minute(db: Session, now_utc: datetime.datetime | None = None) -> bool:
    tz = admin_timezone(db)
    now = (now_utc or datetime.datetime.now(datetime.timezone.utc)).astimezone(tz)
    hour, minute = configured_email_time(db)
    return now.hour == hour and now.minute == minute


def next_scheduled_email(db: Session, now_utc: datetime.datetime | None = None) -> datetime.datetime:
    tz = admin_timezone(db)
    now = (now_utc or datetime.datetime.now(datetime.timezone.utc)).astimezone(tz)
    hour, minute = configured_email_time(db)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return target.astimezone(datetime.timezone.utc)
