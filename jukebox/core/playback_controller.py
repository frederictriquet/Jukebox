"""Playback controller — manages position polling and track playback events.

Extracts playback orchestration logic from MainWindow so that the UI layer
only wires controls and display, while this controller owns:
- Position polling (QTimer) and POSITION_UPDATE emission
- Player state change handling (timer start/stop)
- Track loading with TRACK_LOADED event emission
- Tracking of the currently loaded library track
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal

from jukebox.core.event_bus import Events

if TYPE_CHECKING:
    from jukebox.core.audio_player import AudioPlayer
    from jukebox.core.database import Database
    from jukebox.core.event_bus import EventBus

logger = logging.getLogger(__name__)


class PlaybackController(QObject):
    """Orchestrates audio playback, position polling, and event emission.

    This controller sits between the raw AudioPlayer and the rest of the
    application.  It owns the 100 ms position-polling timer and emits
    ``POSITION_UPDATE`` on the event bus *only* when a library track is
    playing (not when a plugin drives the player directly, e.g. the
    cue-maker mix playback which emits ``MIX_POSITION_UPDATE`` itself).

    Signals:
        track_started(str): Emitted with the filepath when a library track
            starts playing.  UI can use this to update the window title.
    """

    track_started = Signal(str)  # filepath

    def __init__(
        self,
        player: AudioPlayer,
        event_bus: EventBus,
        database: Database,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._player = player
        self._event_bus = event_bus
        self._database = database
        self._current_track_filepath: str | None = None

        # Position polling timer
        self._position_timer = QTimer(self)
        self._position_timer.setInterval(100)
        self._position_timer.timeout.connect(self._poll_position)

        # React to player state changes
        self._player.state_changed.connect(self._on_state_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_and_play(self, filepath: Path) -> bool:
        """Load a library track and start playback.

        Looks up the track in the database to retrieve its ``track_id``
        and emits ``TRACK_LOADED`` so that other plugins (waveform, track
        info…) can react.

        Returns:
            True if the file was loaded successfully.
        """
        if not self._player.load(filepath):
            return False

        self._current_track_filepath = str(filepath)

        # Emit TRACK_LOADED with the database id
        if self._database.conn:
            row = self._database.conn.execute(
                "SELECT id FROM tracks WHERE filepath = ?",
                (str(filepath),),
            ).fetchone()
            if row:
                logger.debug("[Playback] TRACK_LOADED: id=%s", row["id"])
                self._event_bus.emit(Events.TRACK_LOADED, track_id=row["id"])
            else:
                logger.error("[Playback] Track not in database: %s", filepath)

        self._player.play()
        self.track_started.emit(str(filepath))
        return True

    def play(self) -> None:
        """Resume playback."""
        self._player.play()

    def pause(self) -> None:
        """Pause playback."""
        self._player.pause()

    def stop(self) -> None:
        """Stop playback."""
        self._player.stop()

    def release_track(self) -> None:
        """Release the current library track.

        Allows external controllers (e.g., cue_maker plugin) to take over
        the player without interfering with library track position polling.
        After calling this, the position timer will not emit POSITION_UPDATE
        until a new library track is loaded via load_and_play().
        """
        self._current_track_filepath = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_state_changed(self, state: str) -> None:
        """Manage position timer based on player state."""
        if state == "playing":
            self._position_timer.start()
        elif state == "paused":
            self._position_timer.stop()
        elif state == "stopped":
            self._position_timer.stop()
            self._event_bus.emit(Events.POSITION_UPDATE, position=0.0)

    def _poll_position(self) -> None:
        """Emit POSITION_UPDATE only when the library track is playing."""
        if not self._player.is_playing():
            return
        current_file = self._player.current_file
        if (
            current_file is None
            or self._current_track_filepath is None
            or str(current_file) != self._current_track_filepath
        ):
            return
        position = self._player.get_position()
        self._event_bus.emit(Events.POSITION_UPDATE, position=position)
