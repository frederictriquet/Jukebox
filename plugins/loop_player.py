"""Loop player plugin for repeating a section of a track."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QPushButton

from jukebox.core.event_bus import Events
from jukebox.core.settings_sync_mixin import SettingsSyncMixin, SyncedSetting

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol

logger = logging.getLogger(__name__)

# Number of shortcut buttons to recent playlists (slot 0 = the most recent).
# Used both to create the buttons and to cap the list of remembered recent
# playlists: this is the single source of truth for the count.
PLAYLIST_BUTTON_COUNT = 3

# Maximum width of a playlist shortcut button. Deliberately kept small so that
# the PLAYLIST_BUTTON_COUNT buttons do not saturate the controls bar; overly
# long names are truncated with an ellipsis.
PLAYLIST_BUTTON_MAX_WIDTH = 90

# Approximate inner margin (padding + border) subtracted from the usable width
# when computing the label ellipsis.
PLAYLIST_LABEL_PADDING = 16


class LoopPlayerPlugin(SettingsSyncMixin):
    """Enable looping a section of the current track."""

    name = "loop_player"
    version = "1.0.0"
    description = "Loop a section of the current track"
    modes = ["jukebox", "curating"]

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol = None  # type: ignore[assignment]
        self.loop_button: QPushButton | None = None
        # Shortcut buttons to the most recently used playlists (slot 0 = the
        # most recent). Single source of truth: one list, ordered by slot, used
        # everywhere (no duplicated named attributes).
        self._playlist_buttons: list[QPushButton] = []
        # Recently used playlists, most recent first, deduplicated.
        self._recent_playlists: list[tuple[int, str]] = []
        # Whether the buttons should be visible (jukebox mode active).
        self._buttons_visible: bool = False
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

        # Subscribe to waveform widget ready event (decoupled from waveform_visualizer)
        self.context.subscribe(Events.WAVEFORM_WIDGET_READY, self._on_waveform_widget_ready)

        # Remember the last used playlist for the quick re-copy button.
        self.context.subscribe(Events.TRACK_ADDED_TO_PLAYLIST, self._on_track_added_to_playlist)

        # Reconcile the shortcuts with the database after a playlist is deleted
        # or renamed (avoids keeping a dead reference).
        self.context.subscribe(Events.PLAYLIST_CHANGED, self._on_playlists_changed)

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

        layout = controls.layout()
        if layout:
            # Loop button
            loop_duration = self.context.config.loop_player.duration
            self.loop_button = QPushButton("⟲")
            self.loop_button.setCheckable(True)
            self.loop_button.setChecked(False)
            self.loop_button.setToolTip(f"Loop section ({loop_duration}s from current position)")
            self.loop_button.setMaximumWidth(40)
            self.loop_button.clicked.connect(self._toggle_loop)
            self._update_button_style()

            # Loop button aligned left: just before the spacer if present.
            stretch_index = self._find_stretch_index(layout)
            if stretch_index >= 0:
                ui_builder.insert_widget_in_layout(layout, stretch_index, self.loop_button)
            else:
                layout.addWidget(self.loop_button)

            # Create the playlist shortcut buttons (single source: the list).
            # Always created, even without a spacer, so that the handlers
            # (_on_track_added_to_playlist / _on_copy_to_recent_playlist) have
            # valid widgets rather than raising an AttributeError.
            self._playlist_buttons = [
                self._create_playlist_button(slot) for slot in range(PLAYLIST_BUTTON_COUNT)
            ]

            # Place the buttons to the right of the spacer (right-aligned,
            # before the replay timer), ordered most recent -> least recent.
            # The spacer position is re-read AFTER inserting the loop button:
            # no magic index offset, robust to insertion order.
            stretch_index = self._find_stretch_index(layout)
            if stretch_index >= 0:
                for offset, btn in enumerate(self._playlist_buttons):
                    ui_builder.insert_widget_in_layout(layout, stretch_index + 1 + offset, btn)
            else:
                for btn in self._playlist_buttons:
                    layout.addWidget(btn)

            self._refresh_playlist_buttons()

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

    def _toggle_loop(self) -> None:
        """Toggle loop mode."""
        if not self.loop_active:
            # Activate loop at current position
            player = self.context.player
            if not player.current_file:
                logger.warning("[Loop Player] No track loaded")
                if self.loop_button:
                    self.loop_button.setChecked(False)
                return

            # Get track duration
            track_duration = self.context.get_current_track_duration()
            if not track_duration:
                logger.warning("[Loop Player] Cannot get track duration")
                if self.loop_button:
                    self.loop_button.setChecked(False)
                return

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
            if self.position_timer is not None:
                self.position_timer.start()

            # Show loop region on waveform
            self._show_loop_region()

            logger.info(
                "[Loop Player] Loop activated: %.1fs - %.1fs", self.loop_start, self.loop_end
            )

            # Emit loop activated event
            self.context.emit(
                Events.LOOP_ACTIVATED,
                loop_start=self.loop_start,
                loop_end=self.loop_end,
                filepath=player.current_file,
            )

        else:
            # Deactivate loop
            self.loop_active = False
            if self.position_timer is not None:
                self.position_timer.stop()
            self._hide_loop_region()
            logger.info("[Loop Player] Loop deactivated")

            # Emit loop deactivated event
            self.context.emit(Events.LOOP_DEACTIVATED)

        self._update_button_style()

    def _check_position(self) -> None:
        """Check playback position and loop if necessary."""
        if not self.loop_active:
            return

        player = self.context.player
        if not player.is_playing():
            return

        # Get track duration
        track_duration = self.context.get_current_track_duration()
        if not track_duration:
            return

        current_pos = player.get_position() * track_duration

        # If we've passed the loop end, jump back to loop start
        if current_pos >= self.loop_end:
            player.set_position(self.loop_start / track_duration)
            logger.debug("[Loop Player] Looping back to %.1fs", self.loop_start)

    def _show_loop_region(self) -> None:
        """Show loop region on waveform."""
        if not self.waveform_widget:
            return

        try:
            import pyqtgraph as pg

            # Get track duration
            track_duration = self.context.get_current_track_duration()
            if not track_duration:
                return

            waveform_length = self.waveform_widget.expected_length
            if waveform_length <= 0:
                return

            # Convert seconds to waveform x coordinates
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
            logger.error("[Loop Player] Error showing loop region: %s", e, exc_info=True)

    def _hide_loop_region(self) -> None:
        """Hide loop region from waveform."""
        if self.loop_region and self.waveform_widget:
            try:
                self.waveform_widget.plot_widget.removeItem(self.loop_region)
                self.loop_region = None
            except Exception as e:
                logger.error("[Loop Player] Error hiding loop region: %s", e, exc_info=True)

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

        track_duration = self.context.get_current_track_duration()
        if not track_duration:
            return

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

        # Notify other plugins of the new loop position
        self.context.emit(
            Events.LOOP_ACTIVATED,
            loop_start=self.loop_start,
            loop_end=self.loop_end,
            filepath=player.current_file,
        )

        logger.debug("[Loop Player] Loop moved to %.2fs - %.2fs", self.loop_start, self.loop_end)

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
            track_duration = self.context.get_current_track_duration()
            if not track_duration:
                return

            waveform_length = self.waveform_widget.expected_length
            if waveform_length <= 0:
                return

            x_start = (self.loop_start / track_duration) * waveform_length
            x_end = (self.loop_end / track_duration) * waveform_length

            self.loop_region.setRegion([x_start, x_end])

        except Exception as e:
            logger.error("[Loop Player] Error updating loop region: %s", e, exc_info=True)

    def _update_button_style(self) -> None:
        """Update button style based on loop state."""
        if not self.loop_button:
            return

        if self.loop_active:
            self.loop_button.setStyleSheet("background-color: #4CAF50; color: white;")
        else:
            self.loop_button.setStyleSheet("")

    @staticmethod
    def _find_stretch_index(layout: Any) -> int:
        """Return the index of the spacer in the layout, or -1 if there is none."""
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.spacerItem():
                return i
        return -1

    def _create_playlist_button(self, slot: int) -> QPushButton:
        """Create a shortcut button to the recent playlist at the given slot.

        Args:
            slot: Index into the recent playlists list (0 = the most recent).
        """
        btn = QPushButton("→ playlist")
        btn.setToolTip("Copier le morceau courant dans une playlist récente")
        btn.setMaximumWidth(PLAYLIST_BUTTON_MAX_WIDTH)
        btn.setEnabled(False)
        btn.setVisible(False)
        btn.clicked.connect(lambda *_a, s=slot: self._on_copy_to_recent_playlist(s))
        return btn

    @staticmethod
    def _format_playlist_label(btn: QPushButton, name: str) -> str:
        """Build the "→ name" label, truncating the name (ellipsis) if needed.

        Prevents a long name from overflowing the button and saturating the
        controls bar; the full name stays accessible via the tooltip.
        """
        prefix = "→ "
        metrics = btn.fontMetrics()
        # Usable width for the name, with prefix and inner margins subtracted.
        available = btn.maximumWidth() - metrics.horizontalAdvance(prefix) - PLAYLIST_LABEL_PADDING
        elided = metrics.elidedText(name, Qt.TextElideMode.ElideRight, max(available, 0))
        return f"{prefix}{elided}"

    def _refresh_playlist_buttons(self) -> None:
        """Update label, tooltip, enabled state and visibility of the buttons."""
        for slot, btn in enumerate(self._playlist_buttons):
            has_playlist = slot < len(self._recent_playlists)
            if has_playlist:
                _, name = self._recent_playlists[slot]
                btn.setText(self._format_playlist_label(btn, name))
                btn.setToolTip(f"Copier le morceau courant dans « {name} »")
            else:
                btn.setText("→ playlist")
                btn.setToolTip("Copier le morceau courant dans une playlist récente")
            btn.setEnabled(has_playlist)
            # Hidden until there are enough recent playlists for this slot.
            btn.setVisible(self._buttons_visible and has_playlist)

    def _on_track_added_to_playlist(self, playlist_id: int, playlist_name: str) -> None:
        """Remember recent playlists and refresh the re-copy buttons."""
        # Move the playlist to the front, deduplicated, and cap at the button count.
        self._recent_playlists = [(playlist_id, playlist_name)] + [
            (pid, pname) for pid, pname in self._recent_playlists if pid != playlist_id
        ]
        self._recent_playlists = self._recent_playlists[:PLAYLIST_BUTTON_COUNT]
        self._refresh_playlist_buttons()

    def _on_playlists_changed(self) -> None:
        """Reconcile recent playlists with the database (deletion/rename).

        A deleted playlist is removed from the shortcuts (no more dead
        reference); a renamed playlist has its label updated.
        """
        database = self.context.database
        if database.conn is None:
            logger.error("[Loop Player] Base de données non connectée")
            return
        try:
            playlists = database.playlists.get_all()
        except Exception:
            logger.exception("[Loop Player] Erreur lors du rafraîchissement des playlists récentes")
            return

        names_by_id = {row["id"]: row["name"] for row in playlists}
        # Keep the recency order, drop missing ids, realign the names.
        reconciled = [
            (pid, names_by_id[pid]) for pid, _ in self._recent_playlists if pid in names_by_id
        ]
        # Adding a track emits PLAYLIST_CHANGED *then* TRACK_ADDED_TO_PLAYLIST
        # for the same mutation. On a plain add, the reconciliation changes
        # nothing (no deletion or rename) and _on_track_added_to_playlist will
        # refresh afterwards; repainting here would be redundant. So we only
        # update the buttons when a deletion/rename actually modified the list,
        # guaranteeing a single refresh per mutation.
        if reconciled == self._recent_playlists:
            return
        self._recent_playlists = reconciled
        self._refresh_playlist_buttons()

    def _on_copy_to_recent_playlist(self, slot: int) -> None:
        """Copy the current track into the recent playlist at the given slot."""
        if slot >= len(self._recent_playlists):
            return
        playlist_id, _ = self._recent_playlists[slot]
        filepath = self.context.player.current_file
        if not filepath:
            return
        self.context.app._on_add_to_playlist(filepath, playlist_id)

    def _on_track_loaded(self, track_id: int) -> None:
        """Reset loop when new track is loaded."""
        if self.loop_active:
            self.loop_active = False
            if self.position_timer is not None:
                self.position_timer.stop()
            self._hide_loop_region()
            if self.loop_button:
                self.loop_button.setChecked(False)
            self._update_button_style()

    def _on_waveform_widget_ready(self, widget: Any) -> None:
        """Handle waveform widget ready event.

        Args:
            widget: The waveform widget instance.
        """
        self.waveform_widget = widget
        logger.debug("[Loop Player] Waveform widget received via event")

    def activate(self, mode: str) -> None:
        """Activate plugin for mode."""
        if mode == "jukebox":
            self._buttons_visible = True
            self._refresh_playlist_buttons()

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for mode."""
        if mode == "jukebox":
            self._buttons_visible = False
            self._refresh_playlist_buttons()
        # Stop loop when switching modes
        if self.loop_active:
            self.loop_active = False
            if self.position_timer is not None:
                self.position_timer.stop()
            self._hide_loop_region()
            if self.loop_button:
                self.loop_button.setChecked(False)
            self._update_button_style()

    _synced_settings = [
        SyncedSetting("duration", float),
        SyncedSetting("coarse_step", float),
        SyncedSetting("fine_step", float),
    ]

    def _on_settings_changed(self) -> None:
        """Reload config when settings change."""
        logger.info("[Loop Player] Settings changed, reloading config from database")
        self._sync_settings_from_db()

    def _after_settings_sync(self, config: Any) -> None:
        if self.loop_button:
            self.loop_button.setToolTip(f"Loop section ({config.duration}s from current position)")

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
