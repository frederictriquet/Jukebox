"""Mode switcher plugin for jukebox vs curating modes."""

import logging
from typing import Any

from jukebox.core.mode_manager import AppMode, ModeManager


class ModeSwitcherPlugin:
    """Plugin to switch between jukebox and curating modes."""

    name = "mode_switcher"
    version = "1.0.0"
    description = "Switch between jukebox and curating modes"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None
        self.mode_manager: ModeManager | None = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

        # Create mode manager and store in app context
        initial_mode_str = getattr(context.config.ui, "mode", "jukebox")
        initial_mode = AppMode.JUKEBOX if initial_mode_str == "jukebox" else AppMode.CURATING

        self.mode_manager = ModeManager(initial_mode)
        context.app.mode_manager = self.mode_manager

        # Connect to mode changes
        self.mode_manager.mode_changed.connect(self._on_mode_changed)

    def register_ui(self, ui_builder: Any) -> None:
        """Register mode switcher in menu."""
        menu = ui_builder.add_menu("&Mode")

        ui_builder.add_menu_action(
            menu, "Jukebox Mode", lambda: self._set_mode(AppMode.JUKEBOX)
        )
        ui_builder.add_menu_action(
            menu, "Curating Mode", lambda: self._set_mode(AppMode.CURATING)
        )
        menu.addSeparator()
        ui_builder.add_menu_action(menu, "Toggle Mode", self._toggle_mode, shortcut="Ctrl+M")

    def _set_mode(self, mode: AppMode) -> None:
        """Set application mode."""
        if self.mode_manager:
            self.mode_manager.set_mode(mode)

    def _toggle_mode(self) -> None:
        """Toggle between modes."""
        if self.mode_manager:
            self.mode_manager.toggle_mode()

    def _on_mode_changed(self, mode: AppMode) -> None:
        """Handle mode change and reload plugins."""
        logging.info(f"Switching to {mode.value} mode...")

        main_window = self.context.app

        # Update config with new mode
        self.context.config.ui.mode = mode.value

        # Hide window to prevent visual flashing during rebuild
        was_visible = main_window.isVisible()
        if was_visible:
            main_window.hide()

        try:
            # Clear event bus subscribers from old plugins
            if hasattr(main_window, "event_bus"):
                main_window.event_bus.clear_all_subscribers()

            # Clear only plugin menus (not all menus)
            if hasattr(main_window, "ui_builder"):
                logging.info(f"Clearing {len(main_window.ui_builder.plugin_menus)} plugin menus")
                main_window.ui_builder.clear_plugin_menus()
            else:
                logging.warning("No ui_builder found in main_window")

            # Clear plugin toolbar if it exists
            if hasattr(main_window, "_plugin_toolbar"):
                main_window.removeToolBar(main_window._plugin_toolbar)
                main_window._plugin_toolbar.deleteLater()
                delattr(main_window, "_plugin_toolbar")

            # Clear widgets added by plugins (dock widgets, bottom widgets)
            from PySide6.QtWidgets import QDockWidget

            for dock in main_window.findChildren(QDockWidget):
                main_window.removeDockWidget(dock)
                dock.deleteLater()

            # Clear bottom widgets from main layout
            central = main_window.centralWidget()
            if central and central.layout():
                layout = central.layout()
                # Remove widgets added after player controls (index > 3)
                while layout.count() > 4:  # Keep toolbar, search, tracklist, controls
                    item = layout.takeAt(layout.count() - 1)
                    if item and item.widget():
                        item.widget().deleteLater()

            # Create new UIBuilder for new plugin set
            from jukebox.ui.ui_builder import UIBuilder

            main_window.ui_builder = UIBuilder(main_window)
            loaded = main_window.plugin_manager.reload_plugins_for_mode(
                mode.value, main_window.ui_builder
            )

            # Re-register shortcuts for new plugins
            if hasattr(main_window, "shortcut_manager"):
                for plugin in main_window.plugin_manager.get_all_plugins():
                    if hasattr(plugin, "register_shortcuts"):
                        plugin.register_shortcuts(main_window.shortcut_manager)

            # Re-emit current track loaded event if a track is playing
            if hasattr(main_window.player, "current_file") and main_window.player.current_file:
                # Find current track ID
                track = main_window.database.conn.execute(
                    "SELECT id FROM tracks WHERE filepath = ?",
                    (str(main_window.player.current_file),),
                ).fetchone()
                if track:
                    from jukebox.core.event_bus import Events

                    main_window.event_bus.emit(Events.TRACK_LOADED, track_id=track["id"])

            logging.info(f"Reloaded {loaded} plugins for {mode.value} mode")

        finally:
            # Show window if it was visible
            if was_visible:
                main_window.show()

    def register_shortcuts(self, shortcut_manager: Any) -> None:
        """Register keyboard shortcuts."""
        # Ctrl+M is already registered via menu action
        pass

    def shutdown(self) -> None:
        """Cleanup."""
        pass
