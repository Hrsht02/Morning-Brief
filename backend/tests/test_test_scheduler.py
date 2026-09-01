import datetime

from app.services.test_scheduler import _parse_target, get_test_schedule, run_due_test_email, schedule_test_email


class FakeDB:
    def __init__(self, values=None):
        self.values = values or {}
        self.commits = 0

    def commit(self):
        self.commits += 1


def test_parse_target_normalizes_to_utc():
    target = _parse_target("2026-09-01T06:00:00+05:30")
    assert target == datetime.datetime(2026, 9, 1, 0, 30, tzinfo=datetime.timezone.utc)


def test_parse_target_rejects_invalid_value():
    assert _parse_target("not-a-time") is None
    assert _parse_target(None) is None


def test_schedule_requires_test_recipient(monkeypatch):
    db = FakeDB({"developer_test_email": "", "admin_timezone": "Asia/Kolkata"})
    monkeypatch.setattr("app.services.test_scheduler.get_setting", lambda db, key, default="": db.values.get(key, default))
    result = schedule_test_email(db, 12, 0)
    assert result["status"] == "error"
    assert result["safe"] is True


def test_run_due_is_idle_without_schedule(monkeypatch):
    db = FakeDB({"sandbox_test_email_enabled": "false"})
    monkeypatch.setattr("app.services.test_scheduler.get_setting", lambda db, key, default="": db.values.get(key, default))
    result = run_due_test_email(db, datetime.datetime.now(datetime.timezone.utc))
    assert result == {"status": "idle", "sent": False, "safe": True}


def test_schedule_status_is_safe(monkeypatch):
    db = FakeDB({"sandbox_test_email_enabled": "true", "sandbox_test_email_scheduled_at": "2026-09-01T06:00:00+00:00", "developer_test_email": "test@example.com"})
    monkeypatch.setattr("app.services.test_scheduler.get_setting", lambda db, key, default="": db.values.get(key, default))
    result = get_test_schedule(db)
    assert result["enabled"] is True
    assert result["safe"] is True
    assert result["one_shot"] is True
