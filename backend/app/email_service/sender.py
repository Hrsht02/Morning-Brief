"""
Orchestrates WHO gets emailed WHEN. Three modes:
  - Normal (cron) mode: only sends to users whose local send-time has just
    arrived, and never sends the same user twice in one day. Skipped entirely
    if scheduling_mode is "manual" (checked by the caller in routers/scheduler.py).
  - force=True (admin "send now" button): sends to every onboarded, active
    user immediately, ignoring the time-window check - useful for testing.
  - test_recipient=<email> (developer sandbox): sends ONE email, built from
    real approved content, to a single fixed address - never touches the
    real subscriber list at all.
"""
import datetime
import logging
import zoneinfo
from sqlalchemy.orm import Session, joinedload

from .. import models
from ..seed import get_setting
from .brevo_client import send_email, render_digest_email, EmailSendError
from ..config import settings

logger = logging.getLogger("morning_brief.email")


def _is_users_send_time_now(user: models.User, window_minutes: int = 30) -> bool:
    """True if it's currently within `window_minutes` after the user's chosen local send time."""
    try:
        tz = zoneinfo.ZoneInfo(user.timezone)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")  # fail safe rather than crash on a bad saved timezone

    now_local = datetime.datetime.now(tz)
    target = now_local.replace(hour=user.send_hour, minute=user.send_minute, second=0, microsecond=0)
    delta_minutes = (now_local - target).total_seconds() / 60
    return 0 <= delta_minutes < window_minutes


def _localize_for_email(story: models.Story, language: str) -> models.Story:
    """Same fallback-safe logic as the web edition - see routers/editions.py._localize
    for the full explanation. In-memory only, never committed."""
    if language == "hi" and story.headline_hi and story.summary_hi:
        story.headline = story.headline_hi
        story.hook = story.hook_hi or story.hook
        story.summary = story.summary_hi
    return story


def _get_todays_approved_stories(db: Session, today: str) -> list:
    return db.query(models.Story).options(joinedload(models.Story.citations)).filter(
        models.Story.edition_date == today,
        models.Story.is_published.is_(True),
        models.Story.publication_status == "approved",
        models.Story.is_test_content.is_(False),
    ).order_by(models.Story.is_pinned.desc(), models.Story.confidence_score.desc()).all()


def send_daily_emails(db: Session, force: bool = False) -> dict:
    today = datetime.date.today().isoformat()

    users = db.query(models.User).filter(
        models.User.is_active.is_(True),
        models.User.onboarded.is_(True),
    ).all()

    stories = _get_todays_approved_stories(db, today)

    if not stories:
        return {"status": "skipped", "detail": "No published stories for today yet", "sent": 0, "failed": 0}

    # Same "how many stories" setting the web edition uses, so the email and
    # the website always agree on what "today's edition" actually contains.
    stories_per_edition = int(get_setting(db, "stories_per_edition", "8"))

    sent, failed, skipped = 0, 0, 0

    for user in users:
        if user.last_sent_date == today and not force:
            skipped += 1
            continue
        if not force and not _is_users_send_time_now(user):
            skipped += 1
            continue

        # Personalize: preferred categories first, but keep it simple/robust
        user_categories = {c.category_slug for c in user.categories}
        if user_categories:
            personalized = [s for s in stories if s.category_slug in user_categories] or stories
        else:
            personalized = stories

        localized = [_localize_for_email(s, user.content_language) for s in personalized]

        try:
            html = render_digest_email(localized, today, settings.FRONTEND_URL, max_stories=stories_per_edition)
            send_email(
                to_email=user.email,
                subject=f"Your Morning Brief — {today}",
                html_content=html,
            )
            user.last_sent_date = today
            db.add(models.EmailLog(user_id=user.id, edition_date=today, status="sent"))
            sent += 1
        except EmailSendError as e:
            logger.warning(f"Email send failed for user {user.id}: {e}")
            db.add(models.EmailLog(user_id=user.id, edition_date=today, status="failed", error=str(e)[:500]))
            failed += 1
        except Exception as e:
            # Never let one bad user/email crash the whole batch job.
            logger.error(f"Unexpected error sending to user {user.id}: {e}")
            db.add(models.EmailLog(user_id=user.id, edition_date=today, status="failed", error=str(e)[:500]))
            failed += 1

    db.commit()
    return {"status": "ok", "sent": sent, "failed": failed, "skipped": skipped}


def send_test_email(db: Session, test_recipient: str, language: str = "en") -> dict:
    """
    Developer sandbox email: sends ONE email built from today's real approved
    stories to a single fixed address, completely independent of the real
    subscriber list, send-time windows, or per-user dedupe logic. Never
    touches EmailLog or any user's last_sent_date.
    """
    today = datetime.date.today().isoformat()
    stories = _get_todays_approved_stories(db, today)

    if not stories:
        return {"status": "skipped", "detail": "No published stories for today yet"}

    stories_per_edition = int(get_setting(db, "stories_per_edition", "8"))
    localized = [_localize_for_email(s, language) for s in stories]

    try:
        html = render_digest_email(localized, today, settings.FRONTEND_URL, max_stories=stories_per_edition)
        send_email(
            to_email=test_recipient,
            subject=f"[TEST] Your Morning Brief — {today}",
            html_content=html,
        )
        return {"status": "ok", "detail": f"Test email sent to {test_recipient}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)[:500]}
