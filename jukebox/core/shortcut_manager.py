"""Keyboard shortcut management."""

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget


class ShortcutManager(QObject):
    """Manage keyboard shortcuts for the application."""

    def __init__(self, parent: QWidget):
        """Initialize shortcut manager.

        Args:
            parent: Parent widget (typically MainWindow)
        """
        super().__init__(parent)
        self.parent_widget = parent
        self.shortcuts: dict[str, QShortcut] = {}
        self.shortcut_owners: dict[str, str] = {}  # key_sequence -> plugin_name

    def register(
        self, key_sequence: str, callback: Callable[[], None], plugin_name: str | None = None
    ) -> QShortcut:
        """Register a keyboard shortcut.

        Args:
            key_sequence: Key sequence (e.g., "Ctrl+P", "Space")
            callback: Function to call when shortcut is activated
            plugin_name: Optional plugin name (for mode-based enable/disable)

        Returns:
            The created QShortcut instance
        """
        # Unregister existing shortcut with same key sequence
        if key_sequence in self.shortcuts:
            self.unregister(key_sequence)

        shortcut = QShortcut(QKeySequence(key_sequence), self.parent_widget)
        shortcut.activated.connect(callback)
        self.shortcuts[key_sequence] = shortcut

        if plugin_name:
            self.shortcut_owners[key_sequence] = plugin_name

        return shortcut

    def unregister(self, key_sequence: str) -> bool:
        """Unregister a keyboard shortcut.

        Args:
            key_sequence: Key sequence to unregister

        Returns:
            True if shortcut was unregistered, False if not found
        """
        if key_sequence not in self.shortcuts:
            return False

        shortcut = self.shortcuts[key_sequence]
        shortcut.setEnabled(False)
        shortcut.deleteLater()
        del self.shortcuts[key_sequence]

        return True

    def is_registered(self, key_sequence: str) -> bool:
        """Check if a shortcut is registered.

        Args:
            key_sequence: Key sequence to check

        Returns:
            True if registered, False otherwise
        """
        return key_sequence in self.shortcuts

    def get_all_shortcuts(self) -> dict[str, QShortcut]:
        """Get all registered shortcuts.

        Returns:
            Dictionary mapping key sequences to QShortcut instances
        """
        return self.shortcuts.copy()

    def clear(self) -> None:
        """Clear all registered shortcuts."""
        for key_sequence in list(self.shortcuts.keys()):
            self.unregister(key_sequence)

    def enable_for_plugin(self, plugin_name: str) -> None:
        """Enable all shortcuts for a plugin.

        Args:
            plugin_name: Name of the plugin
        """
        for key_sequence, owner in self.shortcut_owners.items():
            if owner == plugin_name and key_sequence in self.shortcuts:
                self.shortcuts[key_sequence].setEnabled(True)
                logging.debug(f"Enabled shortcut {key_sequence} for {plugin_name}")

    def disable_for_plugin(self, plugin_name: str) -> None:
        """Disable all shortcuts for a plugin.

        Args:
            plugin_name: Name of the plugin
        """
        for key_sequence, owner in self.shortcut_owners.items():
            if owner == plugin_name and key_sequence in self.shortcuts:
                self.shortcuts[key_sequence].setEnabled(False)
                logging.debug(f"Disabled shortcut {key_sequence} for {plugin_name}")
