"""Search bar widget with debouncing."""

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QLineEdit


class SearchBar(QLineEdit):
    """Search bar with debounced input."""

    search_triggered = Signal(str)

    def __init__(self, parent=None, debounce_ms: int = 300):  # type: ignore
        """Initialize search bar.

        Args:
            parent: Parent widget
            debounce_ms: Debounce delay in milliseconds
        """
        super().__init__(parent)
        self.setPlaceholderText("Search tracks...")

        # Debounce timer
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self._emit_search)

        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text: str) -> None:
        """Handle text change with debounce."""
        self.debounce_timer.stop()
        if len(text) >= 2:
            self.debounce_timer.start(300)
        elif len(text) == 0:
            self.search_triggered.emit("")

    def _emit_search(self) -> None:
        """Emit search signal."""
        self.search_triggered.emit(self.text())
