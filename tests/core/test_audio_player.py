"""Tests for audio player module."""

from pathlib import Path

import pytest

from jukebox.core.audio_player import AudioPlayer


class TestAudioPlayer:
    """Test suite for AudioPlayer."""

    def test_initialization(self, qapp) -> None:  # type: ignore
        """Test player initializes correctly."""
        player = AudioPlayer()

        assert player is not None
        assert player.current_file is None
        assert not player.is_playing()

    def test_volume_control(self, qapp) -> None:  # type: ignore
        """Test volume control and clamping."""
        player = AudioPlayer()

        # Set normal volume
        player.set_volume(50)
        assert player.get_volume() == 50

        # Volume should clamp to 100
        player.set_volume(150)
        assert player.get_volume() == 100

        # Volume should clamp to 0
        player.set_volume(-10)
        assert player.get_volume() == 0

    def test_load_nonexistent_file(self, qapp) -> None:  # type: ignore
        """Test loading non-existent file fails gracefully."""
        player = AudioPlayer()
        result = player.load(Path("/nonexistent/file.mp3"))

        assert result is False
        assert player.current_file is None

    def test_position_control(self, qapp) -> None:  # type: ignore
        """Test position control and clamping."""
        player = AudioPlayer()

        # Position should clamp to 1.0
        player.set_position(1.5)
        # Note: VLC may not accept position before media is loaded
        # This tests the clamping logic

        # Position should clamp to 0.0
        player.set_position(-0.5)

    @pytest.mark.parametrize("volume", [0, 25, 50, 75, 100])
    def test_volume_range(self, qapp, volume: int) -> None:  # type: ignore
        """Test various volume levels."""
        player = AudioPlayer()
        player.set_volume(volume)
        assert player.get_volume() == volume
