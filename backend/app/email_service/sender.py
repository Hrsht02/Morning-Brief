"""Timezone-aware, country/category-personalized email delivery."""
import datetime
import logging
import zoneinfo
from sqlalchemy.orm import Session, joinedload
from .. import models
from ..seed import get_setting
from ..services.personalization import select_personalized_stories
from .brevo_client import send_email, render_digest_email, EmailSendError
from ..config import settings

logger = logging.getLogger("morning_brief.email")
FIXED_DELIVERY_HOUR = 6
FIXED_DELIVERY_MINUTE = 0
DELIVERY_WINDOW_MINUTES = 60


def _is_users_send_time_now(user, window_minutes=DELIVERY_WINDOW_MINUTES):
    """Return true during the fixed 06:00 local-time delivery window.

    User-configured send_hour/send_minute are intentionally ignored. The
    product has one predictable delivery promise: 06:00 in each reader's
    local timezone.
    """
    try:
        tz = zoneinfo.ZoneInfo(user.timezone)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")
    now = datetime.datetime.now(tz)
    target = now.replace(hour=FIXED_DELIVERY_HOUR, minute=FIXED_DELIVERY_MINUTE, second=0, microsecond=0)
    return 0 <= (now - target).total_seconds() / 60 < window_minutes


def _localize_for_email(story, language):
    if language == "hi" and story.headline_hi and story.summary_hi:
        story.headline, story.hook, story.summary = story.headline_hi, story.hook_hi or story.hook, story.summary_hi
    return story


def _get_approved_stories_for_edition(db: Session, edition_date: str):
    """Return only real, approved production stories for one edition."""
    return db.query(models.Story).options(joinedload(models.Story.citations)).filter(
        models.Story.edition_date == edition_date,
        models.Story.is_published.is_(True),
        models.Story.publication_status == "approved",
        models.Story.is_test_content.is_(False),
    ).order_by(models.Story.is_pinned.desc(), models.Story.confidence_score.desc(), models.Story.created_at.asc()).all()


def _get_latest_approved_edition_date(db: Session, local_today: datetime.date) -> str | None:
    row = db.query(models.Story.edition_date).filter(
        models.Story.edition_date <= local_today.isoformat(),
        models.Story.is_published.is_(True),
        models.Story.publication_status == "approved",
        models.Story.is_test_content.is_(False),
    ).order_by(models.Story.edition_date.desc()).first()
    return row[0] if row else None


def _latest_approval_time(stories):
    timestamps = [getattr(s, "reviewed_at", None) or getattr(s, "created_at", None) for s in stories]
    timestamps = [t for t in timestamps if t is not None]
    return max(timestamps) if timestamps else None


def _already_delivered_current_content(db: Session, user_id: int, edition_date: str, stories, local_today: datetime.date, force: bool):
    last_log = db.query(models.EmailLog).filter(
        models.EmailLog.user_id == user_id,
        models.EmailLog.edition_date == edition_date,
        models.EmailLog.status == "sent",
    ).order_by(models.EmailLog.sent_at.desc()).first()
    if not last_log:
        return False
    newest_approval = _latest_approval_time(stories)
    sent_at = last_log.sent_at
    if newest_approval is not None and sent_at is not None and newest_approval > sent_at:
        return False
    if force:
        return sent_at is not None and sent_at.date() == local_today
    return True


def send_daily_emails(db: Session, force=False):
    """Send approved editions to eligible users.

    Scheduled delivery is fixed at 06:00 local time for every user. Users do
    not choose a delivery hour. Their timezone is retained so international
    readers still receive the briefing at 06:00 where they live.

    Manual `force=True` sends the newest approved edition immediately and is
    unaffected by the clock.
    """
    users = db.query(models.User).filter(
        models.User.is_active.is_(True), models.User.onboarded.is_(True), models.User.role == "user"
    ).all()
    sent = failed = skipped = 0
    skip_reasons = {"no_edition": 0, "already_delivered": 0, "outside_window": 0, "no_stories": 0, "no_personalized_stories": 0}

    for user in users:
        try:
            tz = zoneinfo.ZoneInfo(user.timezone)
        except Exception:
            tz = zoneinfo.ZoneInfo("UTC")
        local_today_date = datetime.datetime.now(tz).date()
        local_today = local_today_date.isoformat()
        edition_date = _get_latest_approved_edition_date(db, local_today_date) if force else local_today
        if not edition_date:
            skipped += 1; skip_reasons["no_edition"] += 1; continue
        stories = _get_approved_stories_for_edition(db, edition_date)
        if not stories:
            skipped += 1; skip_reasons["no_stories"] += 1; continue
        if _already_delivered_current_content(db, user.id, edition_date, stories, local_today_date, force):
            skipped += 1; skip_reasons["already_delivered"] += 1; continue
        if not force and not _is_users_send_time_now(user):
            skipped += 1; skip_reasons["outside_window"] += 1; continue

        selected, _ = select_personalized_stories(
            stories,
            user.country_code,
            {c.category_slug for c in user.categories},
            int(get_setting(db, "stories_per_edition", "8")),
            int(get_setting(db, "outside_bubble_min_stories", "1")),
        )
        if not selected:
            skipped += 1; skip_reasons["no_personalized_stories"] += 1; continue
        localized = [_localize_for_email(s, user.content_language) for s in selected]
        try:
            html = render_digest_email(localized, edition_date, settings.FRONTEND_URL, max_stories=len(localized))
            subject_prefix = "Your Morning Brief" if not force else "Your Morning Brief — Approved Edition"
            send_email(to_email=user.email, subject=f"{subject_prefix} — {edition_date}", html_content=html)
            user.last_sent_date = edition_date
            db.add(models.EmailLog(user_id=user.id, edition_date=edition_date, status="sent"))
            sent += 1
        except EmailSendError as exc:
            db.add(models.EmailLog(user_id=user.id, edition_date=edition_date, status="failed", error=str(exc)[:500])); failed += 1
        except Exception as exc:
            logger.exception("Unexpected email error for user %s", user.id)
            db.add(models.EmailLog(user_id=user.id, edition_date=edition_date, status="failed", error=str(exc)[:500])); failed += 1

    db.commit()
    return {"status": "ok", "sent": sent, "failed": failed, "skipped": skipped, "skip_reasons": skip_reasons}


def send_test_email(db: Session, test_recipient: str, language: str = "en"):
    today = datetime.date.today()
    edition_date = _get_latest_approved_edition_date(db, today)
    if not edition_date:
        return {"status": "skipped", "detail": "No approved production stories are available yet"}
    stories = _get_approved_stories_for_edition(db, edition_date)
    if not stories:
        return {"status": "skipped", "detail": "No approved production stories are available yet"}
    localized = [_localize_for_email(s, language) for s in stories[:int(get_setting(db, "stories_per_edition", "8"))]]
    try:
        html = render_digest_email(localized, edition_date, settings.FRONTEND_URL, max_stories=len(localized))
        send_email(to_email=test_recipient, subject=f"[TEST] Your Morning Brief — {edition_date}", html_content=html)
        return {"status": "ok", "detail": f"Test email sent to {test_recipient} using approved edition {edition_date}"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)[:500]}