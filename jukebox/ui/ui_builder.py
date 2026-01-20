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
        self.plugin_menus: list[QMenu] = []
        self.plugin_widgets: list[QWidget] = []  # Track all widgets added by plugins
        self.shared_menus: dict[str, QMenu] = {}  # Keep references to shared menus

    def add_menu(self, name: str) -> QMenu:
        """Add menu to menubar and track it."""
        menu = cast(QMenu, self.main_window.menuBar().addMenu(name))
        self.plugin_menus.append(menu)
        return menu

    def get_or_create_menu(self, name: str) -> QMenu:
        """Get existing menu or create new one.

        Args:
            name: Menu name (e.g., "&Settings")

        Returns:
            QMenu instance
        """
        # Check if we already created this menu
        if name in self.shared_menus:
            return self.shared_menus[name]

        # Check if menu already exists in menubar
        menubar = self.main_window.menuBar()
        for action in menubar.actions():
            if action.text() == name:
                menu = action.menu()
                if menu is not None:
                    # Store reference to prevent garbage collection
                    self.shared_menus[name] = menu
                    if menu not in self.plugin_menus:
                        self.plugin_menus.append(menu)
                    return menu

        # Create new menu and track it
        menu = cast(QMenu, menubar.addMenu(name))
        self.shared_menus[name] = menu
        self.plugin_menus.append(menu)
        return menu

    def clear_plugin_menus(self) -> None:
        """Clear all menus added by plugins."""
        menubar = self.main_window.menuBar()
        for menu in self.plugin_menus:
            menubar.removeAction(menu.menuAction())
            menu.deleteLater()
        self.plugin_menus.clear()

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

    def add_menu_separator(self, menu: QMenu) -> None:
        """Add separator to menu safely."""
        if menu is not None:
            menu.addSeparator()

    def add_toolbar_widget(self, widget: QWidget) -> None:
        """Add widget to toolbar and track it."""
        if not hasattr(self.main_window, "_plugin_toolbar"):
            self.main_window._plugin_toolbar = QToolBar("Plugins")
            self.main_window.addToolBar(self.main_window._plugin_toolbar)
        self.main_window._plugin_toolbar.addWidget(widget)
        self.plugin_widgets.append(widget)

    def add_sidebar_widget(self, widget: QWidget, title: str) -> None:
        """Add widget to sidebar (dock widget) and track it."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QDockWidget

        dock = QDockWidget(title, self.main_window)
        dock.setWidget(widget)
        self.main_window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.plugin_widgets.append(dock)

    def add_bottom_widget(self, widget: QWidget) -> None:
        """Add widget at bottom of main layout and track it."""
        # Access main layout and add widget at bottom
        central = self.main_window.centralWidget()
        if central and central.layout():
            central.layout().addWidget(widget)
            self.plugin_widgets.append(widget)

    def insert_widget_in_layout(self, layout: Any, index: int, widget: QWidget) -> None:
        """Insert widget in a layout at specific index and track it.

        Args:
            layout: QLayout to insert widget into
            index: Index to insert at
            widget: Widget to insert
        """
        layout.insertWidget(index, widget)
        self.plugin_widgets.append(widget)

    def clear_all_plugin_widgets(self) -> None:
        """Clear all widgets added by plugins."""
        for widget in self.plugin_widgets:
            # Remove widget from its parent layout first
            if widget.parent():
                parent = widget.parent()
                if hasattr(parent, "layout") and parent.layout():
                    parent.layout().removeWidget(widget)

            # Hide widget immediately before deletion
            widget.hide()
            widget.deleteLater()
        self.plugin_widgets.clear()
