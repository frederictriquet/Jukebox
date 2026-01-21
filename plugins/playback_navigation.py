"""Playback navigation plugin with keyboard shortcuts."""

from typing import Any

from jukebox.core.event_bus import Events


class PlaybackNavigationPlugin:
    """Navigate playback with keyboard shortcuts."""

    name = "playback_navigation"
    version = "1.0.0"
    description = "Playback navigation with keyboard shortcuts"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None
        self.last_seek_time: float = 0.0
        self.seek_multiplier: int = 1
        self.auto_play_next: bool = True
        self.random_mode: bool = False
        self.auto_play_action: Any = None
        self.random_action: Any = None
        self.auto_play_button: Any = None
        self.random_button: Any = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to track finished event
        context.player.track_finished.connect(self._on_track_finished)

    def register_ui(self, ui_builder: Any) -> None:
        """Register auto-play and random mode menu and buttons."""
        # Add menu options
        menu = ui_builder.add_menu("&Playback")

        from PySide6.QtGui import QAction

        self.auto_play_action = QAction("Auto-play Next Track", ui_builder.main_window)
        self.auto_play_action.setCheckable(True)
        self.auto_play_action.setChecked(self.auto_play_next)
        self.auto_play_action.triggered.connect(self._toggle_auto_play_from_menu)
        menu.addAction(self.auto_play_action)

        self.random_action = QAction("Random Mode", ui_builder.main_window)
        self.random_action.setCheckable(True)
        self.random_action.setChecked(self.random_mode)
        self.random_action.triggered.connect(self._toggle_random_from_menu)
        menu.addAction(self.random_action)

        # Add buttons in player controls (after stop button)
        from PySide6.QtWidgets import QPushButton

        main_window = self.context.app
        controls = main_window.controls
        if controls.layout():
            # Auto-play button
            self.auto_play_button = QPushButton("↻")
            self.auto_play_button.setCheckable(True)
            self.auto_play_button.setChecked(self.auto_play_next)
            self.auto_play_button.setToolTip("Auto-play next track")
            self.auto_play_button.setMaximumWidth(40)
            self.auto_play_button.clicked.connect(self._toggle_auto_play_from_button)

            # Random mode button
            self.random_button = QPushButton("🎲")
            self.random_button.setCheckable(True)
            self.random_button.setChecked(self.random_mode)
            self.random_button.setToolTip("Random mode")
            self.random_button.setMaximumWidth(40)
            self.random_button.clicked.connect(self._toggle_random_from_button)

            self._update_button_styles()

            layout = main_window.controls.layout()
            # Insert at index 3 (after stop button, before spacer)
            ui_builder.insert_widget_in_layout(layout, 3, self.auto_play_button)
            ui_builder.insert_widget_in_layout(layout, 4, self.random_button)

    def register_shortcuts(self, shortcut_manager: Any) -> None:
        """Register keyboard shortcuts."""
        shortcuts = self.context.config.shortcuts

        # Seek shortcuts
        shortcut_manager.register(shortcuts.seek_forward, self._seek_forward)
        shortcut_manager.register(shortcuts.seek_backward, self._seek_backward)

        # Track navigation
        shortcut_manager.register(shortcuts.next_track, self._next_track)
        shortcut_manager.register(shortcuts.previous_track, self._previous_track)
        shortcut_manager.register(shortcuts.skip_to_next, self._next_track)

        # Position jump shortcuts
        shortcut_manager.register(shortcuts.jump_20, lambda: self._jump_to_percent(0.2))
        shortcut_manager.register(shortcuts.jump_40, lambda: self._jump_to_percent(0.4))
        shortcut_manager.register(shortcuts.jump_60, lambda: self._jump_to_percent(0.6))
        shortcut_manager.register(shortcuts.jump_80, lambda: self._jump_to_percent(0.8))

    def _seek_forward(self) -> None:
        """Seek forward with acceleration (configurable base, multiplied if rapid presses)."""
        import time

        config = self.context.config.playback_navigation

        current_time = time.time()
        time_since_last = current_time - self.last_seek_time

        # If pressed within threshold, increase multiplier
        if time_since_last < config.rapid_press_threshold:
            self.seek_multiplier = min(self.seek_multiplier + 1, config.max_seek_multiplier)
        else:
            self.seek_multiplier = 1

        self.last_seek_time = current_time

        player = self.context.player
        if not (player.is_playing() or player.get_position() > 0):
            return

        duration = self._get_current_track_duration()
        if duration and duration > 0:
            current_pos = player.get_position()
            seek_amount = config.seek_amount * self.seek_multiplier
            new_time = (current_pos * duration) + seek_amount
            new_pos = min(new_time / duration, 1.0)
            player.set_position(new_pos)

    def _seek_backward(self) -> None:
        """Seek backward with acceleration (configurable base, multiplied if rapid presses)."""
        import time

        config = self.context.config.playback_navigation

        current_time = time.time()
        time_since_last = current_time - self.last_seek_time

        # If pressed within threshold, increase multiplier
        if time_since_last < config.rapid_press_threshold:
            self.seek_multiplier = min(self.seek_multiplier + 1, config.max_seek_multiplier)
        else:
            self.seek_multiplier = 1

        self.last_seek_time = current_time

        player = self.context.player
        if not (player.is_playing() or player.get_position() > 0):
            return

        duration = self._get_current_track_duration()
        if duration and duration > 0:
            current_pos = player.get_position()
            seek_amount = config.seek_amount * self.seek_multiplier
            new_time = max((current_pos * duration) - seek_amount, 0)
            new_pos = new_time / duration
            player.set_position(new_pos)

    def _get_current_track_duration(self) -> float | None:
        """Get duration of current track from database.

        Returns:
            Duration in seconds or None
        """
        current_file = self.context.player.current_file
        if not current_file:
            return None

        track = self.context.database.get_track_by_filepath(current_file)
        return track["duration_seconds"] if track else None

    def _next_track(self) -> None:
        """Play next track in list."""
        self.context.emit(Events.SELECT_NEXT_TRACK)

    def _previous_track(self) -> None:
        """Play previous track in list."""
        self.context.emit(Events.SELECT_PREVIOUS_TRACK)

    def _jump_to_percent(self, percent: float) -> None:
        """Jump to specific percentage of track.

        Args:
            percent: Position as percentage (0.0 to 1.0)
        """
        player = self.context.player
        if player.is_playing() or player.get_position() > 0:
            player.set_position(percent)

    def _on_track_finished(self) -> None:
        """Handle track finished event."""
        if self.auto_play_next:
            if self.random_mode:
                self._play_random_track()
            else:
                self._next_track()

    def _play_random_track(self) -> None:
        """Play a random track from the list."""
        self.context.emit(Events.SELECT_RANDOM_TRACK)

    def _toggle_auto_play_from_menu(self) -> None:
        """Toggle auto-play from menu action."""
        self.auto_play_next = self.auto_play_action.isChecked()
        # Sync button state
        if self.auto_play_button:
            self.auto_play_button.setChecked(self.auto_play_next)
            self._update_button_styles()

    def _toggle_auto_play_from_button(self) -> None:
        """Toggle auto-play from button."""
        self.auto_play_next = self.auto_play_button.isChecked()
        # Sync menu action state
        if self.auto_play_action:
            self.auto_play_action.setChecked(self.auto_play_next)
        self._update_button_styles()

    def _toggle_random_from_menu(self) -> None:
        """Toggle random mode from menu action."""
        self.random_mode = self.random_action.isChecked()
        # Sync button state
        if self.random_button:
            self.random_button.setChecked(self.random_mode)
            self._update_button_styles()

    def _toggle_random_from_button(self) -> None:
        """Toggle random mode from button."""
        self.random_mode = self.random_button.isChecked()
        # Sync menu action state
        if self.random_action:
            self.random_action.setChecked(self.random_mode)
        self._update_button_styles()

    def _update_button_styles(self) -> None:
        """Update button styles based on state."""
        if self.auto_play_button:
            if self.auto_play_next:
                self.auto_play_button.setStyleSheet("background-color: #0066FF;")
            else:
                self.auto_play_button.setStyleSheet("")

        if self.random_button:
            if self.random_mode:
                self.random_button.setStyleSheet("background-color: #FF6600;")
            else:
                self.random_button.setStyleSheet("")

    def shutdown(self) -> None:
        """Cleanup on application exit. No cleanup needed for this plugin."""
        ...

    def get_settings_schema(self) -> dict[str, Any]:
        """Return settings schema for configuration UI.

        Returns:
            Dict mapping setting keys to their configuration
        """
        return {
            "seek_amount": {
                "label": "Seek Amount",
                "type": "int",
                "min": 1,
                "max": 60,
                "suffix": " seconds",
                "default": int(self.context.config.playback_navigation.seek_amount),
            },
            "rapid_press_threshold": {
                "label": "Rapid Press Threshold",
                "type": "int",
                "min": 100,
                "max": 2000,
                "suffix": " ms",
                "default": int(self.context.config.playback_navigation.rapid_press_threshold * 1000),
            },
            "max_seek_multiplier": {
                "label": "Max Seek Multiplier",
                "type": "int",
                "min": 1,
                "max": 10,
                "default": self.context.config.playback_navigation.max_seek_multiplier,
            },
        }
