"""Video Exporter plugin for creating video clips from loops."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QPushButton

from jukebox.core.event_bus import Events

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol


class VideoExporterPlugin:
    """Export video clips from loop sections with visual layers."""

    name = "video_exporter"
    version = "1.0.0"
    description = "Export video clips from loop sections"
    modes = ["jukebox", "curating"]

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol | None = None
        self.export_button: QPushButton | None = None
        self.loop_active: bool = False
        self.loop_start: float = 0.0
        self.loop_end: float = 0.0
        self.current_filepath: Path | None = None

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin with context.

        Args:
            context: Plugin context providing access to app services.
        """
        self.context = context

        # Subscribe to loop events
        self.context.subscribe(Events.LOOP_ACTIVATED, self._on_loop_activated)
        self.context.subscribe(Events.LOOP_DEACTIVATED, self._on_loop_deactivated)

        # Subscribe to track events to reset state
        self.context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)

        # Subscribe to settings changes
        self.context.subscribe(Events.PLUGIN_SETTINGS_CHANGED, self._on_settings_changed)

        # Load settings from DB on startup
        self._on_settings_changed()

        logging.info("[Video Exporter] Plugin initialized")

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register UI elements.

        Args:
            ui_builder: UI builder for adding widgets.
        """
        # Create export button (hidden by default)
        self.export_button = QPushButton("Export Video")
        self.export_button.setToolTip("Export loop as video clip (Ctrl+Shift+E)")
        self.export_button.setMaximumWidth(120)
        self.export_button.clicked.connect(self._show_export_dialog)
        self.export_button.setVisible(False)  # Hidden until loop is active

        # Add to toolbar
        ui_builder.add_toolbar_widget(self.export_button)

        # Add menu action
        menu = ui_builder.get_or_create_menu("&Tools")
        ui_builder.add_menu_action(
            menu,
            "Export Video from Loop...",
            self._show_export_dialog,
            shortcut="Ctrl+Shift+E",
        )

        logging.info("[Video Exporter] UI registered")

    def shutdown(self) -> None:
        """Cleanup when plugin unloads."""
        logging.info("[Video Exporter] Plugin shutdown")

    def _on_loop_activated(self, loop_start: float, loop_end: float, filepath: Path) -> None:
        """Handle loop activation event.

        Args:
            loop_start: Loop start position in seconds.
            loop_end: Loop end position in seconds.
            filepath: Path to the current track.
        """
        self.loop_active = True
        self.loop_start = loop_start
        self.loop_end = loop_end
        self.current_filepath = filepath

        # Show export button
        if self.export_button:
            self.export_button.setVisible(True)

        logging.debug(f"[Video Exporter] Loop activated: {loop_start:.1f}s - {loop_end:.1f}s")

    def _on_loop_deactivated(self) -> None:
        """Handle loop deactivation event."""
        self.loop_active = False

        # Hide export button
        if self.export_button:
            self.export_button.setVisible(False)

        logging.debug("[Video Exporter] Loop deactivated")

    def _on_track_loaded(self, track_id: int) -> None:
        """Handle track loaded event.

        Args:
            track_id: Database ID of the loaded track.
        """
        # Reset loop state when a new track is loaded
        self.loop_active = False
        self.loop_start = 0.0
        self.loop_end = 0.0
        self.current_filepath = None

        if self.export_button:
            self.export_button.setVisible(False)

    def _on_settings_changed(self) -> None:
        """Reload config when settings change."""
        logging.info("[Video Exporter] Settings changed, reloading config from database")

        db = self.context.database
        config = self.context.config.video_exporter

        # Helper to get setting from DB
        def get_setting(key: str) -> str | None:
            result = db.conn.execute(
                "SELECT setting_value FROM plugin_settings WHERE plugin_name = ? AND setting_key = ?",
                ("video_exporter", key),
            ).fetchone()
            return result["setting_value"] if result else None

        # Reload string settings
        for key in (
            "default_resolution",
            "output_directory",
            "video_clips_folder",
            "waveform_bass_color",
            "waveform_mid_color",
            "waveform_treble_color",
            "waveform_cursor_color",
        ):
            value = get_setting(key)
            if value is not None:
                setattr(config, key, value)
                logging.debug(f"[Video Exporter] {key}: {value}")

        # Reload int settings
        value = get_setting("default_fps")
        if value is not None:
            try:
                config.default_fps = int(float(value))
                logging.debug(f"[Video Exporter] default_fps: {config.default_fps}")
            except ValueError:
                logging.error(f"[Video Exporter] Invalid default_fps value: {value}")

        # Reload float settings
        value = get_setting("waveform_height_ratio")
        if value is not None:
            try:
                config.waveform_height_ratio = float(value)
                logging.debug(f"[Video Exporter] waveform_height_ratio: {config.waveform_height_ratio}")
            except ValueError:
                logging.error(f"[Video Exporter] Invalid waveform_height_ratio value: {value}")

        # Reload boolean settings
        for key in (
            "waveform_enabled",
            "text_enabled",
            "dynamics_enabled",
            "vjing_enabled",
            "video_background_enabled",
        ):
            value = get_setting(key)
            if value is not None:
                bool_value = value.lower() in ("true", "1", "yes")
                setattr(config, key, bool_value)
                logging.debug(f"[Video Exporter] {key}: {bool_value}")

    def _show_export_dialog(self) -> None:
        """Show the export configuration dialog."""
        if not self.loop_active or not self.current_filepath:
            logging.warning("[Video Exporter] No active loop to export")
            self.context.emit(
                Events.STATUS_MESSAGE,
                message="No active loop to export",
                color="#FF6600",
            )
            return

        # Get track metadata for dialog
        track = self.context.database.tracks.get_by_filepath(self.current_filepath)
        if not track:
            logging.warning("[Video Exporter] Track not found in database")
            return

        # Stop playback when opening export dialog
        self.context.player.stop()

        # Import dialog here to avoid circular imports
        from plugins.video_exporter.export_dialog import ExportDialog

        dialog = ExportDialog(
            parent=self.context.app,
            context=self.context,
            filepath=self.current_filepath,
            loop_start=self.loop_start,
            loop_end=self.loop_end,
            track_metadata=track,
        )

        if dialog.exec():
            # Dialog handles the export via worker
            logging.info("[Video Exporter] Export initiated from dialog")

    def get_settings_schema(self) -> dict[str, Any]:
        """Return settings schema for conf_manager plugin.

        Returns:
            Settings schema dictionary.
        """
        return {
            "default_resolution": {
                "label": "Default Resolution",
                "type": "choice",
                "options": ["1080p", "720p", "square_1080", "square_720", "vertical"],
                "default": self.context.config.video_exporter.default_resolution,
            },
            "default_fps": {
                "label": "Default FPS",
                "type": "int",
                "default": self.context.config.video_exporter.default_fps,
                "min": 15,
                "max": 60,
            },
            "output_directory": {
                "label": "Output Directory",
                "type": "directory",
                "default": self.context.config.video_exporter.output_directory,
            },
            "video_clips_folder": {
                "label": "Video Clips Folder (for backgrounds)",
                "type": "directory",
                "default": self.context.config.video_exporter.video_clips_folder,
            },
            "waveform_enabled": {
                "label": "Enable Waveform Layer",
                "type": "bool",
                "default": self.context.config.video_exporter.waveform_enabled,
            },
            "waveform_height_ratio": {
                "label": "Waveform Height Ratio",
                "type": "float",
                "default": self.context.config.video_exporter.waveform_height_ratio,
                "min": 0.1,
                "max": 0.8,
            },
            "waveform_bass_color": {
                "label": "Waveform Bass Color",
                "type": "color",
                "default": self.context.config.video_exporter.waveform_bass_color,
            },
            "waveform_mid_color": {
                "label": "Waveform Mid Color",
                "type": "color",
                "default": self.context.config.video_exporter.waveform_mid_color,
            },
            "waveform_treble_color": {
                "label": "Waveform Treble Color",
                "type": "color",
                "default": self.context.config.video_exporter.waveform_treble_color,
            },
            "waveform_cursor_color": {
                "label": "Waveform Cursor Color",
                "type": "color",
                "default": self.context.config.video_exporter.waveform_cursor_color,
            },
            "text_enabled": {
                "label": "Enable Text Layer",
                "type": "bool",
                "default": self.context.config.video_exporter.text_enabled,
            },
            "dynamics_enabled": {
                "label": "Enable Dynamics Layer",
                "type": "bool",
                "default": self.context.config.video_exporter.dynamics_enabled,
            },
            "vjing_enabled": {
                "label": "Enable VJing Layer",
                "type": "bool",
                "default": self.context.config.video_exporter.vjing_enabled,
            },
            "video_background_enabled": {
                "label": "Enable Video Background",
                "type": "bool",
                "default": self.context.config.video_exporter.video_background_enabled,
            },
        }
