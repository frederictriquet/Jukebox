"""Mixin for syncing plugin settings from DB to Pydantic config."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, ClassVar


@dataclass(frozen=True)
class SyncedSetting:
    """A scalar setting synced from DB to config.

    Attributes:
        db_key: Key used in the plugin_settings DB table.
        value_type: Type to convert the DB string to (int, float, bool, str).
        config_field: Config attribute name. Defaults to db_key if empty.
        transform: Optional post-read transform (e.g. ms -> seconds).
        default_fn: Optional function(config) -> default value for get_setting.
                     Use when the default needs conversion (e.g. seconds -> ms).
    """

    db_key: str
    value_type: type
    config_field: str = ""
    transform: Callable[[Any], Any] | None = None
    default_fn: Callable[[Any], Any] | None = None

    @property
    def field_name(self) -> str:
        return self.config_field or self.db_key


@dataclass(frozen=True)
class SyncedJsonList:
    """A JSON-serialized list setting synced from DB to config.

    Attributes:
        db_key: Key used in the plugin_settings DB table.
        config_field: Config attribute name for the list.
        model_class: Pydantic model class to instantiate each list item.
    """

    db_key: str
    config_field: str
    model_class: type


class SettingsSyncMixin:
    """Mixin that syncs plugin settings from the DB to the Pydantic config.

    Subclasses declare which settings to sync via class variables:
    - ``_synced_settings``: scalar fields (int, float, bool, str)
    - ``_synced_json_lists``: JSON-serialized lists of Pydantic models
    - ``_config_attr``: config attribute name (defaults to ``self.name``)

    Then call ``_sync_settings_from_db()`` wherever settings need reloading.
    Override ``_after_settings_sync(config)`` for post-update side effects.
    """

    # Required by the mixin (provided by the plugin class)
    context: Any
    name: str

    _synced_settings: ClassVar[list[SyncedSetting]] = []
    _synced_json_lists: ClassVar[list[SyncedJsonList]] = []
    _config_attr: ClassVar[str] = ""

    def _get_plugin_config(self) -> Any:
        """Return the plugin's Pydantic config object."""
        attr = self._config_attr or self.name
        return getattr(self.context.config, attr)

    def _sync_settings_from_db(self) -> None:
        """Read all declared settings from DB and update config."""
        config = self._get_plugin_config()

        for setting in self._synced_settings:
            if setting.default_fn:
                default = setting.default_fn(config)
            else:
                default = getattr(config, setting.field_name)

            value = self.context.get_setting(
                self.name, setting.db_key, setting.value_type, default
            )

            if setting.transform:
                value = setting.transform(value)

            setattr(config, setting.field_name, value)

        for jlist in self._synced_json_lists:
            raw = self.context.database.get_plugin_setting(self.name, jlist.db_key)
            if raw:
                try:
                    data = json.loads(raw)
                    setattr(
                        config,
                        jlist.config_field,
                        [jlist.model_class(**item) for item in data],
                    )
                except (json.JSONDecodeError, ValueError) as e:
                    logging.error(f"[{self.name}] Failed to parse {jlist.db_key}: {e}")

        self._after_settings_sync(config)

    def _after_settings_sync(self, config: Any) -> None:
        """Hook for post-sync side effects. Override in subclass."""
