"""Theme switcher plugin."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from jukebox.ui.theme_manager import ThemeManager

if TYPE_CHECKING:
    from jukebox.core.protocols import (
        PluginContextProtocol,
        ShortcutManagerProtocol,
        UIBuilderProtocol,
    )


class ThemeSwitcherPlugin:
    """Plugin to switch between themes at runtime."""

    name = "theme_switcher"
    version = "1.0.0"
    description = "Switch between dark and light themes"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol | None = None
        self.current_theme: str = "dark"

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin."""
        self.context = context
        self.current_theme = context.config.ui.theme
        # Apply initial theme from config
        ThemeManager.apply_theme(self.current_theme)

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register theme switcher in menu."""
        menu = ui_builder.get_or_create_menu("&View")
        ui_builder.add_menu_action(menu, "Dark Theme", lambda: self._switch_theme("dark"))
        ui_builder.add_menu_action(menu, "Light Theme", lambda: self._switch_theme("light"))
        ui_builder.add_menu_separator(menu)
        ui_builder.add_menu_action(menu, "Toggle Theme", self._toggle_theme, shortcut="Ctrl+T")

    def register_shortcuts(self, shortcut_manager: ShortcutManagerProtocol) -> None:
        """Register keyboard shortcuts."""
        # Ctrl+T is already registered via menu action
        pass

    def _switch_theme(self, theme_name: str) -> None:
        """Switch to a specific theme."""
        if ThemeManager.apply_theme(theme_name):
            self.current_theme = theme_name
            logging.info(f"Switched to {theme_name} theme")

    def _toggle_theme(self) -> None:
        """Toggle between dark and light themes."""
        new_theme = "light" if self.current_theme == "dark" else "dark"
        self._switch_theme(new_theme)

    def shutdown(self) -> None:
        """Cleanup on application exit. No cleanup needed for this plugin."""
        ...
