"""Application mode management."""

from enum import Enum

from PySide6.QtCore import QObject, Signal


class AppMode(Enum):
    """Application modes."""

    JUKEBOX = "jukebox"
    CURATING = "curating"


class ModeManager(QObject):
    """Manage application modes."""

    mode_changed = Signal(AppMode)

    def __init__(self, initial_mode: AppMode = AppMode.JUKEBOX):
        """Initialize mode manager.

        Args:
            initial_mode: Initial application mode
        """
        super().__init__()
        self._current_mode = initial_mode

    def set_mode(self, mode: AppMode) -> None:
        """Switch application mode.

        Args:
            mode: Mode to switch to
        """
        if mode != self._current_mode:
            self._current_mode = mode
            self.mode_changed.emit(mode)

    def get_mode(self) -> AppMode:
        """Get current mode.

        Returns:
            Current application mode
        """
        return self._current_mode

    def is_jukebox_mode(self) -> bool:
        """Check if in jukebox mode.

        Returns:
            True if in jukebox mode
        """
        return self._current_mode == AppMode.JUKEBOX

    def is_curating_mode(self) -> bool:
        """Check if in curating mode.

        Returns:
            True if in curating mode
        """
        return self._current_mode == AppMode.CURATING

    def toggle_mode(self) -> None:
        """Toggle between jukebox and curating modes."""
        new_mode = AppMode.CURATING if self.is_jukebox_mode() else AppMode.JUKEBOX
        self.set_mode(new_mode)
