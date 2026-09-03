"""In-process exact-time scheduler for admin-configured production jobs."""
from __future__ import annotations
import datetime
import logging
import threading
from ..database import SessionLocal
from ..seed import get_setting
from .job_status import start_job, complete_job, fail_job, get_job
from .schedule_service import claim_due, finish_schedule, get_schedule, ingestion_cutoff

logger = logging.getLogger("morning_brief.runtime_scheduler")
_stop = threading.Event()
_thread = None
_locks = {"email": threading.Lock(), "ingestion": threading.Lock(), "test_email": threading.Lock()}


def _run_email_worker(schedule):
    db = SessionLocal()
    try:
        start_job(db, "email", mode="scheduled")
        from ..email_service.sender import send_daily_emails
        result = send_daily_emails(db, force=True)
        if result.get("status") == "completed":
            complete_job(db, "email", result); finish_schedule(db, "email", "completed", result)
        else:
            fail_job(db, "email", result.get("detail", "Scheduled email did not complete"), result); finish_schedule(db, "email", "failed", result)
    except Exception as exc:
        logger.exception("Scheduled email failed")
        fail_job(db, "email", str(exc)); finish_schedule(db, "email", "failed", {"error": str(exc)})
    finally:
        db.close(); _locks["email"].release()


def _run_ingestion_worker(schedule):
    try:
        from ..ingestion.pipeline import run_ingestion_background
        db = SessionLocal()
        try: cutoff = ingestion_cutoff(db, schedule)
        finally: db.close()
        run_ingestion_background(mode="scheduled", freshness_after=cutoff)
        db = SessionLocal()
        try:
            result = get_job(db, "ingestion")
            if result.get("status") == "completed": finish_schedule(db, "ingestion", "completed", result.get("result"))
            else: finish_schedule(db, "ingestion", "failed", result.get("result") or {"error": result.get("error")})
        finally: db.close()
    except Exception as exc:
        logger.exception("Scheduled ingestion failed")
        db = SessionLocal()
        try: fail_job(db, "ingestion", str(exc)); finish_schedule(db, "ingestion", "failed", {"error": str(exc)})
        finally: db.close()
    finally:
        _locks["ingestion"].release()


def _run_test_worker():
    db = SessionLocal()
    try:
        start_job(db, "test_email", mode="scheduled_test")
        from .test_scheduler import run_due_test_email
        result = run_due_test_email(db)
        if result.get("status") == "completed": complete_job(db, "test_email", result)
        elif result.get("status") in {"idle", "waiting"}: return
        else: fail_job(db, "test_email", result.get("detail", "Scheduled test email failed"), result)
    except Exception as exc:
        logger.exception("Scheduled test email failed")
        fail_job(db, "test_email", str(exc))
    finally:
        db.close(); _locks["test_email"].release()


def run_due_production_job(job_type: str) -> dict:
    """Claim and launch one due production job; safe for runtime or cron calls."""
    if job_type not in {"email", "ingestion"}: return {"status": "error", "detail": "Unsupported production job"}
    db = SessionLocal()
    try:
        if get_setting(db, "scheduling_mode", "auto").lower() != "auto": return {"status": "skipped", "detail": "Automatic scheduling is disabled"}
        if get_job(db, job_type).get("status") == "in_progress": return {"status": "in_progress", "detail": f"{job_type} is already running"}
        if not _locks[job_type].acquire(blocking=False): return {"status": "in_progress", "detail": f"{job_type} is already being claimed"}
        schedule = claim_due(db, job_type)
        if not schedule:
            _locks[job_type].release(); return {"status": "waiting", "detail": "No due schedule"}
        worker = _run_email_worker if job_type == "email" else _run_ingestion_worker
        threading.Thread(target=worker, args=(schedule,), daemon=True, name=f"{job_type}-scheduler-worker").start()
        return {"status": "in_progress", "detail": f"{job_type} schedule claimed and started"}
    finally:
        db.close()


def _tick():
    for job_type in ("ingestion", "email"):
        try: run_due_production_job(job_type)
        except Exception: logger.exception("%s scheduler tick failed", job_type)

    db = SessionLocal()
    try:
        enabled = get_setting(db, "sandbox_test_email_enabled", "false").lower() == "true"
        target = get_setting(db, "sandbox_test_email_scheduled_at", "")
        if enabled and target and _locks["test_email"].acquire(blocking=False):
            try:
                due = datetime.datetime.fromisoformat(target)
                if due.tzinfo is None: due = due.replace(tzinfo=datetime.timezone.utc)
                if datetime.datetime.now(datetime.timezone.utc) >= due:
                    threading.Thread(target=_run_test_worker, daemon=True, name="test-email-worker").start()
                else: _locks["test_email"].release()
            except ValueError: _locks["test_email"].release()
    finally: db.close()


def _loop():
    logger.info("Unified exact-time runtime scheduler started")
    while not _stop.is_set():
        try: _tick()
        except Exception: logger.exception("Runtime scheduler tick failed")
        _stop.wait(1.0)


def start_runtime_scheduler():
    global _thread
    if _thread and _thread.is_alive(): return
    _stop.clear(); _thread = threading.Thread(target=_loop, daemon=True, name="morning-brief-scheduler"); _thread.start()


def stop_runtime_scheduler(): _stop.set()
