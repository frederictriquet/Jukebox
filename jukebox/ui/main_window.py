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
from jukebox.core.plugin_manager import PluginContext, PluginManager
from jukebox.core.shortcut_manager import ShortcutManager
from jukebox.ui.components.player_controls import PlayerControls
from jukebox.ui.components.search_bar import SearchBar
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
        self.event_bus.subscribe(Events.TRACK_DELETED, self._on_track_deleted)

        # Timer for updating position
        self.position_timer = QTimer()
        self.position_timer.setInterval(100)
        self.position_timer.timeout.connect(self._update_position)

        # Fallback position slider (if no waveform plugin)
        self.fallback_position_slider: Any = None

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

        # Track list (with stretch to take all available space)
        self.track_list = TrackList(database=self.database, event_bus=self.event_bus, config=self.config)
        layout.addWidget(self.track_list, stretch=1)

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
            for file in files:
                filepath = Path(file)
                metadata = MetadataExtractor.extract(filepath)
                self.database.add_track(metadata)

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

        scanner = FileScanner(self.database, self.config.audio.supported_formats, update_progress)
        added = scanner.scan_directory(Path(directory), recursive=True)

        progress.close()
        QMessageBox.information(self, "Scan Complete", f"Added {added} tracks")
        self._load_tracks_from_db()

        # Emit event to notify plugins (start batch processing)
        if added > 0:
            self.event_bus.emit(Events.TRACKS_ADDED)

    def _perform_search(self, query: str) -> None:
        """Perform FTS5 search."""
        # Save current playing track
        current_track = self.player.current_file if self.player.current_file else None

        self.track_list.clear_tracks()
        tracks = self.database.get_all_tracks() if not query else self.database.search_tracks(query)
        for track in tracks:
            self.track_list.add_track(
                Path(track["filepath"]),
                track["title"],
                track["artist"],
                track["genre"] if "genre" in track.keys() else None,
                track["duration_seconds"] if "duration_seconds" in track.keys() else None,
            )

        # Restore selection of current playing track
        if current_track:
            model = self.track_list.model()
            row = model.find_row_by_filepath(current_track)
            if row >= 0:
                self.track_list.selectRow(row)

    def _load_tracks_from_db(self) -> None:
        """Load all tracks from database."""
        self.track_list.clear_tracks()
        tracks = self.database.get_all_tracks()
        for track in tracks:
            self.track_list.add_track(
                Path(track["filepath"]),
                track["title"],
                track["artist"],
                track["genre"] if "genre" in track.keys() else None,
                track["duration_seconds"] if "duration_seconds" in track.keys() else None,
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
        """Handle track deletion - stop current playback and play next track.

        Args:
            filepath: Path of deleted track
        """
        # Check if the deleted file was currently playing
        was_deleted_file_playing = (
            self.player.current_file and self.player.current_file == filepath
        )

        logging.info(
            f"[MainWindow] Track deleted: {filepath.name}, was_playing={was_deleted_file_playing}"
        )

        # Stop current playback if the deleted file was playing
        if was_deleted_file_playing:
            self.player.stop()
            self.position_timer.stop()
            logging.debug("[MainWindow] Stopped playback of deleted track")

            # Defer playing next track to ensure TrackListModel has finished removing the row
            # Use QTimer.singleShot to execute after event loop processes the model update
            QTimer.singleShot(50, self._play_next_after_deletion)

    def _play_next_after_deletion(self) -> None:
        """Play next track after deletion (deferred execution)."""
        model = self.track_list.model()

        if model.rowCount() == 0:
            # No tracks left
            self.setWindowTitle(self.config.ui.window_title)
            logging.info("[MainWindow] No more tracks after deletion")
            return

        # Auto-play the next track
        # Use current selection if valid, otherwise play first track
        play_row = 0

        current_index = self.track_list.selectionModel().currentIndex()
        if current_index.isValid() and current_index.row() < model.rowCount():
            play_row = current_index.row()
            logging.debug(f"[MainWindow] Using current selection row {play_row}")
        else:
            logging.debug("[MainWindow] No valid selection, playing row 0")

        # Select and play
        logging.info(f"[MainWindow] Selecting and playing row {play_row}")
        self.track_list.selectRow(play_row)
        next_filepath = model.data(model.index(play_row, 0), Qt.ItemDataRole.UserRole)
        if next_filepath:
            logging.info(f"[MainWindow] Loading next track: {next_filepath}")
            self._load_and_play(next_filepath)
        else:
            logging.error(f"[MainWindow] Could not get filepath for row {play_row}")

    def _on_files_dropped(self, paths: list[Path]) -> None:
        """Handle files/directories dropped on track list."""
        from jukebox.utils.metadata import MetadataExtractor
        from jukebox.utils.scanner import FileScanner

        # Scan all paths (files and directories)
        for path in paths:
            if path.is_file():
                # Single file - check if it's a supported format
                if path.suffix.lower().lstrip(".") in self.config.audio.supported_formats:
                    # Extract metadata and add to database
                    metadata = MetadataExtractor.extract(path)
                    self.database.add_track(metadata)
            elif path.is_dir():
                # Directory - scan recursively
                scanner = FileScanner(self.database, self.config.audio.supported_formats)
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
                    self.event_bus.emit(Events.TRACK_LOADED, track_id=track["id"])

            self.player.play()
            self.setWindowTitle(f"{self.config.ui.window_title} - {filepath.name}")
            self.position_timer.start()

    def _on_play(self) -> None:
        """Handle play button click."""
        # If no track loaded, load selected track
        if self.player.current_file is None:
            selected = self.track_list.get_selected_track()
            if selected and self.player.load(selected):
                self.setWindowTitle(f"{self.config.ui.window_title} - {selected.name}")

        self.player.play()
        self.position_timer.start()

    def _on_pause(self) -> None:
        """Handle pause button click."""
        # Pause toggles play/pause in VLC
        was_playing = self.player.is_playing()
        self.player.pause()

        # If we were playing, we're now paused -> stop timer
        # If we were paused, we're now playing -> start timer
        if was_playing:
            self.position_timer.stop()
        else:
            self.position_timer.start()

    def _on_stop(self) -> None:
        """Handle stop button click."""
        self.player.stop()
        self.position_timer.stop()
        # Emit for plugins (waveform cursor)
        self.event_bus.emit("position_update", position=0.0)

    def _update_position(self) -> None:
        """Update position based on player position."""
        if self.player.is_playing():
            position = self.player.get_position()
            # Emit for plugins (waveform cursor)
            self.event_bus.emit("position_update", position=position)
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

        # Add fallback position slider if waveform plugin not loaded
        waveform_loaded = "waveform_visualizer" in self.plugin_manager.plugins
        if not waveform_loaded:
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
