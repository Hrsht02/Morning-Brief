"""External recovery triggers for the unified database-backed scheduler.

Render owns exact-minute execution. GitHub Actions calls these endpoints every
few minutes as a recovery mechanism, and the same due-job executor is used so
there is only one scheduling implementation.
"""
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import settings
from ..seed import get_setting
from ..services.runtime_scheduler import run_due_production_job
from ..services.test_scheduler import run_due_test_email

router = APIRouter(prefix="/internal", tags=["internal/cron"])


def verify_cron_secret(x_cron_secret: str = Header(default="")):
    if not settings.CRON_SECRET or x_cron_secret != settings.CRON_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing cron secret")


@router.post("/run-ingestion")
def cron_run_ingestion(db: Session = Depends(get_db), _=Depends(verify_cron_secret)):
    if get_setting(db, "scheduling_mode", "auto") == "manual":
        return {"status": "skipped", "detail": "scheduling_mode is 'manual' - scheduled ingestion is disabled"}
    return run_due_production_job("ingestion")


@router.post("/send-emails")
def cron_send_emails(db: Session = Depends(get_db), _=Depends(verify_cron_secret)):
    if get_setting(db, "scheduling_mode", "auto") == "manual":
        return {"status": "skipped", "detail": "scheduling_mode is 'manual' - scheduled sending is disabled"}
    return run_due_production_job("email")


@router.post("/run-sandbox-test-email")
def cron_run_sandbox_test_email(db: Session = Depends(get_db), _=Depends(verify_cron_secret)):
    return run_due_test_email(db)
