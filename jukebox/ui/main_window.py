"""Main application window."""

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jukebox.core.audio_player import AudioPlayer
from jukebox.core.config import JukeboxConfig
from jukebox.core.database import Database
from jukebox.core.event_bus import EventBus, Events
from jukebox.core.mode_manager import AppMode, ModeManager
from jukebox.core.plugin_manager import PluginContext, PluginManager
from jukebox.core.shortcut_manager import ShortcutManager
from jukebox.ui.components.player_controls import PlayerControls
from jukebox.ui.components.search_bar import SearchBar
from jukebox.ui.components.track_cell_renderer import WaveformStyler
from jukebox.ui.components.track_list import TrackList
from jukebox.ui.ui_builder import UIBuilder
from jukebox.utils.metadata import MetadataExtractor
from jukebox.utils.scanner import FileScanner


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, config: JukeboxConfig):
        """Initialize main window.

        Args:
            config: Application configuration
        """
        super().__init__()
        self.config = config

        # Database
        db_path = Path.home() / ".jukebox" / "jukebox.db"
        self.database = Database(db_path)
        self.database.connect()
        self.database.initialize_schema()

        # Audio player
        self.player = AudioPlayer()

        # Event bus
        self.event_bus = EventBus()

        # Subscribe to events
        self.event_bus.subscribe(Events.TRACKS_ADDED, self._on_tracks_changed)
        # Subscribe to TRACK_DELETED early so MainWindow is called BEFORE TrackListModel
        self.event_bus.subscribe(Events.TRACK_DELETED, self._on_track_deleted)
        # Subscribe to navigation events
        self.event_bus.subscribe(Events.SELECT_NEXT_TRACK, self._on_select_next_track)
        self.event_bus.subscribe(Events.SELECT_PREVIOUS_TRACK, self._on_select_previous_track)
        self.event_bus.subscribe(Events.SELECT_RANDOM_TRACK, self._on_select_random_track)
        # Subscribe to track list manipulation events
        self.event_bus.subscribe(Events.LOAD_TRACK_LIST, self._on_load_track_list)
        # Subscribe to capability events (plugins declare their capabilities)
        self.event_bus.subscribe(
            Events.POSITION_SEEKING_PROVIDED, self._on_position_seeking_provided
        )

        # Timer for updating position
        self.position_timer = QTimer()
        self.position_timer.setInterval(100)
        self.position_timer.timeout.connect(self._update_position)

        # Fallback position slider (if no plugin provides position seeking)
        self.fallback_position_slider: Any = None
        self._position_seeking_provided = False

        self._init_ui()
        self._connect_signals()
        self._register_shortcuts()
        self._load_plugins()
        self._load_tracks_from_db()

    def _init_ui(self) -> None:
        """Initialize UI."""
        self.setWindowTitle(self.config.ui.window_title)
        self.resize(self.config.ui.window_width, self.config.ui.window_height)

        # Central widget
        central = QWidget()
        layout = QVBoxLayout()

        # Toolbar
        toolbar = QHBoxLayout()
        self.add_files_btn = QPushButton("Add Files...")
        self.scan_dir_btn = QPushButton("Scan Directory...")
        self.add_files_btn.clicked.connect(self._add_files)
        self.scan_dir_btn.clicked.connect(self._scan_directory)
        toolbar.addWidget(self.add_files_btn)
        toolbar.addWidget(self.scan_dir_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Search bar
        self.search_bar = SearchBar()
        self.search_bar.search_triggered.connect(self._perform_search)
        layout.addWidget(self.search_bar)

        # Configure waveform cache size from config
        WaveformStyler.configure(self.config.ui.waveform_cache_size)

        # Track list (with stretch to take all available space)
        self.track_list = TrackList(
            database=self.database,
            event_bus=self.event_bus,
            config=self.config,
            mode=self.config.ui.mode,
        )
        layout.addWidget(self.track_list, stretch=1)

        # Connect to model's row_deleted signal (emitted after deletion is complete)
        self.track_list.model().row_deleted.connect(self._on_row_deleted_complete)

        # Player controls (no stretch - fixed height)
        self.controls = PlayerControls()
        layout.addWidget(self.controls, stretch=0)

        # Set initial volume
        self.controls.set_volume(self.config.audio.default_volume)
        self.player.set_volume(self.config.audio.default_volume)

        central.setLayout(layout)
        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        """Connect signals between components."""
        # Track selection
        self.track_list.track_selected.connect(self._load_and_play)

        # Drag and drop
        self.track_list.files_dropped.connect(self._on_files_dropped)

        # Player controls
        self.controls.play_clicked.connect(self._on_play)
        self.controls.pause_clicked.connect(self._on_pause)
        self.controls.stop_clicked.connect(self._on_stop)
        self.controls.volume_changed.connect(self.player.set_volume)

        # Player feedback
        self.player.volume_changed.connect(self.controls.set_volume)
        self.player.state_changed.connect(self._on_player_state_changed)

    def _register_shortcuts(self) -> None:
        """Register default keyboard shortcuts."""
        self.shortcut_manager = ShortcutManager(self)
        shortcuts = self.config.shortcuts

        # Playback controls
        self.shortcut_manager.register(shortcuts.play_pause, self._toggle_play_pause)
        self.shortcut_manager.register(shortcuts.pause, self._on_pause)
        self.shortcut_manager.register(shortcuts.stop, self._on_stop)

        # Volume controls
        self.shortcut_manager.register(shortcuts.volume_up, self._increase_volume)
        self.shortcut_manager.register(shortcuts.volume_down, self._decrease_volume)

        # Application
        self.shortcut_manager.register(shortcuts.quit, self.close)
        self.shortcut_manager.register(shortcuts.focus_search, lambda: self.search_bar.setFocus())

    def _toggle_play_pause(self) -> None:
        """Toggle between play and pause."""
        if self.player.is_playing():
            self._on_pause()
        else:
            self._on_play()

    def _increase_volume(self) -> None:
        """Increase volume by 10."""
        current = self.player.get_volume()
        self.player.set_volume(min(100, current + 10))

    def _decrease_volume(self) -> None:
        """Decrease volume by 10."""
        current = self.player.get_volume()
        self.player.set_volume(max(0, current - 10))

    def _add_files(self) -> None:
        """Open file dialog to add audio files."""
        formats = " ".join(f"*.{fmt}" for fmt in self.config.audio.supported_formats)
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Audio Files",
            str(self.config.audio.music_directory),
            f"Audio Files ({formats});;All Files (*)",
        )

        if files:
            mode = self._get_current_mode()
            for file in files:
                filepath = Path(file)
                metadata = MetadataExtractor.extract(filepath)
                self.database.add_track(metadata, mode=mode)

            self._load_tracks_from_db()

    def _scan_directory(self) -> None:
        """Scan directory for audio files."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Music Directory", str(self.config.audio.music_directory)
        )

        if not directory:
            return

        progress = QProgressDialog("Scanning...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)

        def update_progress(current: int, total: int) -> None:
            progress.setValue(int(current / total * 100))
            QApplication.processEvents()

        mode = self._get_current_mode()
        scanner = FileScanner(
            self.database, self.config.audio.supported_formats, update_progress, mode=mode
        )
        added = scanner.scan_directory(Path(directory), recursive=True)

        progress.close()
        QMessageBox.information(self, "Scan Complete", f"Added {added} tracks to {mode} mode")
        self._load_tracks_from_db()

        # Emit event to notify plugins (start batch processing)
        if added > 0:
            self.event_bus.emit(Events.TRACKS_ADDED)

    def _perform_search(self, query: str) -> None:
        """Perform FTS5 search within current mode."""
        # Save current playing track
        current_track = self.player.current_file if self.player.current_file else None

        self.track_list.clear_tracks()
        mode = self._get_current_mode()
        if not query:
            tracks = self.database.get_all_tracks(mode=mode)
        else:
            tracks = self.database.search_tracks(query, mode=mode)
        for track in tracks:
            self.track_list.add_track(
                Path(track["filepath"]),
                track["title"],
                track["artist"],
                track["genre"] if "genre" in track else None,
                track["duration_seconds"] if "duration_seconds" in track else None,
            )

        # Restore selection of current playing track
        if current_track:
            model = self.track_list.model()
            row = model.find_row_by_filepath(current_track)
            if row >= 0:
                self.track_list.selectRow(row)

    def _load_tracks_from_db(self) -> None:
        """Load all tracks from database for current mode."""
        self.track_list.clear_tracks()
        mode = self._get_current_mode()
        tracks = self.database.get_all_tracks(mode=mode)
        logging.debug(f"[MainWindow] Loaded {len(tracks)} tracks for mode {mode}")
        for track in tracks:
            self.track_list.add_track(
                Path(track["filepath"]),
                track["title"],
                track["artist"],
                track["genre"] if "genre" in track else None,
                track["duration_seconds"] if "duration_seconds" in track else None,
            )

    def _on_tracks_changed(self) -> None:
        """Handle tracks added/changed event - reload track list."""
        # Save current selection (track filepath)
        current_track = None
        if self.player.current_file:
            current_track = self.player.current_file

        # Reload tracks
        self._load_tracks_from_db()

        # Restore selection of current playing track
        if current_track:
            model = self.track_list.model()
            row = model.find_row_by_filepath(current_track)
            if row >= 0:
                self.track_list.selectRow(row)

    def _on_track_deleted(self, filepath: Path) -> None:
        """Handle track deletion - stop current playback and determine next track.

        This is called BEFORE TrackListModel removes the row, so we can query the model.

        Args:
            filepath: Path of deleted track
        """
        # Check if the deleted file was currently playing
        was_deleted_file_playing = self.player.current_file and self.player.current_file == filepath

        # Find the row that will be deleted
        model = self.track_list.model()
        deleted_row = model.find_row_by_filepath(filepath)

        logging.info(
            f"[MainWindow] Track deleted: {filepath.name}, row={deleted_row}, was_playing={was_deleted_file_playing}"
        )

        # Stop current playback if the deleted file was playing
        if was_deleted_file_playing:
            self.player.stop()
            # Timer is managed by _on_player_state_changed
            logging.debug("[MainWindow] Stopped playback of deleted track")

            # Calculate next track to play BEFORE the model removes the row
            # After deletion, row N becomes the "next" track (what was N+1)
            total_rows = model.rowCount()

            if total_rows <= 1:
                # This was the last track (will be 0 after deletion)
                self.setWindowTitle(self.config.ui.window_title)
                logging.info("[MainWindow] No more tracks after deletion")
                return

            # Determine which row to play after deletion
            if deleted_row >= 0:
                if deleted_row < total_rows - 1:
                    # Get the filepath of the NEXT track (row+1) before deletion
                    next_index = model.index(deleted_row + 1, 0)
                    next_filepath = model.data(next_index, Qt.ItemDataRole.UserRole)
                    logging.debug(
                        f"[MainWindow] Next track at row {deleted_row + 1}: {next_filepath}"
                    )
                else:
                    # Was last track, get the previous track
                    prev_index = model.index(deleted_row - 1, 0)
                    next_filepath = model.data(prev_index, Qt.ItemDataRole.UserRole)
                    logging.debug(
                        f"[MainWindow] Was last, previous track at row {deleted_row - 1}: {next_filepath}"
                    )
            else:
                # Couldn't find row - get first track
                first_index = model.index(0, 0)
                next_filepath = model.data(first_index, Qt.ItemDataRole.UserRole)
                logging.debug(
                    f"[MainWindow] Couldn't find row, playing first track: {next_filepath}"
                )

            # Save filepath to play after model update (no Timer needed!)
            if next_filepath:
                self.deleted_track_next_filepath = next_filepath
            else:
                logging.error("[MainWindow] Could not determine next track filepath")

    def _on_row_deleted_complete(self, deleted_row_index: int) -> None:
        """Called after TrackListModel has completed row deletion.

        Args:
            deleted_row_index: The row that was deleted
        """
        # Check if we saved a filepath to play
        if not hasattr(self, "deleted_track_next_filepath"):
            return

        next_filepath = self.deleted_track_next_filepath
        delattr(self, "deleted_track_next_filepath")

        # Find the row of this filepath (it has shifted after deletion)
        model = self.track_list.model()
        row = model.find_row_by_filepath(next_filepath)

        if row >= 0:
            logging.debug(f"[MainWindow] Playing next track at row {row}: {next_filepath.name}")
            self.track_list.selectRow(row)
            self._load_and_play(next_filepath)
        else:
            logging.error(f"[MainWindow] Could not find next filepath: {next_filepath}")

    def _on_files_dropped(self, paths: list[Path]) -> None:
        """Handle files/directories dropped on track list."""
        from jukebox.utils.metadata import MetadataExtractor
        from jukebox.utils.scanner import FileScanner

        mode = self._get_current_mode()

        # Scan all paths (files and directories)
        for path in paths:
            if path.is_file():
                # Single file - check if it's a supported format
                if path.suffix.lower().lstrip(".") in self.config.audio.supported_formats:
                    try:
                        # Extract metadata and add to database
                        metadata = MetadataExtractor.extract(path)
                        self.database.add_track(metadata, mode=mode)
                    except ValueError as e:
                        # Empty or invalid audio file - skip it
                        logging.warning(f"Skipping invalid file {path}: {e}")
            elif path.is_dir():
                # Directory - scan recursively
                scanner = FileScanner(self.database, self.config.audio.supported_formats, mode=mode)
                scanner.scan_directory(path, recursive=True)

        # Emit event to notify plugins
        self.event_bus.emit(Events.TRACKS_ADDED)

    def _load_and_play(self, filepath: Path) -> None:
        """Load and play selected track.

        Args:
            filepath: Path to audio file
        """
        if self.player.load(filepath):
            # Get track ID and emit event
            if self.database.conn:
                track = self.database.conn.execute(
                    "SELECT id FROM tracks WHERE filepath = ?", (str(filepath),)
                ).fetchone()
                if track:
                    logging.debug(f"[MainWindow] Emitting TRACK_LOADED: id={track['id']}")
                    self.event_bus.emit(Events.TRACK_LOADED, track_id=track["id"])
                else:
                    logging.error(f"[MainWindow] Could not find track in database: {filepath}")

            self.player.play()
            self.setWindowTitle(f"{self.config.ui.window_title} - {filepath.name}")
            # Timer is managed by _on_player_state_changed

    def _on_play(self) -> None:
        """Handle play button click."""
        # If no track loaded, load selected track
        if self.player.current_file is None:
            selected = self.track_list.get_selected_track()
            if selected and self.player.load(selected):
                self.setWindowTitle(f"{self.config.ui.window_title} - {selected.name}")

        self.player.play()
        # Timer is managed by _on_player_state_changed

    def _on_pause(self) -> None:
        """Handle pause button click."""
        self.player.pause()
        # Timer is managed by _on_player_state_changed

    def _on_stop(self) -> None:
        """Handle stop button click."""
        self.player.stop()
        # Timer and position reset are managed by _on_player_state_changed

    def _on_player_state_changed(self, state: str) -> None:
        """Handle player state changes (from any source, including plugins).

        Centralizes position timer management - all play/pause/stop actions
        trigger this via the player's state_changed signal.
        """
        if state == "playing":
            self.position_timer.start()
        elif state == "paused":
            self.position_timer.stop()
        elif state == "stopped":
            self.position_timer.stop()
            self.event_bus.emit(Events.POSITION_UPDATE, position=0.0)

    def _update_position(self) -> None:
        """Update position based on player position."""
        if self.player.is_playing():
            position = self.player.get_position()
            # Emit for plugins (waveform cursor)
            self.event_bus.emit(Events.POSITION_UPDATE, position=position)
            # Update fallback slider if exists
            if self.fallback_position_slider and self.fallback_position_slider.isVisible():
                self.fallback_position_slider.blockSignals(True)
                self.fallback_position_slider.setValue(int(position * 1000))
                self.fallback_position_slider.blockSignals(False)

    def _load_plugins(self) -> None:
        """Load all plugins."""
        plugins_dir = Path(__file__).parent.parent.parent / "plugins"
        context = PluginContext(self)
        self.plugin_manager = PluginManager(plugins_dir, context)
        self.ui_builder = UIBuilder(self)

        # Load plugins for current mode
        current_mode = self.config.ui.mode
        loaded = self.plugin_manager.load_all_plugins(mode=current_mode)
        logging.info(f"Loaded {loaded} plugins for {current_mode} mode")

        # Register plugin UIs and shortcuts
        for plugin in self.plugin_manager.get_all_plugins():
            plugin.register_ui(self.ui_builder)
            if hasattr(plugin, "register_shortcuts"):
                plugin.register_shortcuts(self.shortcut_manager)

        # Add fallback position slider if no plugin provides position seeking
        if not self._position_seeking_provided:
            from PySide6.QtCore import Qt

            from jukebox.ui.components.clickable_slider import ClickableSlider

            self.fallback_position_slider = ClickableSlider(Qt.Orientation.Horizontal)
            self.fallback_position_slider.setRange(0, 1000)
            self.fallback_position_slider.setMaximumHeight(120)
            self.fallback_position_slider.setMinimumHeight(120)
            self.fallback_position_slider.sliderMoved.connect(
                lambda val: self.player.set_position(val / 1000.0)
            )
            # Add to bottom layout
            central = self.centralWidget()
            layout = central.layout() if central else None
            if layout:
                layout.addWidget(self.fallback_position_slider)

        # Subscribe to mode changes to reload tracks (after plugins are loaded)
        # mode_manager may be set by mode_switcher plugin
        if not hasattr(self, "mode_manager") or self.mode_manager is None:
            self.mode_manager = ModeManager(AppMode(self.config.ui.mode))
        self.mode_manager.mode_changed.connect(self._on_mode_changed)

    def _on_position_seeking_provided(self) -> None:
        """Handle POSITION_SEEKING_PROVIDED event.

        Called when a plugin declares it provides position seeking capability.
        This prevents MainWindow from adding a fallback position slider.
        """
        self._position_seeking_provided = True

    def _on_select_next_track(self) -> None:
        """Handle SELECT_NEXT_TRACK event."""
        self.track_list.select_next_track()

    def _on_select_previous_track(self) -> None:
        """Handle SELECT_PREVIOUS_TRACK event."""
        self.track_list.select_previous_track()

    def _on_select_random_track(self) -> None:
        """Handle SELECT_RANDOM_TRACK event."""
        import random

        model = self.track_list.model()
        if model.rowCount() > 0:
            random_row = random.randint(0, model.rowCount() - 1)
            self.track_list.selectRow(random_row)
            filepath = model.data(model.index(random_row, 0), Qt.ItemDataRole.UserRole)
            if filepath:
                self._load_and_play(filepath)

    def _on_load_track_list(self, filepaths: list[Path]) -> None:
        """Handle LOAD_TRACK_LIST event - load specific tracks into the list.

        Args:
            filepaths: List of track filepaths to load
        """
        self.track_list.clear_tracks()

        # Load track data from database for each filepath
        for filepath in filepaths:
            track = self.database.conn.execute(
                "SELECT title, artist, genre, duration_seconds FROM tracks WHERE filepath = ?",
                (str(filepath),),
            ).fetchone()

            if track:
                self.track_list.add_track(
                    filepath,
                    track["title"],
                    track["artist"],
                    track["genre"] if "genre" in track else None,
                    track["duration_seconds"] if "duration_seconds" in track else None,
                )

    def _get_current_mode(self) -> str:
        """Get current application mode.

        Returns:
            Mode string ("jukebox" or "curating")
        """
        if hasattr(self, "mode_manager") and self.mode_manager is not None:
            return self.mode_manager.get_mode().value
        return self.config.ui.mode

    def _on_mode_changed(self, mode: AppMode) -> None:
        """Handle mode change - reload track list for new mode.

        Note: Most mode change logic is handled by mode_switcher plugin.
        This handler provides minimal functionality when the plugin is not loaded.

        Args:
            mode: New application mode
        """
        # Only act if mode_switcher plugin is not loaded
        if "mode_switcher" not in self.plugin_manager.plugins:
            logging.info(f"[MainWindow] Mode changed to {mode.value} (no mode_switcher plugin)")
            self._load_tracks_from_db()
