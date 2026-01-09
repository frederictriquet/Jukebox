"""Performance benchmarks."""

import time
from pathlib import Path

import pytest

from jukebox.core.audio_player import AudioPlayer
from jukebox.core.config import AudioConfig, JukeboxConfig, LoggingConfig, UIConfig, load_config
from jukebox.ui.main_window import MainWindow


@pytest.mark.benchmark
class TestPerformance:
    """Performance benchmarks."""

    def test_player_init_time(self, qapp):  # type: ignore
        """Benchmark player initialization."""
        start = time.perf_counter()
        player = AudioPlayer()
        duration = time.perf_counter() - start

        assert player is not None
        assert duration < 0.5  # Should init in < 500ms

    def test_config_load_time(self):  # type: ignore
        """Benchmark configuration loading."""
        start = time.perf_counter()
        config = load_config()
        duration = time.perf_counter() - start

        assert config is not None
        assert duration < 0.1  # Should load in < 100ms

    def test_window_init_time(self, qapp):  # type: ignore
        """Benchmark window initialization."""
        config = JukeboxConfig(
            audio=AudioConfig(),
            ui=UIConfig(),
            logging=LoggingConfig(),
        )

        start = time.perf_counter()
        window = MainWindow(config)
        duration = time.perf_counter() - start

        assert window is not None
        assert duration < 1.0  # Should init in < 1s

    def test_multiple_tracks_addition(self, qapp):  # type: ignore
        """Benchmark adding multiple tracks."""
        config = JukeboxConfig(
            audio=AudioConfig(),
            ui=UIConfig(),
            logging=LoggingConfig(),
        )
        window = MainWindow(config)

        # Clear any existing tracks
        window.track_list.clear_tracks()

        # Add dummy tracks
        start = time.perf_counter()
        for i in range(100):
            window.track_list.add_track(Path(f"/tmp/track{i}.mp3"))
        duration = time.perf_counter() - start

        assert window.track_list.count() == 100
        assert duration < 0.5  # Should add 100 tracks in < 500ms
