"""Main application window."""

import logging
from pathlib import Path

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
from jukebox.core.event_bus import EventBus
from jukebox.core.plugin_manager import PluginContext, PluginManager
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

        # Timer for updating position slider
        self.position_timer = QTimer()
        self.position_timer.setInterval(100)
        self.position_timer.timeout.connect(self._update_position)

        self._init_ui()
        self._connect_signals()
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

        # Track list
        self.track_list = TrackList()
        layout.addWidget(self.track_list)

        # Player controls
        self.controls = PlayerControls()
        layout.addWidget(self.controls)

        # Set initial volume
        self.controls.set_volume(self.config.audio.default_volume)
        self.player.set_volume(self.config.audio.default_volume)

        central.setLayout(layout)
        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        """Connect signals between components."""
        # Track selection
        self.track_list.track_selected.connect(self._load_and_play)

        # Player controls
        self.controls.play_clicked.connect(self._on_play)
        self.controls.pause_clicked.connect(self._on_pause)
        self.controls.stop_clicked.connect(self._on_stop)
        self.controls.volume_changed.connect(self.player.set_volume)

        # Player feedback
        self.player.volume_changed.connect(self.controls.set_volume)

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

    def _perform_search(self, query: str) -> None:
        """Perform FTS5 search."""
        self.track_list.clear_tracks()
        tracks = self.database.get_all_tracks() if not query else self.database.search_tracks(query)
        for track in tracks:
            self.track_list.add_track(Path(track["filepath"]), track["title"], track["artist"])

    def _load_tracks_from_db(self) -> None:
        """Load all tracks from database."""
        self.track_list.clear_tracks()
        tracks = self.database.get_all_tracks()
        for track in tracks:
            self.track_list.add_track(Path(track["filepath"]), track["title"], track["artist"])

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
                    from jukebox.core.event_bus import Events

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
        self.player.pause()
        self.position_timer.stop()

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

    def _load_plugins(self) -> None:
        """Load all plugins."""
        plugins_dir = Path(__file__).parent.parent.parent / "plugins"
        context = PluginContext(self)
        self.plugin_manager = PluginManager(plugins_dir, context)
        ui_builder = UIBuilder(self)

        loaded = self.plugin_manager.load_all_plugins()
        logging.info(f"Loaded {loaded} plugins")

        for plugin in self.plugin_manager.get_all_plugins():
            plugin.register_ui(ui_builder)
