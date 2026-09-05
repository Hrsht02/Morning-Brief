"""Automatic cleanup of old editorial data to keep the free database small."""
import datetime
import logging
from sqlalchemy import delete
from sqlalchemy.orm import Session
from .. import models
from ..seed import get_setting, set_setting

logger = logging.getLogger("morning_brief.retention")


def cleanup_old_stories(db: Session, force: bool = False) -> dict:
    try:
        retention_days = max(1, int(get_setting(db, "news_retention_days", "7")))
    except (TypeError, ValueError):
        retention_days = 7
    today = datetime.datetime.now(datetime.timezone.utc).date()
    cutoff = today - datetime.timedelta(days=retention_days)
    cutoff_date = cutoff.isoformat()

    if not force and get_setting(db, "last_retention_cleanup_date", "") == today.isoformat():
        return {"status": "skipped", "deleted": 0, "retention_days": retention_days, "cutoff_date": cutoff_date}

    old_ids = [row[0] for row in db.query(models.Story.id).filter(models.Story.edition_date < cutoff_date).all()]
    if old_ids:
        db.execute(delete(models.Citation).where(models.Citation.story_id.in_(old_ids)))
        db.execute(delete(models.Story).where(models.Story.id.in_(old_ids)))
    set_setting(db, "last_retention_cleanup_date", today.isoformat(), "Last successful automatic news retention cleanup")
    db.commit()
    logger.info("Retention cleanup removed %s stories older than %s days", len(old_ids), retention_days)
    return {"status": "completed", "deleted": len(old_ids), "retention_days": retention_days, "cutoff_date": cutoff_date}
