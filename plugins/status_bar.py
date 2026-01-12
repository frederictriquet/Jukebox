"""Status bar plugin - displays status messages from other plugins."""

from typing import Any

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class StatusBarPlugin:
    """Centralized status bar for plugin messages."""

    name = "status_bar"
    version = "1.0.0"
    description = "Status bar for system messages"

    # Class variable to share status widget across plugins
    _status_widget: "StatusBarWidget | None" = None

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to status events
        context.subscribe("status_message", self._on_status_message)

    def register_ui(self, ui_builder: Any) -> None:
        """Register status bar widget."""
        StatusBarPlugin._status_widget = StatusBarWidget()
        ui_builder.add_bottom_widget(StatusBarPlugin._status_widget)

    def _on_status_message(self, message: str, color: str | None = None) -> None:
        """Handle status message event."""
        if StatusBarPlugin._status_widget:
            StatusBarPlugin._status_widget.set_message(message, color)

    def shutdown(self) -> None:
        """Cleanup."""
        StatusBarPlugin._status_widget = None

    @staticmethod
    def get_widget() -> "StatusBarWidget | None":
        """Get the status widget instance."""
        return StatusBarPlugin._status_widget


class StatusBarWidget(QWidget):
    """Widget to display status messages."""

    def __init__(self) -> None:
        """Initialize widget."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI."""
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 2, 10, 2)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888888;")  # Gray by default

        layout.addWidget(self.status_label)
        layout.addStretch()

        self.setLayout(layout)
        self.setMaximumHeight(20)

    def set_message(self, message: str, color: str | None = None) -> None:
        """Set status message.

        Args:
            message: Message to display
            color: Optional color (hex string like "#00FF00")
        """
        self.status_label.setText(message)
        if color:
            self.status_label.setStyleSheet(f"color: {color};")
        else:
            self.status_label.setStyleSheet("color: #888888;")

    def clear(self) -> None:
        """Clear status message."""
        self.status_label.setText("")
