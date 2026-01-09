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

    def add_sidebar_widget(self, widget: QWidget, title: str) -> None:
        """Add widget to sidebar (dock widget)."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QDockWidget

        dock = QDockWidget(title, self.main_window)
        dock.setWidget(widget)
        self.main_window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def add_bottom_widget(self, widget: QWidget) -> None:
        """Add widget at bottom of main layout."""
        # Access main layout and add widget at bottom
        if hasattr(self.main_window, "centralWidget"):
            central = self.main_window.centralWidget()
            if central and central.layout():
                central.layout().addWidget(widget)
