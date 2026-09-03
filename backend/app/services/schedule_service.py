"""Unified persistent schedules for production ingestion and email delivery.

Schedules are stored in the existing settings table so no destructive schema
migration is required. The database values are the source of truth; the
runtime scheduler and recovery cron both consume the same schedule records.
"""
from __future__ import annotations

import datetime
import json
import zoneinfo
from sqlalchemy.orm import Session
from ..seed import get_setting, set_setting

SCHEDULE_KEYS = {"email": "production_email_schedule", "ingestion": "production_ingestion_schedule"}
DEFAULT_TIMEZONE = "Asia/Kolkata"


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def _timezone(db: Session, name: str | None = None):
    value = name or get_setting(db, "admin_timezone", DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE
    try:
        return zoneinfo.ZoneInfo(value)
    except Exception:
        return zoneinfo.ZoneInfo(DEFAULT_TIMEZONE)


def _parse_hhmm(value: str) -> tuple[int, int]:
    hour, minute = (int(x) for x in value.split(":", 1))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError
    return hour, minute


def _load(db: Session, job_type: str) -> dict:
    key = SCHEDULE_KEYS[job_type]
    raw = get_setting(db, key, "")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except (TypeError, ValueError):
            pass
    return {"enabled": False, "frequency": "daily", "date": None, "time": "06:00", "timezone": get_setting(db, "admin_timezone", DEFAULT_TIMEZONE), "next_run_at": None, "last_run_at": None, "last_status": "ready", "last_result": None, "updated_at": None}


def _save(db: Session, job_type: str, data: dict) -> dict:
    data["updated_at"] = _now_utc().isoformat()
    set_setting(db, SCHEDULE_KEYS[job_type], json.dumps(data, separators=(",", ":")), f"Unified {job_type} production schedule")
    db.commit()
    return data


def _next_from_local(db: Session, data: dict, now_utc: datetime.datetime | None = None) -> datetime.datetime | None:
    tz = _timezone(db, data.get("timezone"))
    now = (now_utc or _now_utc()).astimezone(tz)
    hour, minute = _parse_hhmm(data["time"])
    if data.get("frequency") == "once":
        if not data.get("date"):
            raise ValueError("A date is required for a one-time schedule")
        local_target = datetime.datetime.fromisoformat(f"{data['date']}T{hour:02d}:{minute:02d}").replace(tzinfo=tz)
        return local_target.astimezone(datetime.timezone.utc)
    local_target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if local_target <= now:
        local_target += datetime.timedelta(days=1)
    return local_target.astimezone(datetime.timezone.utc)


def configure_schedule(db: Session, job_type: str, *, frequency: str, date: str | None, time: str, freshness_mode: str | None = None, freshness_after: str | None = None) -> dict:
    if job_type not in SCHEDULE_KEYS:
        raise ValueError("Unsupported schedule type")
    if frequency not in {"once", "daily"}:
        raise ValueError("frequency must be once or daily")
    _parse_hhmm(time)
    if frequency == "once":
        if not date:
            raise ValueError("Date is required for a one-time schedule")
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            raise ValueError("Date must use YYYY-MM-DD format")
    elif date:
        date = None

    data = _load(db, job_type)
    data.update({"enabled": True, "frequency": frequency, "date": date, "time": time, "timezone": get_setting(db, "admin_timezone", DEFAULT_TIMEZONE), "last_status": "scheduled", "last_result": None})
    if job_type == "ingestion":
        if freshness_mode not in {None, "since_last_successful", "after_datetime"}:
            raise ValueError("Unsupported freshness mode")
        data["freshness_mode"] = freshness_mode or "since_last_successful"
        data["freshness_after"] = freshness_after or None
        if data["freshness_mode"] == "after_datetime" and not data["freshness_after"]:
            raise ValueError("A freshness date/time is required for after_datetime")
        if data["freshness_mode"] == "after_datetime":
            try:
                cutoff = datetime.datetime.fromisoformat(data["freshness_after"])
                if cutoff.tzinfo is None:
                    cutoff = cutoff.replace(tzinfo=_timezone(db))
                data["freshness_after"] = cutoff.isoformat()
            except ValueError:
                raise ValueError("Freshness date/time must be ISO format")
    data["next_run_at"] = _next_from_local(db, data)
    return _save(db, job_type, data)


def get_schedule(db: Session, job_type: str) -> dict:
    data = _load(db, job_type)
    if data.get("enabled") and not data.get("next_run_at"):
        data["next_run_at"] = _next_from_local(db, data)
        _save(db, job_type, data)
    return data


def cancel_schedule(db: Session, job_type: str) -> dict:
    data = _load(db, job_type)
    data["enabled"] = False
    data["last_status"] = "cancelled"
    data["next_run_at"] = None
    return _save(db, job_type, data)


def is_due(db: Session, job_type: str, now_utc: datetime.datetime | None = None) -> bool:
    data = get_schedule(db, job_type)
    if not data.get("enabled") or not data.get("next_run_at"):
        return False
    try:
        target = datetime.datetime.fromisoformat(data["next_run_at"])
        if target.tzinfo is None:
            target = target.replace(tzinfo=datetime.timezone.utc)
        return (now_utc or _now_utc()) >= target.astimezone(datetime.timezone.utc)
    except ValueError:
        return False


def claim_due(db: Session, job_type: str, now_utc: datetime.datetime | None = None) -> dict | None:
    """Claim a due schedule before starting its worker.

    Daily schedules are advanced immediately so a long-running job cannot be
    claimed twice. One-time schedules are disabled before execution and can be
    explicitly scheduled again from Admin.
    """
    if not is_due(db, job_type, now_utc):
        return None
    data = get_schedule(db, job_type)
    claimed_at = now_utc or _now_utc()
    data["last_run_at"] = claimed_at.isoformat()
    data["last_status"] = "in_progress"
    if data.get("frequency") == "daily":
        tz = _timezone(db, data.get("timezone"))
        local = claimed_at.astimezone(tz) + datetime.timedelta(days=1)
        hour, minute = _parse_hhmm(data["time"])
        next_local = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        data["next_run_at"] = next_local.astimezone(datetime.timezone.utc).isoformat()
    else:
        data["enabled"] = False
        data["next_run_at"] = None
    return _save(db, job_type, data)


def finish_schedule(db: Session, job_type: str, status: str, result=None) -> dict:
    data = _load(db, job_type)
    data["last_status"] = status
    data["last_result"] = result
    return _save(db, job_type, data)


def ingestion_cutoff(db: Session, schedule: dict | None = None) -> datetime.datetime | None:
    schedule = schedule or get_schedule(db, "ingestion")
    mode = schedule.get("freshness_mode", "since_last_successful")
    if mode == "after_datetime":
        raw = schedule.get("freshness_after")
    else:
        raw = get_setting(db, "last_successful_ingestion_at", "")
    if not raw:
        return None
    try:
        value = datetime.datetime.fromisoformat(raw)
        if value.tzinfo is None:
            value = value.replace(tzinfo=_timezone(db))
        return value.astimezone(datetime.timezone.utc)
    except ValueError:
        return None
