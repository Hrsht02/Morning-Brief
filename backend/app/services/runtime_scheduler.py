"""In-process scheduler for exact admin-configured minute triggers.

The web service is long-lived on Render, so this loop removes the five-minute
GitHub Actions polling gap. GitHub Actions remains a recovery/health trigger,
while this scheduler owns the exact scheduled minute.
"""
from __future__ import annotations

import datetime
import logging
import threading
import time

from ..database import SessionLocal
from ..seed import get_setting, set_setting
from .job_status import start_job, complete_job, fail_job, get_job
from .time_settings import admin_timezone, configured_email_time

logger = logging.getLogger("morning_brief.runtime_scheduler")
_stop = threading.Event()
_thread = None


def _today_key(db):
    return datetime.datetime.now(admin_timezone(db)).date().isoformat()


def _claim_daily_email(db) -> bool:
    """Claim today's production email trigger before launching the worker."""
    today = _today_key(db)
    if get_setting(db, "email_last_trigger_date", "") == today:
        return False
    set_setting(db, "email_last_trigger_date", today)
    db.commit()
    return True


def _run_email_worker():
    db = SessionLocal()
    try:
        start_job(db, "email", mode="scheduled")
        from ..email_service.sender import send_daily_emails
        result = send_daily_emails(db, force=False)
        if result.get("status") == "completed":
            complete_job(db, "email", result)
        else:
            fail_job(db, "email", result.get("detail", "Scheduled email did not complete"), result)
    except Exception as exc:
        logger.exception("Scheduled email failed")
        fail_job(db, "email", str(exc))
    finally:
        db.close()


def _run_test_worker():
    db = SessionLocal()
    try:
        start_job(db, "test_email", mode="scheduled_test")
        from .test_scheduler import run_due_test_email
        result = run_due_test_email(db)
        if result.get("status") == "completed":
            complete_job(db, "test_email", result)
        elif result.get("status") in {"idle", "waiting"}:
            return
        else:
            fail_job(db, "test_email", result.get("detail", "Scheduled test email failed"), result)
    except Exception as exc:
        logger.exception("Scheduled test email failed")
        fail_job(db, "test_email", str(exc))
    finally:
        db.close()


def _tick():
    db = SessionLocal()
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        local_now = now.astimezone(admin_timezone(db))
        hour, minute = configured_email_time(db)
        if local_now.hour == hour and local_now.minute == minute and local_now.second < 2:
            existing = get_job(db, "email")
            if _claim_daily_email(db) and existing.get("status") != "in_progress":
                threading.Thread(target=_run_email_worker, daemon=True, name="daily-email-worker").start()
    finally:
        db.close()

    # Safe test schedule is one-shot and already stores its exact UTC target.
    db = SessionLocal()
    try:
        enabled = get_setting(db, "sandbox_test_email_enabled", "false").lower() == "true"
        if enabled:
            target = get_setting(db, "sandbox_test_email_scheduled_at", "")
            if target:
                try:
                    due = datetime.datetime.fromisoformat(target)
                    if due.tzinfo is None:
                        due = due.replace(tzinfo=datetime.timezone.utc)
                    if datetime.datetime.now(datetime.timezone.utc) >= due:
                        existing = get_job(db, "test_email")
                        if existing.get("status") != "in_progress":
                            threading.Thread(target=_run_test_worker, daemon=True, name="test-email-worker").start()
                except ValueError:
                    pass
    finally:
        db.close()


def _loop():
    logger.info("Exact-time runtime scheduler started")
    while not _stop.is_set():
        try:
            _tick()
        except Exception:
            logger.exception("Runtime scheduler tick failed")
        _stop.wait(1.0)


def start_runtime_scheduler():
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="morning-brief-scheduler")
    _thread.start()


def stop_runtime_scheduler():
    _stop.set()
