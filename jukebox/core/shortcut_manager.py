"""Keyboard shortcut management."""

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

    def register(self, key_sequence: str, callback: Callable[[], None]) -> None:
        """Register a keyboard shortcut.

        Args:
            key_sequence: Key sequence (e.g., "Ctrl+P", "Space")
            callback: Function to call when shortcut is activated
        """
        # Unregister existing shortcut with same key sequence
        if key_sequence in self.shortcuts:
            self.unregister(key_sequence)

        shortcut = QShortcut(QKeySequence(key_sequence), self.parent_widget)
        shortcut.activated.connect(callback)
        self.shortcuts[key_sequence] = shortcut

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
