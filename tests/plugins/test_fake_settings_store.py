"""Tests for FakeSettingsStore and mock context wiring.

Plugin config-priority tests are in test_db_config_priority.py.
This file tests the test infrastructure itself (FakeSettingsStore, get_setting mock).
"""

from .conftest import FakeSettingsStore, make_plugin_context


class TestConfManagerSaveMechanics:
    """Verify DB operations via FakeSettingsStore."""

    def test_save_then_read_roundtrip(self) -> None:
        store = FakeSettingsStore()
        context = make_plugin_context(store=store)

        context.database.settings.save("test_plugin", "key1", "value1")

        assert store.get("test_plugin", "key1") == "value1"

    def test_get_returns_none_when_missing(self) -> None:
        store = FakeSettingsStore()
        context = make_plugin_context(store=store)

        result = context.database.settings.get("test_plugin", "nonexistent")
        assert result is None

    def test_save_overwrites_previous_value(self) -> None:
        store = FakeSettingsStore()
        context = make_plugin_context(store=store)

        context.database.settings.save("p", "k", "v1")
        context.database.settings.save("p", "k", "v2")

        assert store.get("p", "k") == "v2"

    def test_get_setting_converts_types(self) -> None:
        store = FakeSettingsStore()
        store.save("p", "int_val", "42")
        store.save("p", "float_val", "3.14")
        store.save("p", "bool_true", "true")
        store.save("p", "bool_false", "false")

        context = make_plugin_context(store=store)

        assert context.get_setting("p", "int_val", int) == 42
        assert context.get_setting("p", "float_val", float) == 3.14
        assert context.get_setting("p", "bool_true", bool) is True
        assert context.get_setting("p", "bool_false", bool) is False

    def test_get_setting_returns_default_when_missing(self) -> None:
        store = FakeSettingsStore()
        context = make_plugin_context(store=store)

        assert context.get_setting("p", "missing", int, 99) == 99
        assert context.get_setting("p", "missing", str, "fallback") == "fallback"
