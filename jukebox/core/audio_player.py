"""Audio player wrapper for python-vlc."""

import logging
import queue
from enum import Enum
from pathlib import Path
from typing import Any

import vlc
from PySide6.QtCore import QObject, QTimer, Signal


class PlayerState(Enum):
    """Audio player states."""

    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"


class AudioPlayer(QObject):
    """Wrapper around python-vlc for audio playback."""

    # Signals
    state_changed = Signal(str)  # PlayerState.value
    position_changed = Signal(float)  # 0.0 to 1.0
    volume_changed = Signal(int)  # 0 to 100
    track_finished = Signal()

    def __init__(self) -> None:
        """Initialize audio player."""
        super().__init__()
        self._instance: Any = vlc.Instance()
        # vlc.Instance() retourne None si libvlc est absent ou mal configuré.
        if self._instance is None:
            raise RuntimeError(
                "Impossible d'initialiser libVLC : vlc.Instance() a retourné None. "
                "Vérifier que VLC est installé et accessible."
            )
        self._player: Any = self._instance.media_player_new()
        self._current_file: Path | None = None

        # File thread-safe pour recevoir les événements VLC (thread ctypes sans GIL Qt)
        self._end_reached_queue: queue.SimpleQueue[bool] = queue.SimpleQueue()
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._check_end_reached)
        self._poll_timer.start(100)

        # Setup event manager for track end detection
        event_manager = self._player.event_manager()
        event_manager.event_attach(
            vlc.EventType.MediaPlayerEndReached,  # pyright: ignore[reportAttributeAccessIssue]
            self._on_end_reached,
        )

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
        except Exception as e:
            logging.error(f"[AudioPlayer] Impossible de charger le fichier {filepath} : {e}")
            return False

    def play(self) -> None:
        """Start playback."""
        # play() renvoie -1 en cas d'échec : ne pas émettre PLAYING si VLC a échoué.
        if self._player.play() == -1:
            logging.error("[AudioPlayer] Échec du démarrage de la lecture (VLC a retourné -1).")
            return
        self.state_changed.emit(PlayerState.PLAYING.value)

    def pause(self) -> None:
        """Pause playback."""
        # pause() ne renvoie pas de code d'erreur exploitable ; on vérifie l'état réel
        # rapporté par VLC avant d'émettre PAUSED pour éviter une désynchronisation UI.
        self._player.pause()
        if self._player.is_playing() == 1:
            logging.error("[AudioPlayer] La mise en pause a échoué (VLC est toujours en lecture).")
            return
        self.state_changed.emit(PlayerState.PAUSED.value)

    def stop(self) -> None:
        """Stop playback."""
        self._player.stop()
        self.state_changed.emit(PlayerState.STOPPED.value)

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
        return bool(playing) if playing is not None else False

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
        # Les abonnés doivent savoir que la lecture est arrêtée après un unload.
        self.state_changed.emit(PlayerState.STOPPED.value)

    def _on_end_reached(self, _event: Any) -> None:
        """Handle VLC end reached event (appelé depuis le thread ctypes de VLC).

        Pas d'appel Qt direct ici — le thread VLC ne détient pas le GIL Qt.
        On dépose dans une file Python (thread-safe) que le timer principal videra.
        """
        self._end_reached_queue.put(True)

    def _check_end_reached(self) -> None:
        """Draîne la file VLC depuis le thread Qt principal (appelé par le timer)."""
        if not self._end_reached_queue.empty():
            self._end_reached_queue.get()
            # En fin de morceau VLC a stoppé la lecture : on notifie l'état STOPPED
            # pour que l'UI (icône play/pause) se remette à l'arrêt, y compris quand
            # l'auto-play est désactivé. Émis avant track_finished afin qu'un éventuel
            # auto-play enchaîne ensuite avec un état PLAYING qui prévaut.
            self.state_changed.emit(PlayerState.STOPPED.value)
            self.track_finished.emit()
