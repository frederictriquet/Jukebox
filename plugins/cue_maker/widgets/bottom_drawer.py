"""Bottom drawer widget for library access in cue_maker mode."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget


class BottomDrawer(QWidget):
    """Animated drawer widget that collapses/expands from the bottom.

    The drawer has:
    - A handle button at the top (always visible, 32px height)
    - Content area below that animates between 0 and OPEN_HEIGHT

    Initially collapsed (maximumHeight=0).
    """

    OPEN_HEIGHT = 350
    HANDLE_HEIGHT = 32

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the drawer.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Handle button (always visible, 32px)
        self._handle = QPushButton("▲ Library")
        self._handle.setFixedHeight(self.HANDLE_HEIGHT)
        self._handle.clicked.connect(self.toggle)
        layout.addWidget(self._handle)

        # Content widget (will be added by set_content)
        self._content: QWidget | None = None
        self._is_open = False
        self._anim: QPropertyAnimation | None = None

    def set_content(self, content: QWidget) -> None:
        """Set the content widget that will be shown/hidden.

        Args:
            content: Widget to display below the handle
        """
        self._content = content
        layout = self.layout()
        if layout is not None:
            layout.addWidget(content)
        # Start collapsed
        content.setMaximumHeight(0)

    def toggle(self) -> None:
        """Toggle the drawer open/closed with animation."""
        if self._content is None:
            return

        self._is_open = not self._is_open
        start = self._content.height()
        end = self.OPEN_HEIGHT if self._is_open else 0

        # Stop any existing animation
        if self._anim is not None:
            self._anim.stop()

        self._anim = QPropertyAnimation(self._content, b"maximumHeight", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuart)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.start()

        # Update handle text
        arrow = "▼" if self._is_open else "▲"
        self._handle.setText(f"{arrow} Library")

    @property
    def is_open(self) -> bool:
        """Return whether the drawer is open."""
        return self._is_open
