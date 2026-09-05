"""In-process exact-time scheduler for admin-configured production jobs."""
from __future__ import annotations
import datetime,logging,threading
from ..database import SessionLocal
from ..seed import get_setting,set_setting
from .job_status import start_job,complete_job,fail_job,get_job
from .schedule_service import claim_due,finish_schedule,ingestion_cutoff
logger=logging.getLogger("morning_brief.runtime_scheduler")
_stop=threading.Event();_thread=None;_locks={"email":threading.Lock(),"ingestion":threading.Lock(),"test_email":threading.Lock(),"retention":threading.Lock()}

def _heartbeat(db,key,value):
 try:set_setting(db,key,value);db.commit()
 except Exception:db.rollback();logger.exception("Unable to persist scheduler state %s",key)

def _run_email_worker(schedule):
 db=SessionLocal()
 try:
  start_job(db,"email",mode="scheduled");_heartbeat(db,"scheduler_last_email_start",datetime.datetime.now(datetime.timezone.utc).isoformat())
  from ..email_service.sender import send_daily_emails
  result=send_daily_emails(db,force=True)
  if result.get("status")=="completed":complete_job(db,"email",result);finish_schedule(db,"email","completed",result)
  else:
   error=result.get("detail") or f"Scheduled email failed with status: {result.get('status','unknown')}";fail_job(db,"email",error,result);finish_schedule(db,"email","failed",result)
 except Exception as exc:
  logger.exception("Scheduled email failed");error=str(exc)[:1000]
  try:db.rollback();fail_job(db,"email",error,{"status":"failed","stage":"scheduler_email_worker","detail":error});finish_schedule(db,"email","failed",{"error":error})
  except Exception:logger.exception("Unable to persist email failure")
 finally:db.close();_locks["email"].release()

def _run_ingestion_worker(schedule):
 try:
  from ..ingestion.pipeline import run_ingestion_background
  db=SessionLocal()
  try:cutoff=ingestion_cutoff(db,schedule);_heartbeat(db,"scheduler_last_ingestion_start",datetime.datetime.now(datetime.timezone.utc).isoformat())
  finally:db.close()
  result=run_ingestion_background(mode="scheduled",freshness_after=cutoff);db=SessionLocal()
  try:
   job=get_job(db,"ingestion")
   if result.get("status") in {"ok","completed"} or job.get("status")=="completed":finish_schedule(db,"ingestion","completed",result)
   else:
    error=result.get("detail") or job.get("error") or f"Scheduled ingestion failed with status: {result.get('status','unknown')}"
    if job.get("status")!="failed":fail_job(db,"ingestion",error,result)
    finish_schedule(db,"ingestion","failed",result)
  finally:db.close()
 except Exception as exc:
  logger.exception("Scheduled ingestion failed");error=str(exc)[:1000];db=SessionLocal()
  try:db.rollback();fail_job(db,"ingestion",error,{"status":"failed","stage":"scheduler_ingestion_worker","detail":error});finish_schedule(db,"ingestion","failed",{"error":error})
  except Exception:logger.exception("Unable to persist ingestion failure")
  finally:db.close()
 finally:_locks["ingestion"].release()

def _run_test_worker():
 db=SessionLocal()
 try:
  start_job(db,"test_email",mode="scheduled_test")
  from .test_scheduler import run_due_test_email
  result=run_due_test_email(db)
  if result.get("status")=="completed":complete_job(db,"test_email",result)
  elif result.get("status") in {"idle","waiting"}:fail_job(db,"test_email",result.get("detail","Test email was not due"),result)
  else:fail_job(db,"test_email",result.get("detail","Scheduled test email failed"),result)
 except Exception as exc:logger.exception("Scheduled test email failed");db.rollback();fail_job(db,"test_email",str(exc)[:1000],{"status":"failed","detail":str(exc)[:1000]})
 finally:db.close();_locks["test_email"].release()

def _run_retention_cleanup():
 db=SessionLocal()
 try:
  from .retention import cleanup_old_stories
  result=cleanup_old_stories(db)
  if result.get("status")=="completed":_heartbeat(db,"scheduler_last_retention_cleanup",datetime.datetime.now(datetime.timezone.utc).isoformat())
 except Exception:db.rollback();logger.exception("Retention cleanup failed")
 finally:db.close();_locks["retention"].release()

def run_due_production_job(job_type:str)->dict:
 if job_type not in {"email","ingestion"}:return {"status":"error","detail":"Unsupported production job"}
 db=SessionLocal();acquired=False
 try:
  if get_setting(db,"scheduling_mode","auto").lower()!="auto":return {"status":"skipped","detail":"Automatic scheduling is disabled"}
  if get_job(db,job_type).get("status")=="in_progress":return {"status":"in_progress","detail":f"{job_type} is already running"}
  acquired=_locks[job_type].acquire(blocking=False)
  if not acquired:return {"status":"in_progress","detail":f"{job_type} is already being claimed"}
  schedule=claim_due(db,job_type)
  if not schedule:_locks[job_type].release();acquired=False;return {"status":"waiting","detail":"No due schedule"}
  _heartbeat(db,f"scheduler_last_{job_type}_claim",datetime.datetime.now(datetime.timezone.utc).isoformat())
  worker=_run_email_worker if job_type=="email" else _run_ingestion_worker;threading.Thread(target=worker,args=(schedule,),daemon=True,name=f"{job_type}-scheduler-worker").start();acquired=False
  return {"status":"in_progress","detail":f"{job_type} schedule claimed and started"}
 except Exception:
  if acquired:_locks[job_type].release()
  raise
 finally:db.close()

def _tick():
 now=datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat();db=SessionLocal()
 try:_heartbeat(db,"scheduler_last_tick_at",now)
 finally:db.close()
 for job_type in ("ingestion","email"):
  try:
   result=run_due_production_job(job_type)
   if result.get("status")=="in_progress":
    db=SessionLocal()
    try:_heartbeat(db,f"scheduler_last_trigger_{job_type}",now)
    finally:db.close()
  except Exception:logger.exception("%s scheduler tick failed",job_type)
 db=SessionLocal()
 try:
  local_today=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
  if get_setting(db,"last_retention_cleanup_date","")!=local_today and _locks["retention"].acquire(blocking=False):threading.Thread(target=_run_retention_cleanup,daemon=True,name="retention-cleanup-worker").start()
  enabled=get_setting(db,"sandbox_test_email_enabled","false").lower()=="true";target=get_setting(db,"sandbox_test_email_scheduled_at","")
  if enabled and target and _locks["test_email"].acquire(blocking=False):
   try:
    due=datetime.datetime.fromisoformat(target);due=due.replace(tzinfo=datetime.timezone.utc) if due.tzinfo is None else due
    if datetime.datetime.now(datetime.timezone.utc)>=due:threading.Thread(target=_run_test_worker,daemon=True,name="test-email-worker").start()
    else:_locks["test_email"].release()
   except ValueError:_locks["test_email"].release()
 finally:db.close()

def _loop():
 logger.info("Unified exact-time runtime scheduler started")
 while not _stop.is_set():
  try:_tick()
  except Exception:logger.exception("Runtime scheduler tick failed")
  _stop.wait(1.0)

def start_runtime_scheduler():
 global _thread
 if _thread and _thread.is_alive():return
 _stop.clear();_thread=threading.Thread(target=_loop,daemon=True,name="morning-brief-scheduler");_thread.start()

def stop_runtime_scheduler():_stop.set()
