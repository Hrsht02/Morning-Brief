import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user
from ..seed import get_setting

router = APIRouter(prefix="/editions", tags=["editions"])


def _validate_date(date_str: Optional[str]) -> str:
    if not date_str:
        return datetime.date.today().isoformat()
    try:
        datetime.date.fromisoformat(date_str)
        return date_str
    except ValueError:
        return datetime.date.today().isoformat()  # fail gracefully to "today" rather than error


def _localize(story: models.Story, language: str) -> models.Story:
    """
    Swaps in the Hindi variant of headline/hook/summary IN MEMORY ONLY (never
    committed to the DB) when the user prefers Hindi and a translation was
    actually generated for this story. Falls back to English automatically
    if the Hindi variant is missing - a story never disappears just because
    bilingual generation happened to fail or be off for that run.
    """
    if language == "hi" and story.headline_hi and story.summary_hi:
        story.headline = story.headline_hi
        story.hook = story.hook_hi or story.hook
        story.summary = story.summary_hi
    return story


@router.get("", response_model=schemas.EditionOut)
def get_edition(
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD, defaults to today"),
    category: Optional[str] = Query(default=None, description="Filter to one category slug"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    edition_date = _validate_date(date)

    query = db.query(models.Story).options(joinedload(models.Story.citations)).filter(
        models.Story.edition_date == edition_date,
        models.Story.is_published.is_(True),
        models.Story.publication_status == "approved",
        models.Story.is_test_content.is_(False),  # test/sandbox content never reaches real users
    )

    if category and category != "general":
        query = query.filter(models.Story.category_slug == category)
    elif not category:
        # Default "Mixed / For You": prioritize the user's chosen categories,
        # but always keep at least one story from outside them to avoid a filter bubble.
        user_categories = [c.category_slug for c in user.categories]
        if user_categories:
            min_outside = int(get_setting(db, "outside_bubble_min_stories", "1"))
            preferred = query.filter(models.Story.category_slug.in_(user_categories)).all()
            outside = query.filter(~models.Story.category_slug.in_(user_categories)).limit(min_outside).all()
            stories = sorted(preferred, key=lambda s: (not s.is_pinned, -s.confidence_score)) + outside
            return _build_edition_response(edition_date, stories, db, user.content_language)

    stories = query.order_by(models.Story.is_pinned.desc(), models.Story.confidence_score.desc()).all()
    return _build_edition_response(edition_date, stories, db, user.content_language)


@router.get("/{story_id}", response_model=schemas.StoryOut)
def get_story_detail(
    story_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    story = db.query(models.Story).options(joinedload(models.Story.citations)).filter(
        models.Story.id == story_id,
        models.Story.is_published.is_(True),
        models.Story.publication_status == "approved",
        models.Story.is_test_content.is_(False),
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return _localize(story, user.content_language)


def _build_edition_response(edition_date: str, stories: list, db: Session, language: str) -> schemas.EditionOut:
    stories_per_edition = int(get_setting(db, "stories_per_edition", "8"))
    trimmed = [_localize(s, language) for s in stories[:stories_per_edition]]
    return schemas.EditionOut(
        edition_date=edition_date,
        story_count=len(trimmed),
        estimated_read_minutes=max(1, round(len(trimmed) * 0.5)),
        stories=trimmed,
    )
