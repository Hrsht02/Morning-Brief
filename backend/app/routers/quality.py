import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from .. import models, schemas
from ..auth import get_current_admin, get_current_developer_or_admin
from ..database import get_db
from ..seed import get_setting
from ..services.quality_benchmark import get_benchmark, save_benchmark

router = APIRouter(prefix="/admin/quality", tags=["admin-quality"])


def _edition_date(db: Session) -> str:
    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo(get_setting(db, "admin_timezone", "Asia/Kolkata"))
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")
    return datetime.datetime.now(tz).date().isoformat()


@router.get("/benchmark")
def read_benchmark(db: Session = Depends(get_db), _=Depends(get_current_developer_or_admin)):
    return get_benchmark(db)


@router.put("/benchmark")
def update_benchmark(payload: dict, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    try:
        min_confidence = float(payload.get("min_confidence", 0.55))
        max_similarity = float(payload.get("max_similarity", 0.20))
        apply_mode = str(payload.get("apply_mode", "upcoming"))
        result = save_benchmark(db, min_confidence, max_similarity, apply_mode, _edition_date(db))
        db.add(models.AuditLog(entity_type="quality_benchmark", entity_id="global", action="updated", actor=f"user:{admin.id}({admin.email})", notes=str(result)))
        db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/stories")
def quality_stories(
    status: str = Query("pending"),
    min_confidence: float | None = Query(None, ge=0, le=1),
    max_confidence: float | None = Query(None, ge=0, le=1),
    min_similarity: float | None = Query(None, ge=0, le=1),
    max_similarity: float | None = Query(None, ge=0, le=1),
    edition_date: str | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_developer_or_admin),
):
    q = db.query(models.Story).options(joinedload(models.Story.citations)).filter(models.Story.is_test_content.is_(False))
    if status and status != "all":
        q = q.filter(models.Story.publication_status == status)
    if edition_date:
        q = q.filter(models.Story.edition_date == edition_date)
    if min_confidence is not None:
        q = q.filter(models.Story.confidence_score >= min_confidence)
    if max_confidence is not None:
        q = q.filter(models.Story.confidence_score <= max_confidence)
    if min_similarity is not None:
        q = q.filter(models.Story.max_source_similarity >= min_similarity)
    if max_similarity is not None:
        q = q.filter(models.Story.max_source_similarity <= max_similarity)
    return q.order_by(models.Story.created_at.desc()).limit(500).all()
