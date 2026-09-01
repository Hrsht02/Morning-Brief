import datetime
from types import SimpleNamespace

from app.email_service.sender import _is_users_send_time_now


def _user(timezone):
    return SimpleNamespace(timezone=timezone, send_hour=23, send_minute=59)


def test_fixed_delivery_ignores_user_selected_time(monkeypatch):
    class FakeDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 1, 6, 30, tzinfo=tz)

    monkeypatch.setattr("app.email_service.sender.datetime.datetime", FakeDateTime)
    assert _is_users_send_time_now(_user("Asia/Kolkata")) is True


def test_fixed_delivery_is_outside_window_after_seven(monkeypatch):
    class FakeDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 1, 7, 1, tzinfo=tz)

    monkeypatch.setattr("app.email_service.sender.datetime.datetime", FakeDateTime)
    assert _is_users_send_time_now(_user("Asia/Kolkata")) is False
