"""Tests for main window."""

from jukebox.ui.main_window import MainWindow


class TestMainWindow:
    """Test suite for MainWindow."""

    def test_initialization(self, qapp, test_config):  # type: ignore
        """Test window initializes correctly."""
        window = MainWindow(test_config)

        assert window is not None
        assert window.windowTitle() == "Test Jukebox"
        assert window.player is not None
        assert window.controls is not None
        assert window.track_list is not None

    def test_position_timer_exists(self, qapp, test_config):  # type: ignore
        """Test position timer is created."""
        window = MainWindow(test_config)

        assert window.position_timer is not None
        assert window.position_timer.interval() == 100
        assert not window.position_timer.isActive()

    def test_play_starts_timer(self, qapp, test_config):  # type: ignore
        """Test play button starts position timer."""
        window = MainWindow(test_config)

        assert not window.position_timer.isActive()

        window._on_play()

        assert window.position_timer.isActive()

    def test_pause_stops_timer(self, qapp, test_config):  # type: ignore
        """Test pause button stops position timer."""
        window = MainWindow(test_config)

        window._on_play()
        assert window.position_timer.isActive()

        window._on_pause()
        assert not window.position_timer.isActive()

    def test_stop_emits_position_update(self, qapp, test_config):  # type: ignore
        """Test stop emits position update event."""
        window = MainWindow(test_config)

        window._on_play()
        window._on_stop()

        assert not window.position_timer.isActive()

    def test_initial_volume(self, qapp, test_config):  # type: ignore
        """Test initial volume is set from config."""
        window = MainWindow(test_config)

        assert window.controls.volume_slider.value() == 50
        assert window.player.get_volume() == 50
