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
    modes = ["jukebox", "curating", "cue_maker"]  # Active in all modes

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol = None  # type: ignore[assignment]
        # Instance variables: no state sharing between plugin instances
        self._status_bar: QStatusBar | None = None
        self._status_label: QLabel | None = None

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to status events
        context.subscribe(Events.STATUS_MESSAGE, self._on_status_message)

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register status bar."""
        # Idempotent: do not recreate a QStatusBar if one is already registered
        if self._status_bar is not None:
            return

        # Use Qt's built-in status bar (always at bottom, visible in all modes)
        self._status_bar = QStatusBar()
        self._status_label = QLabel("")
        # No fixed color - use theme's default text color

        self._status_bar.addPermanentWidget(self._status_label)
        ui_builder.main_window.setStatusBar(self._status_bar)

    def _on_status_message(self, message: str, color: str | None = None) -> None:
        """Handle status message event.

        Args:
            message: Text to display.
            color: Optional CSS text color. If None, the theme's default color
                is restored.
        """
        if self._status_label:
            self._status_label.setText(message)
            # Honor the color supplied by the emitter (e.g. batch_helper)
            # instead of silently ignoring it.
            if color:
                self._status_label.setStyleSheet(f"color: {color};")
            else:
                self._status_label.setStyleSheet("")

    def activate(self, mode: str) -> None:
        """Activate plugin for this mode.

        Intentional no-op: the status bar stays visible in all modes, so there
        is nothing to (re)activate on a mode change.
        """

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for this mode.

        Intentional no-op: the status bar stays visible in all modes, so it is
        never hidden on a mode change.
        """

    def shutdown(self) -> None:
        """Cleanup on application exit."""
        self._status_bar = None
        self._status_label = None
