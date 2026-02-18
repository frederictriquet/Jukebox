"""Mode switcher plugin for jukebox vs curating modes."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel

from jukebox.core.event_bus import Events
from jukebox.core.mode_manager import AppMode, ModeManager

if TYPE_CHECKING:
    from jukebox.core.protocols import (
        PluginContextProtocol,
        ShortcutManagerProtocol,
        UIBuilderProtocol,
    )


class ModeSwitcherPlugin:
    """Plugin to switch between jukebox, curating, and cue maker modes."""

    name = "mode_switcher"
    version = "1.0.0"
    description = "Switch between application modes"
    modes = ["jukebox", "curating", "cue_maker"]  # Active in all modes

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol | None = None
        self.mode_manager: ModeManager | None = None
        self.jukebox_action: Any = None
        self.curating_action: Any = None
        self.cue_maker_action: Any = None

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin."""
        self.context = context

        # Create mode manager and store in app context
        initial_mode_str = getattr(context.config.ui, "mode", "jukebox")
        if initial_mode_str == "jukebox":
            initial_mode = AppMode.JUKEBOX
        elif initial_mode_str == "curating":
            initial_mode = AppMode.CURATING
        elif initial_mode_str == "cue_maker":
            initial_mode = AppMode.CUE_MAKER
        else:
            initial_mode = AppMode.JUKEBOX

        self.mode_manager = ModeManager(initial_mode)
        context.app.mode_manager = self.mode_manager

        # Connect to mode changes
        self.mode_manager.mode_changed.connect(self._on_mode_changed)

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register mode switcher in menu."""
        menu = ui_builder.get_or_create_menu("&Settings")

        # Create checkable actions for modes
        self.jukebox_action = ui_builder.add_menu_action(
            menu, "Jukebox Mode", lambda: self._set_mode(AppMode.JUKEBOX)
        )
        self.jukebox_action.setCheckable(True)

        self.curating_action = ui_builder.add_menu_action(
            menu, "Curating Mode", lambda: self._set_mode(AppMode.CURATING)
        )
        self.curating_action.setCheckable(True)

        self.cue_maker_action = ui_builder.add_menu_action(
            menu, "Cue Maker Mode", lambda: self._set_mode(AppMode.CUE_MAKER)
        )
        self.cue_maker_action.setCheckable(True)

        # Set initial check based on current mode
        if self.mode_manager:
            self._update_menu_checks(self.mode_manager.get_mode())

        ui_builder.add_menu_separator(menu)
        ui_builder.add_menu_action(menu, "Toggle Mode", self._toggle_mode, shortcut="Ctrl+M")

    def _set_mode(self, mode: AppMode) -> None:
        """Set application mode."""
        if self.mode_manager:
            self.mode_manager.set_mode(mode)

    def _toggle_mode(self) -> None:
        """Toggle between modes."""
        if self.mode_manager:
            self.mode_manager.toggle_mode()

    def _update_menu_checks(self, mode: AppMode) -> None:
        """Update menu checkmarks to reflect current mode."""
        if self.jukebox_action:
            self.jukebox_action.setChecked(mode == AppMode.JUKEBOX)
        if self.curating_action:
            self.curating_action.setChecked(mode == AppMode.CURATING)
        if self.cue_maker_action:
            self.cue_maker_action.setChecked(mode == AppMode.CUE_MAKER)

    def _on_mode_changed(self, mode: AppMode) -> None:
        """Handle mode change and reload plugins."""
        logging.info(f"Switching to {mode.value} mode...")

        # Update menu checks
        self._update_menu_checks(mode)

        main_window = self.context.app

        # Update config with new mode
        self.context.config.ui.mode = mode.value

        # Create overlay to hide transition
        overlay = QLabel(main_window)
        overlay.setStyleSheet("background-color: #1e1e1e; color: #ffffff; font-size: 16px;")
        overlay.setGeometry(0, 0, main_window.width(), main_window.height())
        overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay.raise_()
        overlay.show()

        # Process events to ensure overlay is visible before starting cleanup
        QApplication.processEvents()

        # Disable updates
        main_window.setUpdatesEnabled(False)

        try:
            # Stop current playback and unload track
            main_window.player.unload()
            main_window.playback.stop()

            # Reset window title
            main_window.setWindowTitle(main_window.config.ui.window_title)

            # Clear waveform
            main_window.event_bus.emit(Events.WAVEFORM_CLEAR)

            # Switch mode (plugins stay loaded, just activate/deactivate)
            # Event subscriptions remain active
            main_window.plugin_manager.switch_mode(mode.value)

            # Update track list display mode (jukebox: artist-title, curating: filename)
            main_window.track_list.set_mode(mode.value)

            # Reload tracks for new mode (apply search if active)
            search_query = main_window.search_bar.text().strip()
            if search_query:
                main_window._perform_search(search_query)
            else:
                main_window._load_tracks_from_db()

            logging.info(f"Switched to {mode.value} mode")

        finally:
            # Re-enable updates
            main_window.setUpdatesEnabled(True)

            # Force complete repaint before removing overlay
            QApplication.processEvents()
            main_window.update()

            # Small delay then remove overlay
            QTimer.singleShot(50, overlay.deleteLater)

    def register_shortcuts(self, shortcut_manager: ShortcutManagerProtocol) -> None:
        """Register keyboard shortcuts."""
        # Ctrl+M is already registered via menu action
        pass

    def activate(self, mode: str) -> None:
        """Activate plugin for this mode."""
        # Mode switcher always active
        pass

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for this mode."""
        # Mode switcher always active
        pass

    def shutdown(self) -> None:
        """Cleanup on application exit. No cleanup needed for this plugin."""
        ...
