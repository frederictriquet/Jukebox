"""Mixin for plugins that use keyboard shortcuts."""

import logging
from typing import Any


class ShortcutMixin:
    """Mixin that provides shortcut management for plugins.

    Provides common functionality for:
    - Registering shortcuts with the shortcut manager
    - Unregistering and re-registering shortcuts on settings change
    - Enabling/disabling shortcuts on mode activation/deactivation

    Subclasses must:
    - Call `_init_shortcut_mixin()` in their `__init__`
    - Implement `_register_plugin_shortcuts()` to register their specific shortcuts
    - Optionally implement `_reload_plugin_config()` to reload config from database

    Attributes:
        shortcuts: List of registered QShortcut objects
        shortcut_manager: Reference to the shortcut manager
    """

    # Type hints for attributes that should be defined by the plugin class
    context: Any
    name: str

    def _init_shortcut_mixin(self) -> None:
        """Initialize shortcut mixin attributes. Call this in plugin __init__."""
        self.shortcuts: list[Any] = []
        self.shortcut_manager: Any = None

    def register_shortcuts(self, shortcut_manager: Any) -> None:
        """Register shortcuts with the manager.

        Args:
            shortcut_manager: The shortcut manager instance
        """
        self.shortcut_manager = shortcut_manager
        self._register_all_shortcuts()

    def _register_all_shortcuts(self) -> None:
        """Register all shortcuts. Calls the plugin-specific implementation."""
        if not self.shortcut_manager:
            return
        self._register_plugin_shortcuts()

    def _register_plugin_shortcuts(self) -> None:
        """Register plugin-specific shortcuts. Override in subclass."""
        raise NotImplementedError("Subclass must implement _register_plugin_shortcuts()")

    def _on_settings_changed(self) -> None:
        """Reload shortcuts when settings change."""
        logging.info(f"[{self.name}] Reloading shortcuts after settings change")

        # Unregister all current shortcuts
        self._unregister_all_shortcuts()

        # Reload config from database (if implemented)
        self._reload_plugin_config()

        # Re-register shortcuts with new config
        self._register_all_shortcuts()

    def _unregister_all_shortcuts(self) -> None:
        """Unregister all registered shortcuts."""
        for shortcut in self.shortcuts:
            if hasattr(shortcut, "key"):
                key_seq = shortcut.key().toString()
                if self.shortcut_manager:
                    self.shortcut_manager.unregister(key_seq)
        self.shortcuts.clear()

    def _reload_plugin_config(self) -> None:
        """Reload plugin config from database. Override in subclass if needed."""
        pass

    def _activate_shortcuts(self) -> None:
        """Enable all shortcuts."""
        for shortcut in self.shortcuts:
            shortcut.setEnabled(True)

    def _deactivate_shortcuts(self) -> None:
        """Disable all shortcuts."""
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
