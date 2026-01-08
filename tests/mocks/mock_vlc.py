"""Mock VLC objects for testing without VLC installed."""

from typing import Any


class MockVLCMedia:
    """Mock VLC Media object."""

    def __init__(self, path: str):
        self.path = path


class MockVLCPlayer:
    """Mock VLC MediaPlayer object."""

    def __init__(self) -> None:
        self._media: MockVLCMedia | None = None
        self._playing = False
        self._volume = 70
        self._position = 0.0

    def set_media(self, media: MockVLCMedia) -> None:
        """Set media."""
        self._media = media

    def play(self) -> int:
        """Start playback."""
        self._playing = True
        return 0

    def pause(self) -> None:
        """Pause playback."""
        self._playing = False

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


class MockVLCInstance:
    """Mock VLC Instance object."""

    def media_new(self, path: str) -> MockVLCMedia:
        """Create new media."""
        return MockVLCMedia(path)

    def media_player_new(self) -> MockVLCPlayer:
        """Create new media player."""
        return MockVLCPlayer()


def mock_vlc_module() -> Any:
    """Create mock vlc module."""

    class VLCModule:
        """Mock vlc module."""

        @staticmethod
        def Instance() -> MockVLCInstance:  # noqa: N802
            """Create VLC instance."""
            return MockVLCInstance()

    return VLCModule()
