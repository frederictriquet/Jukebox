"""Loop player plugin for repeating a section of a track."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QPushButton

from jukebox.core.event_bus import Events

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol


class LoopPlayerPlugin:
    """Enable looping a section of the current track."""

    name = "loop_player"
    version = "1.0.0"
    description = "Loop a section of the current track"
    modes = ["jukebox", "curating"]

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol | None = None
        self.loop_button: QPushButton | None = None
        self.loop_active: bool = False
        self.loop_start: float = 0.0  # Position in seconds
        self.loop_end: float = 0.0  # Position in seconds
        self.position_timer: QTimer | None = None
        self.waveform_widget: Any = None
        self.loop_region: Any = None  # pyqtgraph LinearRegionItem

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to track loaded event to reset loop
        self.context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)

        # Subscribe to settings changes
        self.context.subscribe(Events.PLUGIN_SETTINGS_CHANGED, self._on_settings_changed)

        # Load settings from database at startup
        self._on_settings_changed()

        # Timer to check playback position
        self.position_timer = QTimer()
        self.position_timer.setInterval(50)  # Check every 50ms
        self.position_timer.timeout.connect(self._check_position)

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register loop button in player controls."""
        main_window = self.context.app
        controls = main_window.controls

        if controls.layout():
            # Loop button
            loop_duration = self.context.config.loop_player.duration
            self.loop_button = QPushButton("⟲")
            self.loop_button.setCheckable(True)
            self.loop_button.setChecked(False)
            self.loop_button.setToolTip(f"Loop section ({loop_duration}s from current position)")
            self.loop_button.setMaximumWidth(40)
            self.loop_button.clicked.connect(self._toggle_loop)
            self._update_button_style()

            layout = controls.layout()
            # Find the stretch item and insert button before it
            stretch_index = -1
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item and item.spacerItem():
                    stretch_index = i
                    break

            # If stretch found, insert before it; otherwise append
            if stretch_index >= 0:
                ui_builder.insert_widget_in_layout(layout, stretch_index, self.loop_button)
            else:
                layout.addWidget(self.loop_button)

        # Add menu options in Playback menu
        menu = ui_builder.get_or_create_menu("&Playback")
        ui_builder.add_menu_separator(menu)
        ui_builder.add_menu_action(menu, "Toggle Loop", self._toggle_loop, shortcut="Ctrl+L")
        ui_builder.add_menu_action(
            menu,
            "Move Loop Forward (Coarse)",
            self._move_loop_coarse_forward,
            shortcut="Ctrl+Right",
        )
        ui_builder.add_menu_action(
            menu,
            "Move Loop Backward (Coarse)",
            self._move_loop_coarse_backward,
            shortcut="Ctrl+Left",
        )
        ui_builder.add_menu_action(
            menu, "Move Loop Forward (Fine)", self._move_loop_fine_forward, shortcut="Shift+Right"
        )
        ui_builder.add_menu_action(
            menu, "Move Loop Backward (Fine)", self._move_loop_fine_backward, shortcut="Shift+Left"
        )

        # Get reference to waveform widget if available
        if hasattr(main_window, "plugin_manager"):
            waveform_plugin = main_window.plugin_manager.plugins.get("waveform_visualizer")
            if waveform_plugin and hasattr(waveform_plugin, "waveform_widget"):
                self.waveform_widget = waveform_plugin.waveform_widget

    def _toggle_loop(self) -> None:
        """Toggle loop mode."""
        if not self.loop_active:
            # Activate loop at current position
            player = self.context.player
            if not player.current_file:
                logging.warning("[Loop Player] No track loaded")
                if self.loop_button:
                    self.loop_button.setChecked(False)
                return

            # Get track duration from database
            track = self.context.database.tracks.get_by_filepath(player.current_file)

            if not track or not track["duration_seconds"]:
                logging.warning("[Loop Player] Cannot get track duration")
                if self.loop_button:
                    self.loop_button.setChecked(False)
                return

            track_duration = track["duration_seconds"]

            # Get current position in seconds
            loop_duration = self.context.config.loop_player.duration
            position = player.get_position()

            # Clamp position to valid range [0.0, 1.0]
            position = max(0.0, min(1.0, position))

            current_pos = position * track_duration
            self.loop_start = current_pos
            self.loop_end = current_pos + loop_duration

            # Don't exceed track duration
            if self.loop_end > track_duration:
                self.loop_end = track_duration

            self.loop_active = True
            self.position_timer.start()

            # Show loop region on waveform
            self._show_loop_region()

            logging.info(
                f"[Loop Player] Loop activated: {self.loop_start:.1f}s - {self.loop_end:.1f}s"
            )

        else:
            # Deactivate loop
            self.loop_active = False
            self.position_timer.stop()
            self._hide_loop_region()
            logging.info("[Loop Player] Loop deactivated")

        self._update_button_style()

    def _check_position(self) -> None:
        """Check playback position and loop if necessary."""
        if not self.loop_active:
            return

        player = self.context.player
        if not player.is_playing():
            return

        # Get track duration from database
        track = self.context.database.tracks.get_by_filepath(player.current_file)

        if not track or not track["duration_seconds"]:
            return

        track_duration = track["duration_seconds"]
        current_pos = player.get_position() * track_duration

        # If we've passed the loop end, jump back to loop start
        if current_pos >= self.loop_end:
            player.set_position(self.loop_start / track_duration)
            logging.debug(f"[Loop Player] Looping back to {self.loop_start:.1f}s")

    def _show_loop_region(self) -> None:
        """Show loop region on waveform."""
        if not self.waveform_widget:
            return

        try:
            import pyqtgraph as pg

            # Convert seconds to waveform x coordinates
            player = self.context.player
            track = self.context.database.tracks.get_by_filepath(player.current_file)

            if not track or not track["duration_seconds"]:
                return

            track_duration = track["duration_seconds"]
            waveform_length = self.waveform_widget.expected_length
            if waveform_length <= 0:
                return

            x_start = (self.loop_start / track_duration) * waveform_length
            x_end = (self.loop_end / track_duration) * waveform_length

            # Create semi-transparent region
            self.loop_region = pg.LinearRegionItem(
                values=[x_start, x_end],
                brush=pg.mkBrush(255, 255, 0, 50),  # Yellow with 50/255 alpha
                movable=False,
            )
            self.waveform_widget.plot_widget.addItem(self.loop_region)

        except Exception as e:
            logging.error(f"[Loop Player] Error showing loop region: {e}", exc_info=True)

    def _hide_loop_region(self) -> None:
        """Hide loop region from waveform."""
        if self.loop_region and self.waveform_widget:
            try:
                self.waveform_widget.plot_widget.removeItem(self.loop_region)
                self.loop_region = None
            except Exception as e:
                logging.error(f"[Loop Player] Error hiding loop region: {e}", exc_info=True)

    def _move_loop(self, delta: float) -> None:
        """Move loop position by delta seconds.

        Args:
            delta: Seconds to move (positive = forward, negative = backward)
        """
        if not self.loop_active:
            return

        player = self.context.player
        if not player.current_file:
            return

        track = self.context.database.tracks.get_by_filepath(player.current_file)
        if not track or not track["duration_seconds"]:
            return

        track_duration = track["duration_seconds"]
        loop_duration = self.loop_end - self.loop_start

        # Calculate new positions
        new_start = self.loop_start + delta
        new_end = self.loop_end + delta

        # Clamp to valid range
        if new_start < 0:
            new_start = 0
            new_end = loop_duration
        elif new_end > track_duration:
            new_end = track_duration
            new_start = track_duration - loop_duration

        self.loop_start = new_start
        self.loop_end = new_end

        # Update visual region
        self._update_loop_region()

        logging.debug(f"[Loop Player] Loop moved to {self.loop_start:.2f}s - {self.loop_end:.2f}s")

    def _move_loop_coarse_forward(self) -> None:
        """Move loop forward by coarse step."""
        step = self.context.config.loop_player.coarse_step
        self._move_loop(step)

    def _move_loop_coarse_backward(self) -> None:
        """Move loop backward by coarse step."""
        step = self.context.config.loop_player.coarse_step
        self._move_loop(-step)

    def _move_loop_fine_forward(self) -> None:
        """Move loop forward by fine step."""
        step = self.context.config.loop_player.fine_step
        self._move_loop(step)

    def _move_loop_fine_backward(self) -> None:
        """Move loop backward by fine step."""
        step = self.context.config.loop_player.fine_step
        self._move_loop(-step)

    def _update_loop_region(self) -> None:
        """Update loop region display on waveform."""
        if not self.loop_region or not self.waveform_widget:
            return

        try:
            player = self.context.player
            track = self.context.database.tracks.get_by_filepath(player.current_file)

            if not track or not track["duration_seconds"]:
                return

            track_duration = track["duration_seconds"]
            waveform_length = self.waveform_widget.expected_length
            if waveform_length <= 0:
                return

            x_start = (self.loop_start / track_duration) * waveform_length
            x_end = (self.loop_end / track_duration) * waveform_length

            self.loop_region.setRegion([x_start, x_end])

        except Exception as e:
            logging.error(f"[Loop Player] Error updating loop region: {e}", exc_info=True)

    def _update_button_style(self) -> None:
        """Update button style based on loop state."""
        if not self.loop_button:
            return

        if self.loop_active:
            self.loop_button.setStyleSheet("background-color: #4CAF50; color: white;")
        else:
            self.loop_button.setStyleSheet("")

    def _on_track_loaded(self, track_id: int) -> None:
        """Reset loop when new track is loaded."""
        if self.loop_active:
            self.loop_active = False
            self.position_timer.stop()
            self._hide_loop_region()
            if self.loop_button:
                self.loop_button.setChecked(False)
            self._update_button_style()

    def activate(self, mode: str) -> None:
        """Activate plugin for mode."""
        pass

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for mode."""
        # Stop loop when switching modes
        if self.loop_active:
            self.loop_active = False
            self.position_timer.stop()
            self._hide_loop_region()
            if self.loop_button:
                self.loop_button.setChecked(False)
            self._update_button_style()

    def _on_settings_changed(self) -> None:
        """Reload config when settings change."""
        logging.info("[Loop Player] Settings changed, reloading config from database")

        db = self.context.database

        # Reload duration setting
        duration_setting = db.conn.execute(
            "SELECT setting_value FROM plugin_settings WHERE plugin_name = ? AND setting_key = ?",
            ("loop_player", "duration"),
        ).fetchone()

        if duration_setting:
            try:
                duration = float(duration_setting["setting_value"])
                self.context.config.loop_player.duration = duration
                logging.info(f"[Loop Player] Loop duration: {duration}s")

                # Update button tooltip if button exists
                if self.loop_button:
                    self.loop_button.setToolTip(f"Loop section ({duration}s from current position)")
            except ValueError:
                logging.error(
                    f"[Loop Player] Invalid duration value: {duration_setting['setting_value']}"
                )

        # Reload coarse_step setting
        coarse_setting = db.conn.execute(
            "SELECT setting_value FROM plugin_settings WHERE plugin_name = ? AND setting_key = ?",
            ("loop_player", "coarse_step"),
        ).fetchone()

        if coarse_setting:
            try:
                coarse_step = float(coarse_setting["setting_value"])
                self.context.config.loop_player.coarse_step = coarse_step
                logging.info(f"[Loop Player] Coarse step: {coarse_step}s")
            except ValueError:
                logging.error(
                    f"[Loop Player] Invalid coarse_step value: {coarse_setting['setting_value']}"
                )

        # Reload fine_step setting
        fine_setting = db.conn.execute(
            "SELECT setting_value FROM plugin_settings WHERE plugin_name = ? AND setting_key = ?",
            ("loop_player", "fine_step"),
        ).fetchone()

        if fine_setting:
            try:
                fine_step = float(fine_setting["setting_value"])
                self.context.config.loop_player.fine_step = fine_step
                logging.info(f"[Loop Player] Fine step: {fine_step}s")
            except ValueError:
                logging.error(
                    f"[Loop Player] Invalid fine_step value: {fine_setting['setting_value']}"
                )

    def get_settings_schema(self) -> dict[str, Any]:
        """Return settings schema for configuration UI.

        Returns:
            Dict mapping setting keys to their configuration
        """
        return {
            "duration": {
                "label": "Loop Duration (seconds)",
                "type": "float",
                "default": self.context.config.loop_player.duration,
                "min": 1.0,
                "max": 300.0,
            },
            "coarse_step": {
                "label": "Coarse Step (seconds) - Ctrl+Arrows",
                "type": "float",
                "default": self.context.config.loop_player.coarse_step,
                "min": 0.1,
                "max": 10.0,
            },
            "fine_step": {
                "label": "Fine Step (seconds) - Shift+Arrows",
                "type": "float",
                "default": self.context.config.loop_player.fine_step,
                "min": 0.01,
                "max": 1.0,
            },
        }

    def shutdown(self) -> None:
        """Cleanup on shutdown."""
        if self.position_timer:
            self.position_timer.stop()
        self._hide_loop_region()
