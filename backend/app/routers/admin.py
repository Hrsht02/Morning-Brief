import datetime
import json
import secrets
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_admin, get_current_developer_or_admin
from ..security import hash_password
from ..seed import get_setting
from ..email_service.sender import send_daily_emails, send_test_email

router = APIRouter(prefix="/admin", tags=["admin"])


def log_audit(db: Session, entity_type: str, entity_id, action: str, actor: models.User, notes: str = None):
    """Central helper - every admin action worth reconstructing later goes
    through this, so the audit trail is consistent rather than ad-hoc."""
    db.add(models.AuditLog(
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        action=action,
        actor=f"user:{actor.id}({actor.email})",
        notes=notes,
    ))


# ---------------- Sources ----------------
@router.get("/sources", response_model=list[schemas.SourceOut])
def list_sources(db: Session = Depends(get_db), _dev=Depends(get_current_developer_or_admin)):
    return db.query(models.Source).order_by(models.Source.name).all()


@router.post("/sources", response_model=schemas.SourceOut, status_code=201)
def create_source(payload: schemas.SourceCreate, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    existing = db.query(models.Source).filter(models.Source.rss_url == payload.rss_url).first()
    if existing:
        raise HTTPException(status_code=409, detail="A source with this RSS URL already exists")
    source = models.Source(**payload.model_dump())
    db.add(source)
    db.flush()
    log_audit(db, "source", source.id, "created", admin, f"name={source.name}, risk={source.legal_risk_level}")
    db.commit()
    db.refresh(source)
    return source


@router.put("/sources/{source_id}", response_model=schemas.SourceOut)
def update_source(source_id: int, payload: schemas.SourceUpdate, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    source = db.query(models.Source).filter(models.Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(source, field, value)
    if "legal_risk_level" in changes:
        log_audit(db, "source", source.id, "risk_level_changed", admin, f"new risk={changes['legal_risk_level']}")
    db.commit()
    db.refresh(source)
    return source


@router.delete("/sources/{source_id}", response_model=schemas.MessageResponse)
def delete_source(source_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    source = db.query(models.Source).filter(models.Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    log_audit(db, "source", source.id, "deleted", admin, f"name={source.name}")
    db.delete(source)
    db.commit()
    return schemas.MessageResponse(message="Source deleted")


# ---------------- Categories ----------------
@router.post("/categories", response_model=schemas.CategoryOut, status_code=201)
def create_category(payload: schemas.CategoryCreate, db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    existing = db.query(models.Category).filter(models.Category.slug == payload.slug).first()
    if existing:
        raise HTTPException(status_code=409, detail="A category with this slug already exists")
    category = models.Category(**payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.delete("/categories/{slug}", response_model=schemas.MessageResponse)
def delete_category(slug: str, db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    category = db.query(models.Category).filter(models.Category.slug == slug).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    category.is_active = False
    db.commit()
    return schemas.MessageResponse(message="Category deactivated")


# ---------------- Settings ----------------
@router.get("/settings", response_model=list[schemas.SettingOut])
def list_settings(db: Session = Depends(get_db), _dev=Depends(get_current_developer_or_admin)):
    return db.query(models.Setting).order_by(models.Setting.key).all()


@router.put("/settings/{key}", response_model=schemas.SettingOut)
def update_setting(key: str, payload: schemas.SettingUpdate, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    setting = db.query(models.Setting).filter(models.Setting.key == key).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    old_value = setting.value
    setting.value = payload.value
    log_audit(db, "setting", key, "updated", admin, f"'{old_value}' -> '{payload.value}'")
    db.commit()
    db.refresh(setting)
    return setting


# ---------------- Verification layers ----------------
@router.get("/verification-layers", response_model=list[schemas.VerificationLayerOut])
def list_verification_layers(db: Session = Depends(get_db), _dev=Depends(get_current_developer_or_admin)):
    return db.query(models.VerificationLayer).order_by(models.VerificationLayer.sort_order).all()


@router.put("/verification-layers/{layer_id}", response_model=schemas.VerificationLayerOut)
def update_verification_layer(layer_id: int, payload: schemas.VerificationLayerUpdate, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    layer = db.query(models.VerificationLayer).filter(models.VerificationLayer.id == layer_id).first()
    if not layer:
        raise HTTPException(status_code=404, detail="Verification layer not found")
    changes = payload.model_dump(exclude_unset=True)
    if "config" in changes and changes["config"] is not None:
        changes["config"] = json.dumps(changes["config"])
    for field, value in changes.items():
        setattr(layer, field, value)
    log_audit(db, "verification_layer", layer.key, "updated", admin, str(changes))
    db.commit()
    db.refresh(layer)
    return layer


# ---------------- Users ----------------
@router.get("/users", response_model=list[schemas.AdminUserOut])
def list_users(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    return db.query(models.User).order_by(models.User.created_at.desc()).limit(500).all()


@router.put("/users/{user_id}/toggle-active", response_model=schemas.AdminUserOut)
def toggle_user_active(user_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    target.is_active = not target.is_active
    log_audit(db, "user", target.id, "active_toggled", admin, f"is_active={target.is_active}")
    db.commit()
    db.refresh(target)
    return target


# ---------------- Developer accounts ----------------
@router.get("/developers", response_model=list[schemas.AdminUserOut])
def list_developers(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    return db.query(models.User).filter(models.User.role == "developer").order_by(models.User.created_at.desc()).all()


@router.post("/developers", response_model=schemas.AdminUserOut, status_code=201)
def create_developer(payload: schemas.DeveloperAccountCreate, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    existing = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    free_plan = db.query(models.Plan).filter(models.Plan.slug == "free").first()
    developer = models.User(
        email=payload.email.lower(), hashed_password=hash_password(payload.password), role="developer",
        onboarded=True, plan_id=free_plan.id if free_plan else None,
    )
    db.add(developer)
    db.flush()
    log_audit(db, "user", developer.id, "developer_created", admin, f"email={developer.email}")
    db.commit()
    db.refresh(developer)
    return developer


@router.delete("/developers/{user_id}", response_model=schemas.MessageResponse)
def revoke_developer(user_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    target = db.query(models.User).filter(models.User.id == user_id, models.User.role == "developer").first()
    if not target:
        raise HTTPException(status_code=404, detail="Developer account not found")
    log_audit(db, "user", target.id, "developer_revoked", admin, f"email={target.email}")
    target.is_active = False
    target.role = "user"
    db.commit()
    return schemas.MessageResponse(message="Developer access revoked")


# ---------------- API keys ----------------
@router.get("/api-keys", response_model=list[schemas.ApiKeyOut])
def list_api_keys(db: Session = Depends(get_db), _dev=Depends(get_current_developer_or_admin)):
    return db.query(models.ApiKey).order_by(models.ApiKey.created_at.desc()).all()


@router.post("/api-keys", response_model=schemas.ApiKeyCreatedOut, status_code=201)
def create_api_key(payload: schemas.ApiKeyCreate, db: Session = Depends(get_db), user=Depends(get_current_developer_or_admin)):
    raw_key = "mb_" + secrets.token_urlsafe(32)
    api_key = models.ApiKey(name=payload.name, key_prefix=raw_key[:8], key_hash=hash_password(raw_key), created_by_user_id=user.id)
    db.add(api_key)
    db.flush()
    log_audit(db, "api_key", api_key.id, "created", user, f"name={payload.name}")
    db.commit()
    db.refresh(api_key)
    return schemas.ApiKeyCreatedOut(
        id=api_key.id, name=api_key.name, key_prefix=api_key.key_prefix,
        is_active=api_key.is_active, created_at=api_key.created_at,
        last_used_at=api_key.last_used_at, raw_key=raw_key,
    )


@router.delete("/api-keys/{key_id}", response_model=schemas.MessageResponse)
def revoke_api_key(key_id: int, db: Session = Depends(get_db), user=Depends(get_current_developer_or_admin)):
    api_key = db.query(models.ApiKey).filter(models.ApiKey.id == key_id).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    api_key.is_active = False
    log_audit(db, "api_key", api_key.id, "revoked", user)
    db.commit()
    return schemas.MessageResponse(message="API key revoked")


# ---------------- Audit log ----------------
@router.get("/audit-log", response_model=list[schemas.AuditLogOut])
def get_audit_log(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    return db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc()).limit(200).all()


# ---------------- Story moderation / approval workflow ----------------
@router.get("/stories/pending", response_model=list[schemas.StoryOut])
def pending_stories(db: Session = Depends(get_db), _dev=Depends(get_current_developer_or_admin)):
    return db.query(models.Story).options(joinedload(models.Story.citations)) \
        .filter(models.Story.publication_status == "pending", models.Story.is_test_content.is_(False)) \
        .order_by(models.Story.created_at.desc()).all()


@router.put("/stories/{story_id}/approve", response_model=schemas.StoryOut)
def approve_story(story_id: int, payload: schemas.StoryDecision = schemas.StoryDecision(), db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    story = db.query(models.Story).filter(models.Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    story.publication_status = "approved"
    story.is_published = True
    story.needs_review = False
    story.pipeline_stage = "published"
    story.reviewed_by_user_id = admin.id
    story.reviewed_at = datetime.datetime.utcnow()
    story.review_notes = payload.notes
    log_audit(db, "story", story.id, "approved", admin, payload.notes)
    db.commit()
    db.refresh(story)
    return story


@router.put("/stories/{story_id}/reject", response_model=schemas.StoryOut)
def reject_story(story_id: int, payload: schemas.StoryDecision = schemas.StoryDecision(), db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    story = db.query(models.Story).filter(models.Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    story.publication_status = "rejected"
    story.is_published = False
    story.pipeline_stage = "rejected"
    story.reviewed_by_user_id = admin.id
    story.reviewed_at = datetime.datetime.utcnow()
    story.review_notes = payload.notes
    log_audit(db, "story", story.id, "rejected", admin, payload.notes)
    db.commit()
    db.refresh(story)
    return story


@router.put("/stories/{story_id}", response_model=schemas.StoryOut)
def update_story(story_id: int, payload: schemas.StoryUpdate, db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    story = db.query(models.Story).filter(models.Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(story, field, value)
    db.commit()
    db.refresh(story)
    return story


@router.delete("/stories/{story_id}", response_model=schemas.MessageResponse)
def delete_story(story_id: int, db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    story = db.query(models.Story).filter(models.Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    db.delete(story)
    db.commit()
    return schemas.MessageResponse(message="Story deleted")


# ---------------- Manual trigger actions ----------------
@router.post("/actions/run-ingestion", response_model=dict)
def trigger_ingestion(background_tasks: BackgroundTasks, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    from ..ingestion.pipeline import run_ingestion_background
    if get_setting(db, "ingestion_status", "idle") == "running":
        raise HTTPException(status_code=409, detail="Ingestion is already running - check back in a few minutes")
    log_audit(db, "ingestion", None, "manual_trigger", admin)
    db.commit()
    background_tasks.add_task(run_ingestion_background)
    return {"status": "started", "detail": "Ingestion started in the background. This can take a few minutes - poll /admin/actions/ingestion-status for progress."}


@router.get("/actions/ingestion-status", response_model=dict)
def get_ingestion_status(db: Session = Depends(get_db), _dev=Depends(get_current_developer_or_admin)):
    status = get_setting(db, "ingestion_status", "idle")
    raw_result = get_setting(db, "ingestion_last_result", "")
    try:
        last_result = json.loads(raw_result) if raw_result else None
    except json.JSONDecodeError:
        last_result = None
    return {"status": status, "last_result": last_result}


@router.post("/actions/send-emails-now", response_model=dict)
def trigger_send_emails(db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    log_audit(db, "email", None, "manual_send_triggered", admin)
    db.commit()
    return send_daily_emails(db, force=True)


@router.post("/actions/send-test-email", response_model=dict)
def trigger_test_email(db: Session = Depends(get_db), user=Depends(get_current_developer_or_admin)):
    recipient = get_setting(db, "developer_test_email", "") or user.email
    return send_test_email(db, test_recipient=recipient, language=user.content_language)


# ---------------- Stats ----------------
@router.get("/stats", response_model=dict)
def get_stats(db: Session = Depends(get_db), _dev=Depends(get_current_developer_or_admin)):
    today = datetime.date.today().isoformat()
    approved_query = db.query(models.Story).filter(
        models.Story.publication_status == "approved",
        models.Story.is_published.is_(True),
        models.Story.is_test_content.is_(False),
    )
    return {
        "total_users": db.query(models.User).filter(models.User.role == "user").count(),
        "active_users": db.query(models.User).filter(models.User.is_active.is_(True), models.User.role == "user").count(),
        "onboarded_users": db.query(models.User).filter(models.User.onboarded.is_(True), models.User.role == "user").count(),
        "developer_accounts": db.query(models.User).filter(models.User.role == "developer").count(),
        "todays_stories": db.query(models.Story).filter(models.Story.edition_date == today, models.Story.is_test_content.is_(False)).count(),
        "pending_approval": db.query(models.Story).filter(models.Story.publication_status == "pending", models.Story.is_test_content.is_(False)).count(),
        "approved_today": approved_query.filter(models.Story.edition_date == today).count(),
        "approved_total": approved_query.count(),
        "active_sources": db.query(models.Source).filter(models.Source.is_active.is_(True)).count(),
        "high_risk_sources": db.query(models.Source).filter(models.Source.legal_risk_level == "high_risk").count(),
        "sources_with_errors": db.query(models.Source).filter(models.Source.last_fetch_error.isnot(None)).count(),
        "emails_sent_today": db.query(models.EmailLog).filter(models.EmailLog.edition_date == today, models.EmailLog.status == "sent").count(),
        "scheduling_mode": get_setting(db, "scheduling_mode", "auto"),
        "skip_all_verification": get_setting(db, "skip_all_verification", "false") == "true",
        "require_human_approval_all": get_setting(db, "require_human_approval_all", "true") == "true",
        "testing_mode": get_setting(db, "testing_mode", "false") == "true",
        "active_api_keys": db.query(models.ApiKey).filter(models.ApiKey.is_active.is_(True)).count(),
    }
