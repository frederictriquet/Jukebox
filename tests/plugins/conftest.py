"""Shared helpers for plugin configuration tests."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock


class FakeSettingsStore:
    """In-memory replacement for the plugin_settings DB table."""

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def get(self, plugin_name: str, key: str) -> str | None:
        return self._data.get((plugin_name, key))

    def save(self, plugin_name: str, key: str, value: str) -> None:
        self._data[(plugin_name, key)] = value


def make_plugin_context(
    config: MagicMock | None = None,
    store: FakeSettingsStore | None = None,
) -> MagicMock:
    """Build a mock PluginContext wired to a FakeSettingsStore."""
    store = store or FakeSettingsStore()
    context = MagicMock()
    context.config = config or MagicMock()

    context.database.settings.get.side_effect = store.get
    context.database.settings.save.side_effect = store.save
    context.database.get_plugin_setting.side_effect = (
        lambda plugin_name, key: store.get(plugin_name, key)
    )

    def get_setting(
        plugin_name: str, key: str, value_type: type, default=None,  # type: ignore[assignment]
    ):  # type: ignore[return]
        value = store.get(plugin_name, key)
        if value is None:
            return default
        if value_type is bool:
            return value.lower() in ("true", "1", "yes")
        return value_type(value)

    context.get_setting = get_setting
    return context


def make_plugin(
    module_path: str,
    class_name: str,
    config_attr: str,
    config_class: type,
    yaml_kwargs: dict | None = None,
    db_settings: dict[str, str] | None = None,
    register_shortcuts: bool = True,
) -> tuple:
    """Generic factory: create any plugin with yaml config + optional DB overrides.

    For ShortcutMixin plugins, register_shortcuts() is called automatically
    unless register_shortcuts=False (useful for timing-gap tests).

    Returns:
        (plugin, store) tuple.
    """
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    plugin = cls()

    store = FakeSettingsStore()
    for k, v in (db_settings or {}).items():
        store.save(plugin.name, k, v)

    config = MagicMock()
    setattr(config, config_attr, config_class(**(yaml_kwargs or {})))

    context = make_plugin_context(config, store)
    plugin.initialize(context)

    if register_shortcuts and hasattr(plugin, "register_shortcuts"):
        sm = MagicMock()
        sm.register.return_value = MagicMock()
        plugin.register_shortcuts(sm)

    return plugin, store


def make_shortcut_manager() -> MagicMock:
    """Create a mock ShortcutManager with register() returning a mock."""
    sm = MagicMock()
    sm.register.return_value = MagicMock()
    return sm
