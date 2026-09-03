import datetime
import json
import secrets
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db, SessionLocal
from ..auth import get_current_admin, get_current_developer_or_admin
from ..security import hash_password
from ..seed import get_setting
from ..email_service.sender import send_daily_emails, send_test_email
from ..services.job_status import start_job, complete_job, fail_job, get_job

router = APIRouter(prefix="/admin", tags=["admin"])


def log_audit(db: Session, entity_type: str, entity_id, action: str, actor: models.User, notes: str = None):
    db.add(models.AuditLog(entity_type=entity_type, entity_id=str(entity_id) if entity_id is not None else None, action=action, actor=f"user:{actor.id}({actor.email})", notes=notes))

# ---------------- Sources ----------------
@router.get("/sources", response_model=list[schemas.SourceOut])
def list_sources(db: Session = Depends(get_db), _=Depends(get_current_developer_or_admin)):
    return db.query(models.Source).order_by(models.Source.trust_tier.asc(), models.Source.name.asc()).all()

@router.post("/sources", response_model=schemas.SourceOut)
def create_source(payload: schemas.SourceCreate, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    if db.query(models.Source).filter(models.Source.rss_url == payload.rss_url).first():
        raise HTTPException(status_code=409, detail="A source with this RSS URL already exists")
    source = models.Source(**payload.model_dump()); db.add(source); log_audit(db, "source", None, "created", admin); db.commit(); db.refresh(source); return source

@router.put("/sources/{source_id}", response_model=schemas.SourceOut)
def update_source(source_id: int, payload: schemas.SourceUpdate, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    source = db.query(models.Source).filter(models.Source.id == source_id).first()
    if not source: raise HTTPException(status_code=404, detail="Source not found")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(source, key, value)
    log_audit(db, "source", source.id, "updated", admin); db.commit(); db.refresh(source); return source

@router.delete("/sources/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    source = db.query(models.Source).filter(models.Source.id == source_id).first()
    if not source: raise HTTPException(status_code=404, detail="Source not found")
    db.delete(source); log_audit(db, "source", source_id, "deleted", admin); db.commit(); return {"status": "deleted"}

# ---------------- Categories ----------------
@router.get("/categories", response_model=list[schemas.CategoryOut])
def list_categories(db: Session = Depends(get_db), _=Depends(get_current_developer_or_admin)):
    return db.query(models.Category).order_by(models.Category.sort_order.asc()).all()

@router.post("/categories", response_model=schemas.CategoryOut)
def create_category(payload: schemas.CategoryCreate, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    if db.query(models.Category).filter(models.Category.slug == payload.slug).first(): raise HTTPException(status_code=409, detail="Category already exists")
    row = models.Category(**payload.model_dump()); db.add(row); log_audit(db, "category", row.slug, "created", admin); db.commit(); db.refresh(row); return row

@router.put("/categories/{slug}", response_model=schemas.CategoryOut)
def update_category(slug: str, payload: schemas.CategoryUpdate, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    row = db.query(models.Category).filter(models.Category.slug == slug).first()
    if not row: raise HTTPException(status_code=404, detail="Category not found")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    log_audit(db, "category", slug, "updated", admin); db.commit(); db.refresh(row); return row

@router.delete("/categories/{slug}")
def delete_category(slug: str, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    row = db.query(models.Category).filter(models.Category.slug == slug).first()
    if not row: raise HTTPException(status_code=404, detail="Category not found")
    db.delete(row); log_audit(db, "category", slug, "deleted", admin); db.commit(); return {"status": "deleted"}

# ---------------- Settings ----------------
@router.get("/settings", response_model=list[schemas.SettingOut])
def list_settings(db: Session = Depends(get_db), _=Depends(get_current_developer_or_admin)):
    return db.query(models.Setting).order_by(models.Setting.key.asc()).all()

@router.put("/settings/{key}")
def update_setting(key: str, payload: schemas.SettingUpdate, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    row = db.query(models.Setting).filter(models.Setting.key == key).first()
    if not row: raise HTTPException(status_code=404, detail="Setting not found")
    value = str(payload.value).strip()
    if key in {"email_send_time", "email_send_window_start", "email_send_window_end", "final_ingestion_time"}:
        try:
            hour, minute = map(int, value.split(":", 1))
            if not (0 <= hour <= 23 and 0 <= minute <= 59): raise ValueError
            value = f"{hour:02d}:{minute:02d}"
        except Exception:
            raise HTTPException(status_code=422, detail=f"{key} must use HH:MM 24-hour format")
    row.value = value; log_audit(db, "setting", key, "updated", admin, notes=f"value={value}"); db.commit(); return {"status": "updated", "key": key, "value": value}

# ---------------- Verification layers ----------------
@router.get("/verification-layers", response_model=list[schemas.VerificationLayerOut])
def list_verification_layers(db: Session = Depends(get_db), _=Depends(get_current_developer_or_admin)):
    return db.query(models.VerificationLayer).order_by(models.VerificationLayer.sort_order.asc()).all()

@router.put("/verification-layers/{layer_id}", response_model=schemas.VerificationLayerOut)
def update_verification_layer(layer_id: int, payload: schemas.VerificationLayerUpdate, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    row = db.query(models.VerificationLayer).filter(models.VerificationLayer.id == layer_id).first()
    if not row: raise HTTPException(status_code=404, detail="Verification layer not found")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    log_audit(db, "verification_layer", row.id, "updated", admin); db.commit(); db.refresh(row); return row

# ---------------- Users / developers / API keys ----------------
@router.get("/users", response_model=list[schemas.UserAdminOut])
def list_users(db: Session = Depends(get_db), _=Depends(get_current_developer_or_admin)):
    return db.query(models.User).order_by(models.User.created_at.desc()).all()

@router.put("/users/{user_id}/toggle-active")
def toggle_user(user_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin": raise HTTPException(status_code=400, detail="Admin accounts cannot be deactivated here")
    user.is_active = not user.is_active; log_audit(db, "user", user.id, "toggled_active", admin); db.commit(); return {"status": "updated", "is_active": user.is_active}

@router.get("/developers", response_model=list[schemas.UserAdminOut])
def list_developers(db: Session = Depends(get_db), _=Depends(get_current_developer_or_admin)):
    return db.query(models.User).filter(models.User.role == "developer").order_by(models.User.created_at.desc()).all()

@router.post("/developers", response_model=schemas.UserAdminOut)
def create_developer(payload: schemas.DeveloperCreate, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    if db.query(models.User).filter(models.User.email == payload.email).first(): raise HTTPException(status_code=409, detail="Email already exists")
    user = models.User(email=payload.email, hashed_password=hash_password(payload.password), role="developer", is_admin=False, onboarded=True, country_code="IN")
    db.add(user); log_audit(db, "developer", None, "created", admin, notes=user.email); db.commit(); db.refresh(user); return user

@router.delete("/developers/{user_id}")
def revoke_developer(user_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    user = db.query(models.User).filter(models.User.id == user_id, models.User.role == "developer").first()
    if not user: raise HTTPException(status_code=404, detail="Developer not found")
    user.is_active = False; log_audit(db, "developer", user.id, "revoked", admin); db.commit(); return {"status": "revoked"}

@router.get("/api-keys", response_model=list[schemas.ApiKeyOut])
def list_api_keys(db: Session = Depends(get_db), _=Depends(get_current_developer_or_admin)):
    return db.query(models.ApiKey).order_by(models.ApiKey.created_at.desc()).all()

@router.post("/api-keys")
def create_api_key(payload: schemas.ApiKeyCreate, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    raw = "mb_" + secrets.token_urlsafe(32); row = models.ApiKey(name=payload.name, key_prefix=raw[:10], key_hash=hash_password(raw), created_by_user_id=admin.id); db.add(row); log_audit(db, "api_key", None, "created", admin); db.commit(); db.refresh(row); return {"id": row.id, "name": row.name, "key_prefix": row.key_prefix, "raw_key": raw}

@router.delete("/api-keys/{key_id}")
def revoke_api_key(key_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    row = db.query(models.ApiKey).filter(models.ApiKey.id == key_id).first()
    if not row: raise HTTPException(status_code=404, detail="API key not found")
    row.is_active = False; log_audit(db, "api_key", row.id, "revoked", admin); db.commit(); return {"status": "revoked"}

@router.get("/audit-log", response_model=list[schemas.AuditLogOut])
def audit_log(db: Session = Depends(get_db), _=Depends(get_current_developer_or_admin)):
    return db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc()).limit(500).all()

# ---------------- Story moderation ----------------
@router.get("/stories/pending", response_model=list[schemas.StoryOut])
def pending_stories(db: Session = Depends(get_db), _=Depends(get_current_developer_or_admin)):
    return db.query(models.Story).options(joinedload(models.Story.citations)).filter(models.Story.publication_status == "pending", models.Story.is_test_content.is_(False)).order_by(models.Story.created_at.desc()).all()

@router.put("/stories/{story_id}/approve")
def approve_story(story_id: int, payload: schemas.ReviewAction, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    story = db.query(models.Story).filter(models.Story.id == story_id).first()
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    story.publication_status = "approved"; story.is_published = True; story.needs_review = False; story.reviewed_by_user_id = admin.id; story.reviewed_at = datetime.datetime.utcnow(); story.review_notes = payload.notes
    log_audit(db, "story", story.id, "approved", admin, notes=payload.notes); db.commit(); return {"status": "approved"}

@router.put("/stories/{story_id}/reject")
def reject_story(story_id: int, payload: schemas.ReviewAction, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    story = db.query(models.Story).filter(models.Story.id == story_id).first()
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    story.publication_status = "rejected"; story.is_published = False; story.needs_review = False; story.reviewed_by_user_id = admin.id; story.reviewed_at = datetime.datetime.utcnow(); story.review_notes = payload.notes
    log_audit(db, "story", story.id, "rejected", admin, notes=payload.notes); db.commit(); return {"status": "rejected"}

# ---------------- Actions ----------------
@router.post("/actions/run-ingestion", response_model=dict)
def trigger_ingestion(background_tasks: BackgroundTasks, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    from ..ingestion.pipeline import run_ingestion_background
    if get_setting(db, "ingestion_status", "idle") == "running": raise HTTPException(status_code=409, detail="Ingestion is already running - check Operations")
    log_audit(db, "ingestion", None, "manual_trigger", admin); db.commit(); background_tasks.add_task(run_ingestion_background)
    return {"status": "in_progress", "detail": "Ingestion started in the background."}

@router.get("/actions/ingestion-status", response_model=dict)
def get_ingestion_status(db: Session = Depends(get_db), _dev=Depends(get_current_developer_or_admin)):
    status = get_setting(db, "ingestion_status", "idle"); raw_result = get_setting(db, "ingestion_last_result", "")
    try: last_result = json.loads(raw_result) if raw_result else None
    except json.JSONDecodeError: last_result = None
    return {"status": status, "last_result": last_result, "started_at": get_setting(db, "ingestion_started_at", ""), "completed_at": get_setting(db, "ingestion_completed_at", "")}


def _email_worker(mode: str, force: bool = False):
    db = SessionLocal()
    name = "email" if mode != "test" else "test_email"
    try:
        start_job(db, name, mode="manual" if mode == "manual" else mode)
        result = send_daily_emails(db, force=force) if mode != "test" else send_test_email(db, get_setting(db, "developer_test_email", ""))
        if result.get("status") == "completed": complete_job(db, name, result)
        elif result.get("status") in {"scheduled", "waiting", "skipped"}: complete_job(db, name, result)
        else: fail_job(db, name, result.get("detail", "Email operation failed"), result)
    except Exception as exc:
        fail_job(db, name, str(exc))
    finally:
        db.close()

@router.post("/actions/send-emails-now", response_model=dict)
def trigger_send_emails(background_tasks: BackgroundTasks, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    existing = get_job(db, "email")
    if existing.get("status") == "in_progress": return {"status": "in_progress", "detail": "Email delivery is already running"}
    log_audit(db, "email", None, "manual_send_triggered", admin); db.commit(); background_tasks.add_task(_email_worker, "manual", True)
    return {"status": "in_progress", "detail": "Email delivery started. Follow the status in Admin → Operations."}

@router.post("/actions/send-test-email", response_model=dict)
def trigger_test_email(background_tasks: BackgroundTasks, db: Session = Depends(get_db), user=Depends(get_current_developer_or_admin)):
    recipient = get_setting(db, "developer_test_email", "") or user.email
    if get_job(db, "test_email").get("status") == "in_progress": return {"status": "in_progress", "detail": "Test email is already running"}
    background_tasks.add_task(_email_worker, "test", False)
    return {"status": "in_progress", "detail": f"Safe test email queued for {recipient}."}

# ---------------- Stats ----------------
@router.get("/stats", response_model=dict)
def get_stats(db: Session = Depends(get_db), _dev=Depends(get_current_developer_or_admin)):
    today = datetime.date.today().isoformat()
    approved_query = db.query(models.Story).filter(models.Story.publication_status == "approved", models.Story.is_published.is_(True), models.Story.is_test_content.is_(False))
    return {"total_users": db.query(models.User).filter(models.User.role == "user").count(), "active_users": db.query(models.User).filter(models.User.is_active.is_(True), models.User.role == "user").count(), "onboarded_users": db.query(models.User).filter(models.User.onboarded.is_(True), models.User.role == "user").count(), "developer_accounts": db.query(models.User).filter(models.User.role == "developer").count(), "todays_stories": db.query(models.Story).filter(models.Story.edition_date == today, models.Story.is_test_content.is_(False)).count(), "pending_approval": db.query(models.Story).filter(models.Story.publication_status == "pending", models.Story.is_test_content.is_(False)).count(), "approved_today": approved_query.filter(models.Story.edition_date == today).count(), "approved_total": approved_query.count(), "active_sources": db.query(models.Source).filter(models.Source.is_active.is_(True)).count(), "high_risk_sources": db.query(models.Source).filter(models.Source.legal_risk_level == "high_risk").count(), "sources_with_errors": db.query(models.Source).filter(models.Source.last_fetch_error.isnot(None)).count(), "emails_sent_today": db.query(models.EmailLog).filter(models.EmailLog.edition_date == today, models.EmailLog.status == "sent").count(), "scheduling_mode": get_setting(db, "scheduling_mode", "auto"), "skip_all_verification": get_setting(db, "skip_all_verification", "false") == "true", "require_human_approval_all": get_setting(db, "require_human_approval_all", "true") == "true", "testing_mode": get_setting(db, "testing_mode", "false") == "true", "active_api_keys": db.query(models.ApiKey).filter(models.ApiKey.is_active.is_(True)).count()}
