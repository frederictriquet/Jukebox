"""Cue Maker plugin - main plugin class."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from plugins.cue_maker.widgets.bottom_drawer import BottomDrawer

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol
    from plugins.cue_maker.analyzer import AnalyzeWorker
    from plugins.cue_maker.widgets.cue_maker_widget import CueMakerWidget

logger = logging.getLogger(__name__)


class CueMakerPlugin:
    """Plugin for creating cue sheets from DJ mixes.

    This plugin provides a dedicated mode for:
    - Loading and analyzing DJ mixes with shazamix
    - Validating and correcting identified tracks
    - Adjusting timestamps manually or via waveform
    - Adding tracks manually via search/directory navigator
    - Exporting to standard CUE format

    Active only in cue_maker mode.
    """

    name = "cue_maker"
    version = "1.0.0"
    description = "Create cue sheets for DJ mixes"
    modes = ["cue_maker"]  # Active only in cue_maker mode

    def __init__(self) -> None:
        """Initialize plugin state."""
        self.context: PluginContextProtocol | None = None
        self._ui_builder: UIBuilderProtocol | None = None
        self.main_widget: CueMakerWidget | None = None
        self._analyzer: AnalyzeWorker | None = None
        self._cue_context_action: Any | None = None
        self._original_central: QWidget | None = None
        self._splitter: QSplitter | None = None
        self._nav_dock: Any | None = None
        self._saved_bottom_widgets: list[QWidget] = []
        self._drawer: BottomDrawer | None = None
        self._drawer_genre_buttons: QWidget | None = None

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin with application context.

        Args:
            context: Application context providing access to services
        """
        self.context = context
        self._active = False

        # Listen for explicit "add track to cue" requests (e.g. from directory navigator)
        from jukebox.core.event_bus import Events

        context.subscribe(Events.CUE_ADD_TRACK, self._on_cue_add_track)
        logger.info("[Cue Maker] Plugin initialized")

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register UI elements.

        Creates the main cue maker widget and adds it to the bottom of the main window.
        The widget is hidden by default and shown when entering cue_maker mode.

        Args:
            ui_builder: UI builder for adding UI elements
        """
        from plugins.cue_maker.widgets.cue_maker_widget import CueMakerWidget

        assert self.context is not None
        self._ui_builder = ui_builder
        self.main_widget = CueMakerWidget(self.context)
        ui_builder.add_bottom_widget(self.main_widget)

        # Hide initially - activate() will show it when entering cue_maker mode
        self.main_widget.setVisible(False)

        # Connect signals
        self.main_widget.analyze_requested.connect(self._on_analyze)

        logger.info("[Cue Maker] UI registered")

    def activate(self, mode: str) -> None:
        """Activate plugin when entering cue_maker mode.

        Rebuilds the central widget with:
        - Top: cue maker widget (takes all available space)
        - Bottom: drawer with directory navigator, search bar, track list, controls

        Args:
            mode: Mode being activated (should be "cue_maker")
        """
        self._active = True
        assert self.context is not None

        app = self.context.app
        nav_plugin = app.plugin_manager.plugins.get("directory_navigator")

        # Save original central widget
        self._original_central = app.centralWidget()

        # Hide the directory navigator dock and reparent its widget
        nav_widget = None
        if nav_plugin and hasattr(nav_plugin, "widget") and nav_plugin.widget:
            nav_widget = nav_plugin.widget
            self._nav_dock = nav_widget.parent()
            if self._nav_dock and hasattr(self._nav_dock, "setVisible"):
                self._nav_dock.setVisible(False)
            # Reparent: extract from dock
            nav_widget.setParent(None)

        # Detach ALL widgets from original layout before setCentralWidget
        # destroys it. Other plugins' bottom widgets (waveform, genre_suggester)
        # would be destroyed otherwise since they're children of the old central.
        known_widgets = {app.search_bar, app.track_list, app.controls, self.main_widget}
        self._saved_bottom_widgets = []
        if self._original_central is not None:
            original_layout = self._original_central.layout()
            if original_layout is not None:
                while original_layout.count():
                    item = original_layout.takeAt(0)
                    w = item.widget() if item else None
                    if w:
                        if w not in known_widgets:
                            self._saved_bottom_widgets.append(w)
                            w.setVisible(False)
                        w.setParent(None)

        # Build new layout:
        # Central widget with vertical layout
        central = QWidget()
        v_layout = QVBoxLayout(central)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(0)

        # Top: CueMakerWidget (stretch=1, takes all available space)
        if self.main_widget:
            v_layout.addWidget(self.main_widget, stretch=1)
            self.main_widget.setVisible(True)

        # Bottom: BottomDrawer with library content
        self._drawer = BottomDrawer()

        # Create content for drawer:
        # - Horizontal splitter: DirNav | (SearchBar + TrackList)
        h_splitter = QSplitter(Qt.Orientation.Horizontal)
        if nav_widget:
            h_splitter.addWidget(nav_widget)
            nav_widget.setVisible(True)

        right_container = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(app.search_bar)
        right_layout.addWidget(app.track_list, stretch=1)
        right_container.setLayout(right_layout)
        h_splitter.addWidget(right_container)

        # Set horizontal proportions (25% navigator, 75% tracklist)
        h_splitter.setSizes([250, 750])

        # Create drawer content with splitter + controls + waveform
        drawer_content = QWidget()
        dc_layout = QVBoxLayout(drawer_content)
        dc_layout.setContentsMargins(0, 0, 0, 0)
        dc_layout.addWidget(h_splitter, stretch=1)

        dc_layout.addWidget(app.controls, stretch=0)

        # Add genre filter buttons to drawer (from genre_filter plugin)
        genre_filter_plugin = app.plugin_manager.plugins.get("genre_filter")
        if genre_filter_plugin and hasattr(genre_filter_plugin, "_make_button_container"):
            # Create a second set of genre buttons for the drawer
            self._drawer_genre_buttons = genre_filter_plugin._make_button_container(
                genre_filter_plugin._on_filter_changed
            )
            dc_layout.addWidget(self._drawer_genre_buttons, stretch=0)

        # Re-add waveform visualizer widget (from waveform_visualizer plugin)
        # It was detached to avoid destruction when we replaced the central widget
        waveform_plugin = app.plugin_manager.plugins.get("waveform_visualizer")
        if (
            waveform_plugin
            and hasattr(waveform_plugin, "waveform_widget")
            and waveform_plugin.waveform_widget
        ):
            waveform_widget = waveform_plugin.waveform_widget
            waveform_widget.setVisible(True)
            dc_layout.addWidget(waveform_widget, stretch=0)
            # Remove from saved widgets to avoid adding it twice in deactivate()
            try:
                self._saved_bottom_widgets.remove(waveform_widget)
            except ValueError:
                pass

        self._drawer.set_content(drawer_content)
        v_layout.addWidget(self._drawer)

        # Replace central widget
        app.setCentralWidget(central)

        # Add "Add to Cue Sheet" in track context menu
        if self._ui_builder and self._cue_context_action is None:
            self._cue_context_action = self._ui_builder.add_track_context_action(
                "Add to Cue Sheet",
                self._add_track_to_cue,
                separator_before=True,
            )

        logger.debug("[Cue Maker] Activated for %s mode", mode)

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin when leaving cue_maker mode.

        Restores the original central widget layout with search bar, tracklist,
        and player controls. Puts the navigator widget back into its dock.

        Args:
            mode: Mode being deactivated
        """
        self._active = False
        assert self.context is not None

        app = self.context.app

        if self.main_widget:
            self.main_widget.stop_mix_playback()
            self.main_widget.cleanup_workers()
            self.main_widget.setVisible(False)

        # Remove widgets from drawer layout before restoring
        # This includes search_bar, track_list, controls, and waveform_widget
        for w in [app.search_bar, app.track_list, app.controls]:
            w.setParent(None)
        if self.main_widget:
            self.main_widget.setParent(None)

        # Remove drawer genre buttons
        if self._drawer_genre_buttons:
            self._drawer_genre_buttons.setParent(None)
            self._drawer_genre_buttons = None

        # Remove waveform widget from drawer (was added in activate)
        waveform_plugin = app.plugin_manager.plugins.get("waveform_visualizer")
        if (
            waveform_plugin
            and hasattr(waveform_plugin, "waveform_widget")
            and waveform_plugin.waveform_widget
        ):
            waveform_plugin.waveform_widget.setParent(None)
            self._saved_bottom_widgets.append(waveform_plugin.waveform_widget)

        # Restore navigator widget to its dock
        nav_plugin = app.plugin_manager.plugins.get("directory_navigator")
        if nav_plugin and hasattr(nav_plugin, "widget") and nav_plugin.widget:
            nav_widget = nav_plugin.widget
            nav_widget.setParent(None)
            if self._nav_dock and hasattr(self._nav_dock, "setWidget"):
                self._nav_dock.setWidget(nav_widget)
                # Don't show dock here - directory_navigator.activate() handles it
        self._nav_dock = None

        # Rebuild original central widget
        central = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(app.search_bar)
        layout.addWidget(app.track_list, stretch=1)
        layout.addWidget(app.controls, stretch=0)
        if self.main_widget:
            layout.addWidget(self.main_widget)
        # Restore other plugins' bottom widgets (waveform, genre_suggester, etc.)
        for w in self._saved_bottom_widgets:
            w.setVisible(True)
            layout.addWidget(w)
        self._saved_bottom_widgets = []
        central.setLayout(layout)
        app.setCentralWidget(central)

        # Clean up references
        self._splitter = None
        self._drawer = None
        self._original_central = None

        # Remove context menu action
        if self._ui_builder and self._cue_context_action is not None:
            try:
                self._ui_builder.track_context_actions.remove(  # type: ignore[attr-defined]
                    self._cue_context_action
                )
            except ValueError:
                pass
            self._cue_context_action = None

        logger.debug("[Cue Maker] Deactivated for %s mode", mode)

    def shutdown(self) -> None:
        """Cleanup resources when plugin is unloaded."""
        if self._analyzer is not None:
            if self._analyzer.isRunning():
                self._analyzer.requestInterruption()
                self._analyzer.quit()
                self._analyzer.wait(5000)
            self._analyzer = None
        if self.main_widget:
            self.main_widget.cleanup_workers()
        self.main_widget = None
        self.context = None
        logger.info("[Cue Maker] Plugin shut down")

    # --- Analysis ---

    def _on_analyze(self) -> None:
        """Start shazamix analysis of the loaded mix.

        Checks the persistent cache first. If cached results exist for the same
        file (same path, size, mtime), they are loaded instantly. Otherwise a
        background AnalyzeWorker is started and results are cached on completion.
        """
        if not self.main_widget or not self.context:
            return

        mix_path = self.main_widget.model.sheet.mix_filepath
        if not mix_path:
            return

        # Get config
        cue_config = getattr(self.context.config, "cue_maker", None)
        db_path = str(cue_config.shazamix_db_path.expanduser()) if cue_config else ""
        if not db_path:
            logger.warning("[Cue Maker] No shazamix database path configured")
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self.main_widget,
                "Configuration",
                "No shazamix database path configured.\n" "Set shazamix_db_path in config.yaml.",
            )
            return

        from plugins.cue_maker.analyzer import AnalyzeWorker

        self._analyzer = AnalyzeWorker(
            mix_path,
            db_path,
            segment_duration=cue_config.segment_duration if cue_config else 30.0,
            overlap=cue_config.overlap if cue_config else 15.0,
            max_workers=cue_config.max_workers if cue_config else 4,
        )
        self._analyzer.setObjectName("CueMaker-AnalyzeWorker")
        self._analyzer.progress.connect(self.main_widget.set_analysis_progress)
        self._analyzer.finished.connect(self._on_analysis_done)
        self._analyzer.error.connect(self.main_widget.on_analysis_error)

        self.main_widget.analyze_btn.setEnabled(False)
        self._analyzer.start()
        logger.info("[Cue Maker] Analysis started for %s", mix_path)

        from jukebox.core.event_bus import Events

        self.context.emit(Events.STATUS_MESSAGE, message="Cue Maker: Analyzing mix...")

    def _on_analysis_done(self, entries: list) -> None:
        """Handle analysis completion and update UI."""
        if self.main_widget:
            self.main_widget.on_analysis_complete(entries)
            # Cache entries for instant reload on next load
            mix_path = self.main_widget.model.sheet.mix_filepath
            if mix_path:
                from plugins.cue_maker.cache import save_entries_cache

                save_entries_cache(mix_path, entries)
        if self.context:
            from jukebox.core.event_bus import Events

            n = len(entries)
            msg = f"Cue Maker: Found {n} track{'s' if n != 1 else ''} in mix"
            self.context.emit(Events.STATUS_MESSAGE, message=msg)

    # --- Track addition to cue sheet ---

    def _add_track_to_cue(self, track: dict[str, Any]) -> None:
        """Add a track to the cue sheet from the context menu.

        Args:
            track: Track dictionary with artist, title, filepath, id keys.
        """
        if not self.main_widget or not self.context:
            return

        artist = track.get("artist", "") or ""
        title = track.get("title", "") or ""
        filepath = track.get("filepath", "") or ""
        track_id = track.get("id", 0)

        # Get duration from database
        duration_ms = 0
        if track_id:
            db = self.context.database
            if db and hasattr(db, "tracks"):
                track_info = db.tracks.get_by_id(track_id)
                if track_info:
                    duration_s = track_info["duration_seconds"] or 0
                    duration_ms = int(duration_s * 1000)

        self.main_widget.model.add_manual_entry(
            start_time_ms=0,
            artist=artist,
            title=title,
        )

        # Update filepath and duration on the newly added entry
        for entry in self.main_widget.model.sheet.entries:
            if entry.filepath == "" and entry.artist == artist and entry.title == title:
                entry.filepath = str(filepath)
                entry.track_id = track_id
                if duration_ms > 0:
                    entry.duration_ms = duration_ms
                break

        logger.info("[Cue Maker] Added track to cue: %s - %s", artist, title)

    def _on_cue_add_track(self, track_id: int) -> None:
        """Handle CUE_ADD_TRACK event."""
        if not self._active or not self.main_widget or not self.context:
            return

        db = self.context.database
        if not db.conn:  # type: ignore[attr-defined]
            return

        row = db.conn.execute(  # type: ignore[attr-defined]
            "SELECT id, artist, title, filepath FROM tracks WHERE id = ?",
            (track_id,),
        ).fetchone()
        if not row:
            return

        self._add_track_to_cue(dict(row))
