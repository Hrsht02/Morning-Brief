import datetime

from app.services.sandbox import email_eligibility, limit_value, local_send_window, setting_bool
from app.routers.sandbox import _check


def test_check_returns_boolean_result():
    assert _check("x", True, "ok") == {"name": "x", "passed": True, "detail": "ok"}
    assert _check("x", 0, "bad")["passed"] is False


def test_setting_bool_parsing():
    assert setting_bool("true") is True
    assert setting_bool("YES") is True
    assert setting_bool("off") is False
    assert setting_bool(None, default=True) is True


def test_limit_value_is_bounded():
    assert limit_value("10") == 10
    assert limit_value("0") == 1
    assert limit_value("999") == 50
    assert limit_value("bad", default=12) == 12


def test_local_send_window_is_timezone_aware():
    now = datetime.datetime(2026, 9, 1, 0, 30, tzinfo=datetime.timezone.utc)
    local_now, in_window = local_send_window(now, "Asia/Kolkata", 6, 0)
    assert local_now.hour == 6
    assert local_now.minute == 0
    assert in_window is True


def test_local_send_window_rejects_time_before_schedule():
    now = datetime.datetime(2026, 9, 1, 23, 0, tzinfo=datetime.timezone.utc)
    _, in_window = local_send_window(now, "Asia/Kolkata", 6, 0)
    assert in_window is False


def test_email_eligibility_explains_each_gate():
    assert email_eligibility(in_send_window=False, already_sent=False, candidate_count=10, selected_count=10) == (False, "outside_send_window")
    assert email_eligibility(in_send_window=True, already_sent=True, candidate_count=10, selected_count=10) == (False, "already_delivered")
    assert email_eligibility(in_send_window=True, already_sent=False, candidate_count=0, selected_count=0) == (False, "no_approved_stories")
    assert email_eligibility(in_send_window=True, already_sent=False, candidate_count=10, selected_count=0) == (False, "no_personalized_stories")
    assert email_eligibility(in_send_window=True, already_sent=False, candidate_count=10, selected_count=10) == (True, "would_send")
