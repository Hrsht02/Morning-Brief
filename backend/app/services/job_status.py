"""Persistent, UI-friendly lifecycle state for long-running jobs."""
import datetime
import json
from sqlalchemy.orm import Session
from ..seed import get_setting, set_setting


def _now():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _load(db, name):
    raw = get_setting(db, f"job_{name}_status", "")
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return None


def save_job(db: Session, name: str, payload: dict):
    set_setting(db, f"job_{name}_status", json.dumps(payload, separators=(",", ":")))
    db.commit()
    return payload


def start_job(db: Session, name: str, mode: str = "manual"):
    existing = _load(db, name)
    payload = {
        "name": name,
        "mode": mode,
        "status": "in_progress",
        "started_at": _now(),
        "completed_at": None,
        "result": None,
        "error": None,
        "previous": existing,
    }
    return save_job(db, name, payload)


def complete_job(db: Session, name: str, result=None):
    payload = _load(db, name) or {"name": name}
    payload.update({"status": "completed", "completed_at": _now(), "result": result, "error": None})
    return save_job(db, name, payload)


def cancel_job(db: Session, name: str, result=None):
    payload = _load(db, name) or {"name": name}
    payload.update({"status": "cancelled", "completed_at": _now(), "result": result, "error": None})
    return save_job(db, name, payload)


def fail_job(db: Session, name: str, error: str, result=None):
    payload = _load(db, name) or {"name": name}
    payload.update({"status": "failed", "completed_at": _now(), "result": result, "error": str(error)[:1000]})
    return save_job(db, name, payload)


def get_job(db: Session, name: str):
    return _load(db, name) or {
        "name": name,
        "status": "ready",
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
    }
