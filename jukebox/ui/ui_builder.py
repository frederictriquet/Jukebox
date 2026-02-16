"""UI builder API for plugins."""

from collections.abc import Callable
from typing import Any, cast

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QToolBar, QWidget


class ContextMenuAction:
    """A context menu action registered by a plugin."""

    def __init__(
        self,
        text: str,
        callback: Callable[[dict[str, Any]], None],
        icon: str | None = None,
        separator_before: bool = False,
    ):
        """Initialize context menu action.

        Args:
            text: Action text displayed in menu
            callback: Function called with track dict when action is triggered
            icon: Optional icon name
            separator_before: Add separator before this action
        """
        self.text = text
        self.callback = callback
        self.icon = icon
        self.separator_before = separator_before


class UIBuilder:
    """API for plugins to inject UI elements."""

    def __init__(self, main_window: Any):
        """Initialize UI builder."""
        self.main_window = main_window
        self.plugin_menus: list[QMenu] = []
        self.plugin_widgets: list[QWidget] = []  # Track all widgets added by plugins
        self.shared_menus: dict[str, QMenu] = {}  # Keep references to shared menus
        self.track_context_actions: list[ContextMenuAction] = []  # Track context menu actions

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
                    return cast(QMenu, menu)

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

    def add_left_sidebar_widget(self, widget: QWidget, title: str) -> None:
        """Add widget to left sidebar (dock widget) and track it."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QDockWidget

        dock = QDockWidget(title, self.main_window)
        dock.setWidget(widget)
        self.main_window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
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

    def add_track_context_action(
        self,
        text: str,
        callback: Callable[[dict[str, Any]], None],
        icon: str | None = None,
        separator_before: bool = False,
    ) -> ContextMenuAction:
        """Add an action to the track list context menu.

        Args:
            text: Action text displayed in menu
            callback: Function called with track dict when action is triggered.
                     The track dict contains: id, filepath, filename, title, artist, etc.
            icon: Optional icon name
            separator_before: Add separator before this action

        Returns:
            The created ContextMenuAction

        Example:
            def on_analyze(track):
                print(f"Analyzing {track['filepath']}")

            ui_builder.add_track_context_action("Analyze Track", on_analyze)
        """
        action = ContextMenuAction(text, callback, icon, separator_before)
        self.track_context_actions.append(action)
        return action

    def get_track_context_actions(self) -> list[ContextMenuAction]:
        """Get all registered track context menu actions."""
        return self.track_context_actions

    def clear_track_context_actions(self) -> None:
        """Clear all track context menu actions."""
        self.track_context_actions.clear()
