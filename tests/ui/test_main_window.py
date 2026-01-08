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

        # Timer should not be active initially
        assert not window.position_timer.isActive()

        # Simulate play (without actual audio file)
        window._on_play()

        # Timer should now be active
        assert window.position_timer.isActive()

    def test_pause_stops_timer(self, qapp, test_config):  # type: ignore
        """Test pause button stops position timer."""
        window = MainWindow(test_config)

        # Start timer
        window._on_play()
        assert window.position_timer.isActive()

        # Pause should stop timer
        window._on_pause()
        assert not window.position_timer.isActive()

    def test_stop_resets_position(self, qapp, test_config):  # type: ignore
        """Test stop button resets position to 0."""
        window = MainWindow(test_config)

        # Start playing
        window._on_play()

        # Set some position
        window.controls.set_position(0.5)

        # Stop should reset to 0
        window._on_stop()
        assert window.controls.position_slider.value() == 0
        assert not window.position_timer.isActive()

    def test_initial_volume(self, qapp, test_config):  # type: ignore
        """Test initial volume is set from config."""
        window = MainWindow(test_config)

        assert window.controls.volume_slider.value() == 50
        assert window.player.get_volume() == 50
