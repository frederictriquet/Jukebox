"""Search bar widget with debouncing."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit


class SearchBar(QLineEdit):
    """Search bar with debounced input."""

    search_triggered = Signal(str)

    def __init__(self, parent=None, debounce_ms: int = 300, *, focus_shortcut: str = "Ctrl+F"):  # type: ignore
        """Initialize search bar.

        Args:
            parent: Parent widget
            debounce_ms: Debounce delay in milliseconds
            focus_shortcut: Keyboard shortcut text for focusing the search bar
        """
        super().__init__(parent)
        self._debounce_ms = debounce_ms
        self.setPlaceholderText(f"Search tracks... ({focus_shortcut} to focus)")
        self.setClearButtonEnabled(True)

        # Only take focus when explicitly clicked or via Ctrl+F
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        # Debounce timer
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self._emit_search)

        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text: str) -> None:
        """Handle text change with debounce."""
        self.debounce_timer.stop()
        if len(text) >= 2:
            self.debounce_timer.start(self._debounce_ms)
        elif len(text) == 0:
            self.search_triggered.emit("")

    def _emit_search(self) -> None:
        """Emit search signal."""
        self.search_triggered.emit(self.text())

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Escape:
            # Clear focus on ESC
            self.clearFocus()
        else:
            # Let default handling continue for other keys
            super().keyPressEvent(event)
