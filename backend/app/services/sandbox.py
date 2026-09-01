"""Pure helpers used by the admin production sandbox.

Keep decision logic here so it can be unit-tested without a live database,
email provider, or scheduler side effects.
"""
from __future__ import annotations

import datetime
import zoneinfo


def setting_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def local_send_window(now_utc: datetime.datetime, timezone_name: str | None, hour: int, minute: int, window_minutes: int = 60):
    """Return local time and whether the current time is in the scheduler window.

    The production sender uses a one-sided window: from the configured send time
    up to ``window_minutes`` afterwards. This helper deliberately mirrors that
    behavior rather than using an absolute +/- window.
    """
    try:
        tz = zoneinfo.ZoneInfo(timezone_name or "UTC")
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")
    local_now = now_utc.astimezone(tz)
    target = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    elapsed_minutes = (local_now - target).total_seconds() / 60
    return local_now, 0 <= elapsed_minutes < window_minutes


def email_eligibility(*, in_send_window: bool, already_sent: bool, candidate_count: int, selected_count: int):
    """Return a deterministic explanation of automatic-email eligibility."""
    if already_sent:
        return False, "already_delivered"
    if not in_send_window:
        return False, "outside_send_window"
    if candidate_count <= 0:
        return False, "no_approved_stories"
    if selected_count <= 0:
        return False, "no_personalized_stories"
    return True, "would_send"


def limit_value(raw, default=10, minimum=1, maximum=50):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))
