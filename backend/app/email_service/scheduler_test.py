"""Safe production-scheduler email test.

This module is an application helper, not a pytest test module. The filename is
kept for backwards compatibility with the existing admin endpoint, while the
callable intentionally does not start with ``test_`` so pytest will not execute
it as a test requiring a database fixture or send email during CI.
"""
import datetime
import zoneinfo
from sqlalchemy.orm import Session
from .. import models
from ..seed import get_setting
from ..services.personalization import select_personalized_stories
from .brevo_client import send_email, render_digest_email
from .sender import _get_approved_stories_for_edition, _is_users_send_time_now, _localize_for_email
from ..config import settings


def run_automatic_email_test(db: Session, test_recipient: str | None = None):
    """Safely exercise automatic-email eligibility using a test recipient only."""
    if get_setting(db, "scheduling_mode", "auto") != "auto":
        return {"status": "skipped", "reason": "scheduling_mode is 'manual'", "would_send": False}

    recipient = (test_recipient or get_setting(db, "developer_test_email", "")).strip()
    if not recipient:
        return {"status": "error", "reason": "Set developer_test_email in Admin -> Settings first", "would_send": False}

    users = db.query(models.User).filter(
        models.User.is_active.is_(True),
        models.User.onboarded.is_(True),
        models.User.role == "user",
    ).order_by(models.User.id.asc()).all()
    if not users:
        return {"status": "skipped", "reason": "No active onboarded subscriber users", "would_send": False}

    candidates = []
    for user in users:
        try:
            tz = zoneinfo.ZoneInfo(user.timezone)
        except Exception:
            tz = zoneinfo.ZoneInfo("UTC")
        local_today = datetime.datetime.now(tz).date()
        edition_date = local_today.isoformat()
        stories = _get_approved_stories_for_edition(db, edition_date)
        if not stories:
            continue
        if not _is_users_send_time_now(user, window_minutes=60):
            continue
        candidates.append((user, stories, edition_date))

    if not candidates:
        return {
            "status": "skipped",
            "would_send": False,
            "reason": "No subscriber is currently inside their configured automatic send window with an approved edition",
            "checked_users": len(users),
            "send_window": "06:00-07:00 local by default",
        }

    user, stories, edition_date = candidates[0]
    selected, resolution = select_personalized_stories(
        stories,
        user.country_code,
        {c.category_slug for c in user.categories},
        int(get_setting(db, "stories_per_edition", "8")),
        int(get_setting(db, "outside_bubble_min_stories", "1")),
    )
    if not selected:
        return {"status": "skipped", "would_send": False, "reason": "Automatic personalization produced no eligible stories"}

    localized = [_localize_for_email(s, user.content_language) for s in selected]
    html = render_digest_email(localized, edition_date, settings.FRONTEND_URL, max_stories=len(localized))
    send_email(
        to_email=recipient,
        subject=f"[SCHEDULER TEST] Morning Brief — {edition_date}",
        html_content=html,
    )
    return {
        "status": "ok",
        "would_send": True,
        "test_recipient": recipient,
        "simulated_user_id": user.id,
        "simulated_user_timezone": user.timezone,
        "simulated_send_time": f"{user.send_hour:02d}:{user.send_minute:02d}",
        "edition_date": edition_date,
        "stories_sent": len(localized),
        "effective_country": resolution.effective,
        "note": "This was a safe scheduler test. No real subscriber was emailed and no delivery state was changed.",
    }
