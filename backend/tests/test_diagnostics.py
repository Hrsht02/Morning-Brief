import datetime
from types import SimpleNamespace

from app.services.test_scheduler import _parse_target


def test_parse_target_normalizes_timezone():
    result = _parse_target("2026-09-01T09:00:00+05:30")
    assert result == datetime.datetime(2026, 9, 1, 3, 30, tzinfo=datetime.timezone.utc)


def test_parse_target_invalid_returns_none():
    assert _parse_target("not-a-time") is None
