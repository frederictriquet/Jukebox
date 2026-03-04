"""Tests for ModeManager."""

import pytest
from PySide6.QtWidgets import QApplication

from jukebox.core.mode_manager import AppMode, ModeManager


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Provide a QApplication instance for the test module."""
    app = QApplication.instance() or QApplication([])
    return app  # type: ignore[return-value]


class TestModeManager:
    """Tests for ModeManager."""

    def test_initial_mode_defaults_to_jukebox(self, qapp: QApplication) -> None:
        """Test that ModeManager starts in JUKEBOX mode by default."""
        manager = ModeManager()
        assert manager.get_mode() == AppMode.JUKEBOX

    def test_initial_mode_can_be_overridden(self, qapp: QApplication) -> None:
        """Test that ModeManager accepts a custom initial mode."""
        manager = ModeManager(initial_mode=AppMode.CURATING)
        assert manager.get_mode() == AppMode.CURATING

    def test_set_mode_changes_mode(self, qapp: QApplication) -> None:
        """Test that set_mode updates the current mode."""
        manager = ModeManager()
        manager.set_mode(AppMode.CURATING)
        assert manager.get_mode() == AppMode.CURATING

    def test_set_mode_to_new_mode_emits_signal(self, qapp: QApplication) -> None:
        """Test that set_mode emits mode_changed when the mode actually changes."""
        manager = ModeManager()
        emitted: list[AppMode] = []
        manager.mode_changed.connect(lambda mode: emitted.append(mode))

        manager.set_mode(AppMode.CURATING)

        assert len(emitted) == 1
        assert emitted[0] == AppMode.CURATING

    def test_set_mode_to_same_mode_does_not_emit_signal(self, qapp: QApplication) -> None:
        """Test that set_mode does NOT emit mode_changed when mode is unchanged."""
        manager = ModeManager()
        emitted: list[AppMode] = []
        manager.mode_changed.connect(lambda mode: emitted.append(mode))

        manager.set_mode(AppMode.JUKEBOX)  # Same as initial

        assert len(emitted) == 0

    def test_get_mode_returns_current_mode(self, qapp: QApplication) -> None:
        """Test that get_mode returns the current mode correctly."""
        manager = ModeManager()
        assert manager.get_mode() == AppMode.JUKEBOX

        manager.set_mode(AppMode.CUE_MAKER)
        assert manager.get_mode() == AppMode.CUE_MAKER

    def test_is_jukebox_mode_true_when_jukebox(self, qapp: QApplication) -> None:
        """Test is_jukebox_mode returns True in JUKEBOX mode."""
        manager = ModeManager(initial_mode=AppMode.JUKEBOX)
        assert manager.is_jukebox_mode() is True

    def test_is_jukebox_mode_false_when_not_jukebox(self, qapp: QApplication) -> None:
        """Test is_jukebox_mode returns False when not in JUKEBOX mode."""
        manager = ModeManager(initial_mode=AppMode.CURATING)
        assert manager.is_jukebox_mode() is False

    def test_is_curating_mode_true_when_curating(self, qapp: QApplication) -> None:
        """Test is_curating_mode returns True in CURATING mode."""
        manager = ModeManager(initial_mode=AppMode.CURATING)
        assert manager.is_curating_mode() is True

    def test_is_curating_mode_false_when_not_curating(self, qapp: QApplication) -> None:
        """Test is_curating_mode returns False when not in CURATING mode."""
        manager = ModeManager(initial_mode=AppMode.JUKEBOX)
        assert manager.is_curating_mode() is False

    def test_toggle_mode_from_jukebox_goes_to_curating(self, qapp: QApplication) -> None:
        """Test toggle_mode moves JUKEBOX -> CURATING."""
        manager = ModeManager(initial_mode=AppMode.JUKEBOX)
        manager.toggle_mode()
        assert manager.get_mode() == AppMode.CURATING

    def test_toggle_mode_from_curating_goes_to_jukebox(self, qapp: QApplication) -> None:
        """Test toggle_mode moves CURATING -> JUKEBOX."""
        manager = ModeManager(initial_mode=AppMode.CURATING)
        manager.toggle_mode()
        assert manager.get_mode() == AppMode.JUKEBOX

    def test_toggle_mode_from_cue_maker_goes_to_jukebox(self, qapp: QApplication) -> None:
        """Test toggle_mode from CUE_MAKER lands on JUKEBOX (index -1, next_index=0)."""
        manager = ModeManager(initial_mode=AppMode.CUE_MAKER)
        manager.toggle_mode()
        assert manager.get_mode() == AppMode.JUKEBOX

    def test_toggle_mode_emits_signal(self, qapp: QApplication) -> None:
        """Test that toggle_mode emits mode_changed with the new mode."""
        manager = ModeManager(initial_mode=AppMode.JUKEBOX)
        emitted: list[AppMode] = []
        manager.mode_changed.connect(lambda mode: emitted.append(mode))

        manager.toggle_mode()

        assert len(emitted) == 1
        assert emitted[0] == AppMode.CURATING

    def test_signal_fires_with_correct_appmode_value(self, qapp: QApplication) -> None:
        """Test that the mode_changed signal carries the correct AppMode enum value."""
        manager = ModeManager(initial_mode=AppMode.JUKEBOX)
        received: list[AppMode] = []
        manager.mode_changed.connect(lambda mode: received.append(mode))

        manager.set_mode(AppMode.CUE_MAKER)

        assert len(received) == 1
        assert received[0] is AppMode.CUE_MAKER

    def test_multiple_toggles_cycle_correctly(self, qapp: QApplication) -> None:
        """Test that multiple toggles cycle correctly between JUKEBOX and CURATING."""
        manager = ModeManager(initial_mode=AppMode.JUKEBOX)

        manager.toggle_mode()
        assert manager.get_mode() == AppMode.CURATING

        manager.toggle_mode()
        assert manager.get_mode() == AppMode.JUKEBOX

        manager.toggle_mode()
        assert manager.get_mode() == AppMode.CURATING
