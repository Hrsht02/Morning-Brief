"""Read-only operational and editorial management endpoints."""
import datetime,json
from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session,joinedload
from .. import models,schemas
from ..auth import get_current_developer_or_admin
from ..config import settings
from ..database import get_db
from ..seed import get_setting
from ..services.personalization import SUPPORTED_COUNTRIES
from ..services.job_status import get_job
from ..services.schedule_service import get_schedule

router=APIRouter(prefix="/admin",tags=["admin/operations"])

@router.get("/stories/approved",response_model=list[schemas.StoryOut])
def approved_stories(limit:int=200,db:Session=Depends(get_db),_=Depends(get_current_developer_or_admin)):
 return db.query(models.Story).options(joinedload(models.Story.citations)).filter(models.Story.publication_status=="approved",models.Story.is_published.is_(True),models.Story.is_test_content.is_(False)).order_by(models.Story.edition_date.desc(),models.Story.is_pinned.desc(),models.Story.created_at.desc()).limit(max(1,min(limit,1000))).all()

@router.get("/countries",response_model=dict)
def countries(db:Session=Depends(get_db),_=Depends(get_current_developer_or_admin)):
 users=db.query(models.User).filter(models.User.role=="user").all();stories=db.query(models.Story).filter(models.Story.is_test_content.is_(False)).all()
 return {"supported":[{"code":c,"name":n} for c,n in SUPPORTED_COUNTRIES.items() if c!="GLOBAL"],"fallback":"GLOBAL","default":"IN","users_by_country":{c:sum(1 for u in users if u.country_code==c) for c in SUPPORTED_COUNTRIES if c!="GLOBAL"},"stories_by_country":{c:sum(1 for s in stories if s.country_code==c) for c in SUPPORTED_COUNTRIES}}

@router.get("/jobs",response_model=dict)
def job_status(db:Session=Depends(get_db),_=Depends(get_current_developer_or_admin)):
 raw=get_setting(db,"ingestion_last_result","")
 try:last=json.loads(raw) if raw else None
 except json.JSONDecodeError:last=None
 email_schedule=get_schedule(db,"email");ingestion_schedule=get_schedule(db,"ingestion")
 test_schedule={"enabled":get_setting(db,"sandbox_test_email_enabled","false").lower()=="true","scheduled_at":get_setting(db,"sandbox_test_email_scheduled_at","") or None}
 ingestion_job=get_job(db,"ingestion")
 scheduler={"last_tick_at":get_setting(db,"scheduler_last_tick_at","") or None,"last_ingestion_claim":get_setting(db,"scheduler_last_ingestion_claim","") or None,"last_email_claim":get_setting(db,"scheduler_last_email_claim","") or None,"last_ingestion_start":get_setting(db,"scheduler_last_ingestion_start","") or None,"last_email_start":get_setting(db,"scheduler_last_email_start","") or None,"last_retention_cleanup":get_setting(db,"scheduler_last_retention_cleanup","") or None}
 return {"ingestion":{"status":ingestion_job.get("status","ready"),"started_at":get_setting(db,"ingestion_started_at","") ,"completed_at":get_setting(db,"ingestion_completed_at","") ,"last_result":last,"job":ingestion_job},"email":get_job(db,"email"),"test_email":get_job(db,"test_email"),"scheduler":scheduler,"email_top_n":max(1,int(get_setting(db,"email_top_n","25"))),"news_retention_days":max(1,int(get_setting(db,"news_retention_days","7"))),"schedules":{"timezone":get_setting(db,"admin_timezone","Asia/Kolkata"),"email":email_schedule,"ingestion":ingestion_schedule,"test_email":test_schedule,"mode":get_setting(db,"scheduling_mode","auto")},"schedule":{"mode":get_setting(db,"scheduling_mode","auto"),"admin_timezone":get_setting(db,"admin_timezone","Asia/Kolkata"),"email_time":email_schedule.get("time","06:00"),"next_email_at":email_schedule.get("next_run_at"),"test_schedule":test_schedule}}

@router.get("/health/details",response_model=dict)
def detailed_health(db:Session=Depends(get_db),_=Depends(get_current_developer_or_admin)):
 return {"status":"ok","checked_at":datetime.datetime.utcnow().isoformat(),"database":"ok","groq_configured":bool(settings.GROQ_API_KEY),"gemini_configured":bool(settings.GEMINI_API_KEY),"brevo_configured":bool(settings.BREVO_API_KEY),"scheduler_last_tick_at":get_setting(db,"scheduler_last_tick_at","") or None}

@router.post("/actions/test-automatic-email",response_model=dict)
def test_automatic_email(db:Session=Depends(get_db),_=Depends(get_current_developer_or_admin)):
 from ..email_service.scheduler_test import run_automatic_email_test
 try:return run_automatic_email_test(db)
 except Exception as exc:return {"status":"failed","would_send":False,"reason":str(exc)[:500]}
