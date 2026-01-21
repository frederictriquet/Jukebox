"""Status bar plugin - displays status messages from other plugins."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QLabel, QStatusBar

from jukebox.core.event_bus import Events

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol


class StatusBarPlugin:
    """Centralized status bar for plugin messages."""

    name = "status_bar"
    version = "1.0.0"
    description = "Status bar for system messages"
    modes = ["jukebox", "curating"]  # Active in all modes

    # Class variable to share status bar across plugins
    _status_bar: QStatusBar | None = None
    _status_label: QLabel | None = None

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol | None = None

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to status events
        context.subscribe(Events.STATUS_MESSAGE, self._on_status_message)

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register status bar."""
        # Use Qt's built-in status bar (always at bottom, visible in all modes)
        StatusBarPlugin._status_bar = QStatusBar()
        StatusBarPlugin._status_label = QLabel("")
        # No fixed color - use theme's default text color

        StatusBarPlugin._status_bar.addPermanentWidget(StatusBarPlugin._status_label)
        ui_builder.main_window.setStatusBar(StatusBarPlugin._status_bar)

    def _on_status_message(self, message: str, color: str | None = None) -> None:
        """Handle status message event.

        Note: color parameter is ignored - always uses theme default color.
        """
        if StatusBarPlugin._status_label:
            StatusBarPlugin._status_label.setText(message)

    def activate(self, mode: str) -> None:
        """Activate plugin for this mode."""
        # Status bar always visible
        pass

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for this mode."""
        # Status bar always visible
        pass

    def shutdown(self) -> None:
        """Cleanup on application exit."""
        StatusBarPlugin._status_bar = None
        StatusBarPlugin._status_label = None
