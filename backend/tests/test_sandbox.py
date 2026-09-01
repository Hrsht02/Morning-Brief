from app.routers.sandbox import _check, _setting_bool


def test_check_returns_boolean_result():
    assert _check("x", True, "ok") == {"name": "x", "passed": True, "detail": "ok"}
    assert _check("x", 0, "bad")["passed"] is False


def test_setting_bool_parsing(db=None):
    class Setting:
        def __init__(self, value):
            self.value = value

    class FakeQuery:
        def __init__(self, value):
            self.value = value
        def filter(self, *args, **kwargs):
            return self
        def first(self):
            return Setting(self.value)

    class FakeDB:
        def __init__(self, value): self.value = value
        def query(self, *args): return FakeQuery(self.value)

    # This test intentionally targets the helper contract indirectly through
    # a minimal fake DB; no real database or provider is contacted.
    from app.routers import sandbox
    original = sandbox.get_setting
    try:
        sandbox.get_setting = lambda db, key, default: "true"
        assert _setting_bool(FakeDB("true"), "anything") is True
        sandbox.get_setting = lambda db, key, default: "false"
        assert _setting_bool(FakeDB("false"), "anything", True) is False
    finally:
        sandbox.get_setting = original
