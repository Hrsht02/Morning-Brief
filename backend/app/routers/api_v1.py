"""
The API surface a developer's own tooling/scripts can hit using an X-Api-Key
header (issued from the admin panel). Deliberately sandboxed:
  - Ingestion runs here are always test_mode=True: capped to a few clusters,
    tagged is_test_content so they can NEVER appear in a real user's edition
    or a real email, regardless of any other setting.
  - Email sends here always go to a single fixed test address, never the
    real subscriber list, regardless of who "would" have received it.
  - Read endpoints only expose already-public-shaped data (today's real
    approved edition) - no user PII, no other users' data.

This is the whole point of giving a developer a key instead of admin
credentials: they get a fully working sandbox to build and test against,
with no path - accidental or otherwise - to affecting real users.
"""
import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db
from ..auth import get_api_key_context
from ..ingestion.pipeline import run_ingestion
from ..email_service.sender import send_test_email
from ..seed import get_setting

router = APIRouter(prefix="/api/v1", tags=["developer-api"])


@router.get("/health")
def health(_key: models.ApiKey = Depends(get_api_key_context)):
    return {"status": "ok", "sandbox": True}


@router.get("/editions/today", response_model=schemas.EditionOut)
def today_edition(db: Session = Depends(get_db), _key: models.ApiKey = Depends(get_api_key_context)):
    """Real, currently-approved content - read-only, exactly what a real
    user would see today. No PII, nothing sensitive - safe for a developer
    to build against."""
    today = datetime.date.today().isoformat()
    stories = db.query(models.Story).options(joinedload(models.Story.citations)).filter(
        models.Story.edition_date == today,
        models.Story.is_published.is_(True),
        models.Story.publication_status == "approved",
        models.Story.is_test_content.is_(False),
    ).order_by(models.Story.is_pinned.desc(), models.Story.confidence_score.desc()).all()

    stories_per_edition = int(get_setting(db, "stories_per_edition", "8"))
    trimmed = stories[:stories_per_edition]
    return schemas.EditionOut(
        edition_date=today, story_count=len(trimmed),
        estimated_read_minutes=max(1, round(len(trimmed) * 0.5)), stories=trimmed,
    )


@router.post("/test/run-ingestion", response_model=dict)
def test_run_ingestion(db: Session = Depends(get_db), _key: models.ApiKey = Depends(get_api_key_context)):
    """
    Runs the FULL real pipeline (fetch -> cluster -> generate -> verify)
    against real RSS sources, but capped to 3 clusters and every resulting
    story is tagged is_test_content=True - completely invisible to real
    users regardless of its publication_status. Safe to run as often as
    needed while building/testing against this API.
    """
    result = run_ingestion(db, test_mode=True, max_clusters=3)
    return result


@router.get("/test/stories", response_model=list[schemas.StoryOut])
def test_stories(db: Session = Depends(get_db), _key: models.ApiKey = Depends(get_api_key_context)):
    """View whatever test content your key has generated via test/run-ingestion."""
    return db.query(models.Story).options(joinedload(models.Story.citations)) \
        .filter(models.Story.is_test_content.is_(True)) \
        .order_by(models.Story.created_at.desc()).limit(20).all()


@router.post("/test/send-email", response_model=dict)
def test_send_email(db: Session = Depends(get_db), _key: models.ApiKey = Depends(get_api_key_context)):
    """Sends ONE email, built from today's REAL approved content, to the
    configured developer_test_email setting - never to any real subscriber."""
    recipient = get_setting(db, "developer_test_email", "")
    if not recipient:
        return {"status": "error", "detail": "No developer_test_email configured - ask an admin to set it in Settings"}
    return send_test_email(db, test_recipient=recipient)
