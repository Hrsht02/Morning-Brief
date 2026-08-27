"""
Endpoints called by the GitHub Actions cron workflows (see .github/workflows/).
Protected by a shared secret header rather than user JWT auth, since these
calls come from an automated job, not a logged-in browser.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import settings
from ..seed import get_setting
from ..ingestion.pipeline import run_ingestion_background
from ..email_service.sender import send_daily_emails

router = APIRouter(prefix="/internal", tags=["internal/cron"])


def verify_cron_secret(x_cron_secret: str = Header(default="")):
    if not settings.CRON_SECRET or x_cron_secret != settings.CRON_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing cron secret")


@router.post("/run-ingestion")
def cron_run_ingestion(background_tasks: BackgroundTasks, db: Session = Depends(get_db), _=Depends(verify_cron_secret)):
    # The auto/manual toggle lives here, at the automation entry point itself -
    # when manual, scheduled runs are a no-op and ONLY the admin panel's
    # manual buttons can trigger ingestion. This is the literal on/off switch
    # for "I don't need to send manually, but I want the option to."
    if get_setting(db, "scheduling_mode", "auto") == "manual":
        return {"status": "skipped", "detail": "scheduling_mode is 'manual' - scheduled ingestion is disabled"}

    # Fire-and-forget: ingestion can take several minutes (deliberately paced to
    # respect Groq's free-tier token budget), which would otherwise hang this
    # request past GitHub Actions' own timeout and the hosting platform's
    # request timeout. Returning immediately avoids both.
    if get_setting(db, "ingestion_status", "idle") == "running":
        return {"status": "skipped", "detail": "Ingestion already running"}
    background_tasks.add_task(run_ingestion_background)
    return {"status": "started"}


@router.post("/send-emails")
def cron_send_emails(db: Session = Depends(get_db), _=Depends(verify_cron_secret)):
    if get_setting(db, "scheduling_mode", "auto") == "manual":
        return {"status": "skipped", "detail": "scheduling_mode is 'manual' - scheduled sending is disabled"}
    return send_daily_emails(db, force=False)
