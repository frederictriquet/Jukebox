"""Tests for player controls."""

import pytest

from jukebox.ui.components.player_controls import PlayerControls


class TestPlayerControls:
    """Test PlayerControls widget."""

    def test_initialization(self, qapp):  # type: ignore
        """Test controls initialize correctly."""
        controls = PlayerControls()
        assert controls.play_btn is not None
        assert controls.pause_btn is not None
        assert controls.stop_btn is not None
        assert controls.position_slider is not None
        assert controls.volume_slider is not None

    def test_button_signals(self, qapp, qtbot):  # type: ignore
        """Test button signals are emitted."""
        controls = PlayerControls()

        with qtbot.waitSignal(controls.play_clicked, timeout=1000):
            controls.play_btn.click()

        with qtbot.waitSignal(controls.pause_clicked, timeout=1000):
            controls.pause_btn.click()

        with qtbot.waitSignal(controls.stop_clicked, timeout=1000):
            controls.stop_btn.click()

    def test_volume_slider(self, qapp):  # type: ignore
        """Test volume slider."""
        controls = PlayerControls()

        # Set volume programmatically
        controls.set_volume(75)
        assert controls.volume_slider.value() == 75

    def test_position_slider(self, qapp):  # type: ignore
        """Test position slider."""
        controls = PlayerControls()

        # Set position programmatically
        controls.set_position(0.5)
        assert controls.position_slider.value() == 500  # 0.5 * 1000
