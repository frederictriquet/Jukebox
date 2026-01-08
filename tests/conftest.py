"""Pytest configuration and fixtures."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from jukebox.core.audio_player import AudioPlayer
from jukebox.core.config import AudioConfig, JukeboxConfig, LoggingConfig, UIConfig

# Register pytest plugin for VLC mocking
pytest_plugins = ["tests.pytest_vlc_mock"]


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def test_config():
    """Provide test configuration."""
    return JukeboxConfig(
        audio=AudioConfig(
            default_volume=50,
            supported_formats=["mp3", "flac"],
            music_directory=Path("/tmp/test_music"),
        ),
        ui=UIConfig(window_title="Test Jukebox", window_width=800, window_height=600, theme="dark"),
        logging=LoggingConfig(level="DEBUG", file="test.log"),
    )


@pytest.fixture
def audio_player(qapp):  # type: ignore
    """Provide AudioPlayer instance."""
    return AudioPlayer()


@pytest.fixture
def sample_tracks(tmp_path):
    """Provide sample track paths."""
    tracks = []
    for i in range(5):
        track = tmp_path / f"track_{i}.mp3"
        track.touch()
        tracks.append(track)
    return tracks
