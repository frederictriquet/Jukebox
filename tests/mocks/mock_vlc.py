"""Mock VLC objects for testing without VLC installed."""

from typing import Any


class MockVLCMedia:
    """Mock VLC Media object."""

    def __init__(self, path: str):
        self.path = path


class MockEventManager:
    """Mock VLC EventManager object."""

    def event_attach(self, event_type: Any, callback: Any) -> None:
        """Attach event handler (no-op in mock)."""
        pass


class MockVLCPlayer:
    """Mock VLC MediaPlayer object."""

    def __init__(self) -> None:
        self._media: MockVLCMedia | None = None
        self._playing = False
        self._volume = 70
        self._position = 0.0
        self._event_manager = MockEventManager()

    def set_media(self, media: MockVLCMedia) -> None:
        """Set media."""
        self._media = media

    def play(self) -> int:
        """Start playback."""
        self._playing = True
        return 0

    def pause(self) -> None:
        """Toggle pause playback (VLC behavior: pause toggles play/pause)."""
        self._playing = not self._playing

    def stop(self) -> None:
        """Stop playback."""
        self._playing = False
        self._position = 0.0

    def is_playing(self) -> int:
        """Check if playing."""
        return 1 if self._playing else 0

    def audio_set_volume(self, volume: int) -> int:
        """Set volume."""
        self._volume = max(0, min(100, volume))
        return 0

    def audio_get_volume(self) -> int:
        """Get volume."""
        return self._volume

    def set_position(self, position: float) -> None:
        """Set position."""
        self._position = max(0.0, min(1.0, position))

    def get_position(self) -> float:
        """Get position."""
        return self._position

    def event_manager(self) -> MockEventManager:
        """Get event manager."""
        return self._event_manager


class MockVLCInstance:
    """Mock VLC Instance object."""

    def media_new(self, path: str) -> MockVLCMedia:
        """Create new media."""
        return MockVLCMedia(path)

    def media_player_new(self) -> MockVLCPlayer:
        """Create new media player."""
        return MockVLCPlayer()


class MockEventType:
    """Mock VLC EventType enum."""

    MediaPlayerEndReached = "MediaPlayerEndReached"


def mock_vlc_module() -> Any:
    """Create mock vlc module."""

    class VLCModule:
        """Mock vlc module."""

        # Event types
        EventType = MockEventType

        @staticmethod
        def Instance() -> MockVLCInstance:  # noqa: N802
            """Create VLC instance."""
            return MockVLCInstance()

    return VLCModule()
