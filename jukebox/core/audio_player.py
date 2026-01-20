"""Audio player wrapper for python-vlc."""

from pathlib import Path
from typing import Any

import vlc
from PySide6.QtCore import QObject, Signal


class AudioPlayer(QObject):
    """Wrapper around python-vlc for audio playback."""

    # Signals
    state_changed = Signal(str)  # "playing", "paused", "stopped"
    position_changed = Signal(float)  # 0.0 to 1.0
    volume_changed = Signal(int)  # 0 to 100
    track_finished = Signal()

    def __init__(self) -> None:
        """Initialize audio player."""
        super().__init__()
        self._instance = vlc.Instance()
        self._player = self._instance.media_player_new()
        self._current_file: Path | None = None

        # Setup event manager for track end detection
        event_manager = self._player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_end_reached)

    def load(self, filepath: Path) -> bool:
        """Load an audio file.

        Args:
            filepath: Path to audio file

        Returns:
            True if file loaded successfully, False otherwise
        """
        if not filepath.exists():
            return False

        try:
            media = self._instance.media_new(str(filepath))
            self._player.set_media(media)
            self._current_file = filepath
            return True
        except Exception:
            return False

    def play(self) -> None:
        """Start playback."""
        self._player.play()
        self.state_changed.emit("playing")

    def pause(self) -> None:
        """Pause playback."""
        self._player.pause()
        self.state_changed.emit("paused")

    def stop(self) -> None:
        """Stop playback."""
        self._player.stop()
        self.state_changed.emit("stopped")

    def set_volume(self, volume: int) -> None:
        """Set volume (0-100).

        Args:
            volume: Volume level (0-100)
        """
        volume = max(0, min(100, volume))
        self._player.audio_set_volume(volume)
        self.volume_changed.emit(volume)

    def get_volume(self) -> int:
        """Get current volume (0-100).

        Returns:
            Current volume level
        """
        volume = self._player.audio_get_volume()
        return int(volume) if volume is not None else 0

    def set_position(self, position: float) -> None:
        """Set playback position (0.0-1.0).

        Args:
            position: Position in track (0.0 = start, 1.0 = end)
        """
        position = max(0.0, min(1.0, position))
        self._player.set_position(position)
        self.position_changed.emit(position)

    def get_position(self) -> float:
        """Get playback position (0.0-1.0).

        Returns:
            Current position in track
        """
        position = self._player.get_position()
        return float(position) if position is not None else 0.0

    def is_playing(self) -> bool:
        """Check if currently playing.

        Returns:
            True if playing, False otherwise
        """
        playing = self._player.is_playing()
        return bool(playing == 1) if playing is not None else False

    @property
    def current_file(self) -> Path | None:
        """Get currently loaded file.

        Returns:
            Path to current file or None
        """
        return self._current_file

    def unload(self) -> None:
        """Unload current track and stop playback."""
        self._player.stop()
        self._player.set_media(None)
        self._current_file = None

    def _on_end_reached(self, event: Any) -> None:
        """Handle VLC end reached event.

        Args:
            event: VLC event
        """
        self.track_finished.emit()
