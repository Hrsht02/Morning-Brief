import datetime
from app.services import schedule_service

class FakeDB:
    def __init__(self, values=None): self.values = values or {}; self.commits = 0
    def commit(self): self.commits += 1

def patch_settings(monkeypatch):
    monkeypatch.setattr(schedule_service, "get_setting", lambda db, key, default="": db.values.get(key, default))
    def set_value(db, key, value, description=""): db.values[key] = value
    monkeypatch.setattr(schedule_service, "set_setting", set_value)

def test_daily_schedule_calculates_next_run(monkeypatch):
    patch_settings(monkeypatch); db = FakeDB({"admin_timezone": "Asia/Kolkata"})
    monkeypatch.setattr(schedule_service, "_now_utc", lambda: datetime.datetime(2026, 9, 3, 10, 0, tzinfo=datetime.timezone.utc))
    result = schedule_service.configure_schedule(db, "email", frequency="daily", date=None, time="20:00")
    assert result["enabled"] is True and result["frequency"] == "daily" and result["time"] == "20:00"
    assert result["next_run_at"].startswith("2026-09-03T14:30:00")

def test_one_time_schedule_requires_date(monkeypatch):
    patch_settings(monkeypatch); db = FakeDB({"admin_timezone": "Asia/Kolkata"})
    try: schedule_service.configure_schedule(db, "email", frequency="once", date=None, time="20:00"); assert False, "expected ValueError"
    except ValueError as exc: assert "date" in str(exc).lower()

def test_claim_advances_daily_schedule(monkeypatch):
    patch_settings(monkeypatch); db = FakeDB({"admin_timezone": "Asia/Kolkata"})
    monkeypatch.setattr(schedule_service, "_now_utc", lambda: datetime.datetime(2026, 9, 3, 14, 31, tzinfo=datetime.timezone.utc))
    schedule_service.configure_schedule(db, "email", frequency="daily", date=None, time="20:00")
    claimed = schedule_service.claim_due(db, "email", datetime.datetime(2026, 9, 4, 15, 0, tzinfo=datetime.timezone.utc))
    assert claimed is not None and claimed["last_status"] == "in_progress"
    assert claimed["next_run_at"].startswith("2026-09-05T14:30:00")

def test_ingestion_cutoff_uses_specific_datetime(monkeypatch):
    patch_settings(monkeypatch); db = FakeDB({"admin_timezone": "Asia/Kolkata"})
    schedule = {"freshness_mode": "after_datetime", "freshness_after": "2026-09-03T18:00:00+05:30"}
    cutoff = schedule_service.ingestion_cutoff(db, schedule)
    assert cutoff == datetime.datetime(2026, 9, 3, 12, 30, tzinfo=datetime.timezone.utc)
