import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db
from ..seed import get_setting
from ..services.personalization import select_personalized_stories

router = APIRouter(prefix="/editions", tags=["editions"])


def _validate_date(date_str: Optional[str]) -> str:
    if not date_str:
        return datetime.date.today().isoformat()
    try:
        datetime.date.fromisoformat(date_str)
        return date_str
    except ValueError:
        return datetime.date.today().isoformat()


def _localize(story: models.Story, language: str) -> models.Story:
    if language == "hi" and story.headline_hi and story.summary_hi:
        story.headline = story.headline_hi
        story.hook = story.hook_hi or story.hook
        story.summary = story.summary_hi
    return story


@router.get("", response_model=schemas.EditionOut)
def get_edition(
    date: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    edition_date = _validate_date(date)
    query = db.query(models.Story).options(joinedload(models.Story.citations)).filter(
        models.Story.edition_date == edition_date,
        models.Story.is_published.is_(True),
        models.Story.publication_status == "approved",
        models.Story.is_test_content.is_(False),
    )

    stories = query.all()
    if category and category != "general":
        stories = [s for s in stories if s.category_slug == category]
        selected = stories[: int(get_setting(db, "stories_per_edition", "8"))]
        resolution = __import__("app.services.personalization", fromlist=["resolve_country"]).resolve_country(user.country_code)
    else:
        limit = int(get_setting(db, "stories_per_edition", "8"))
        outside = int(get_setting(db, "outside_bubble_min_stories", "1"))
        selected, resolution = select_personalized_stories(
            stories, user.country_code,
            {c.category_slug for c in user.categories},
            limit, outside,
        )
    return _build_edition_response(edition_date, selected, user.content_language, resolution)


@router.get("/{story_id}", response_model=schemas.StoryOut)
def get_story_detail(story_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    story = db.query(models.Story).options(joinedload(models.Story.citations)).filter(
        models.Story.id == story_id,
        models.Story.is_published.is_(True),
        models.Story.publication_status == "approved",
        models.Story.is_test_content.is_(False),
    ).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return _localize(story, user.content_language)


def _build_edition_response(edition_date: str, stories: list, language: str, resolution) -> schemas.EditionOut:
    trimmed = [_localize(s, language) for s in stories]
    return schemas.EditionOut(
        edition_date=edition_date,
        story_count=len(trimmed),
        estimated_read_minutes=max(1, round(len(trimmed) * 0.5)),
        stories=trimmed,
        country_requested=resolution.requested or None,
        country_effective=resolution.effective,
        country_supported=resolution.supported,
        fallback_used=resolution.fallback_used,
    )
