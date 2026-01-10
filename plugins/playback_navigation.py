"""Playback navigation plugin with keyboard shortcuts."""

from typing import Any


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
        self.auto_play_action: Any = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to track finished event
        context.player.track_finished.connect(self._on_track_finished)

    def register_ui(self, ui_builder: Any) -> None:
        """Register auto-play menu."""
        menu = ui_builder.add_menu("&Playback")

        # Create checkable action for auto-play next
        from PySide6.QtGui import QAction

        self.auto_play_action = QAction("Auto-play Next Track", ui_builder.main_window)
        self.auto_play_action.setCheckable(True)
        self.auto_play_action.setChecked(self.auto_play_next)
        self.auto_play_action.triggered.connect(self._toggle_auto_play)
        menu.addAction(self.auto_play_action)

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
        if not hasattr(self.context.player, "current_file"):
            return None

        current_file = self.context.player.current_file
        if not current_file:
            return None

        track = self.context.database.conn.execute(
            "SELECT duration_seconds FROM tracks WHERE filepath = ?", (str(current_file),)
        ).fetchone()

        return track["duration_seconds"] if track else None

    def _next_track(self) -> None:
        """Play next track in list."""
        main_window = self.context.app
        if hasattr(main_window, "track_list"):
            main_window.track_list.select_next_track()

    def _previous_track(self) -> None:
        """Play previous track in list."""
        main_window = self.context.app
        if hasattr(main_window, "track_list"):
            main_window.track_list.select_previous_track()

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
            self._next_track()

    def _toggle_auto_play(self) -> None:
        """Toggle auto-play next track."""
        self.auto_play_next = self.auto_play_action.isChecked()

    def shutdown(self) -> None:
        """Cleanup."""
        pass
