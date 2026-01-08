"""Integration tests for full playback flow."""

from pathlib import Path

import pytest

from jukebox.core.config import AudioConfig, JukeboxConfig, LoggingConfig, UIConfig
from jukebox.ui.main_window import MainWindow


@pytest.fixture
def test_config():
    """Test configuration."""
    return JukeboxConfig(
        audio=AudioConfig(
            default_volume=50,
            supported_formats=["mp3", "flac"],
            music_directory=Path("/tmp/test_music"),
        ),
        ui=UIConfig(window_title="Test", window_width=800, window_height=600, theme="dark"),
        logging=LoggingConfig(level="DEBUG", file="test.log"),
    )


class TestFullPlayback:
    """Integration tests for complete playback workflow."""

    def test_window_creation(self, qapp, test_config):  # type: ignore
        """Test complete window initialization."""
        window = MainWindow(test_config)

        assert window.player is not None
        assert window.controls is not None
        assert window.track_list is not None
        assert window.position_timer is not None

    def test_volume_sync_integration(self, qapp, test_config):  # type: ignore
        """Test volume synchronization between components."""
        window = MainWindow(test_config)

        # Set via controls
        window.controls.volume_slider.setValue(75)
        assert window.player.get_volume() == 75

        # Set via player
        window.player.set_volume(60)
        assert window.controls.volume_slider.value() == 60

    def test_playback_state_sync(self, qapp, test_config):  # type: ignore
        """Test playback state synchronization."""
        window = MainWindow(test_config)

        # Play
        window._on_play()
        assert window.position_timer.isActive()

        # Pause
        window._on_pause()
        assert not window.position_timer.isActive()

        # Stop
        window._on_stop()
        assert not window.position_timer.isActive()
        assert window.controls.position_slider.value() == 0
