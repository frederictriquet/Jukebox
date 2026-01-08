"""UI builder API for plugins."""

from collections.abc import Callable
from typing import Any, cast

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QToolBar, QWidget


class UIBuilder:
    """API for plugins to inject UI elements."""

    def __init__(self, main_window: Any):
        """Initialize UI builder."""
        self.main_window = main_window

    def add_menu(self, name: str) -> QMenu:
        """Add menu to menubar."""
        return cast(QMenu, self.main_window.menuBar().addMenu(name))

    def add_menu_action(
        self, menu: QMenu, text: str, callback: Callable[[], None], shortcut: str | None = None
    ) -> QAction:
        """Add action to menu."""
        action = QAction(text, self.main_window)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(shortcut)
        menu.addAction(action)
        return action

    def add_toolbar_widget(self, widget: QWidget) -> None:
        """Add widget to toolbar."""
        if not hasattr(self.main_window, "_plugin_toolbar"):
            self.main_window._plugin_toolbar = QToolBar("Plugins")
            self.main_window.addToolBar(self.main_window._plugin_toolbar)
        self.main_window._plugin_toolbar.addWidget(widget)
