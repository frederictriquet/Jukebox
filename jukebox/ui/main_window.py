"""Main application window."""

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jukebox.core.audio_player import AudioPlayer
from jukebox.core.config import JukeboxConfig
from jukebox.ui.components.player_controls import PlayerControls
from jukebox.ui.components.track_list import TrackList


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, config: JukeboxConfig):
        """Initialize main window.

        Args:
            config: Application configuration
        """
        super().__init__()
        self.config = config
        self.player = AudioPlayer()
        self._init_ui()
        self._connect_signals()

    def _init_ui(self) -> None:
        """Initialize UI."""
        self.setWindowTitle(self.config.ui.window_title)
        self.resize(self.config.ui.window_width, self.config.ui.window_height)

        # Central widget
        central = QWidget()
        layout = QVBoxLayout()

        # Add files button
        self.add_files_btn = QPushButton("Add Files...")
        self.add_files_btn.clicked.connect(self._add_files)
        layout.addWidget(self.add_files_btn)

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
        self.controls.play_clicked.connect(self.player.play)
        self.controls.pause_clicked.connect(self.player.pause)
        self.controls.stop_clicked.connect(self.player.stop)
        self.controls.volume_changed.connect(self.player.set_volume)
        self.controls.position_changed.connect(self.player.set_position)

        # Player feedback
        self.player.volume_changed.connect(self.controls.set_volume)
        self.player.position_changed.connect(self.controls.set_position)

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
            paths = [Path(f) for f in files]
            self.track_list.add_tracks(paths)

    def _load_and_play(self, filepath: Path) -> None:
        """Load and play selected track.

        Args:
            filepath: Path to audio file
        """
        if self.player.load(filepath):
            self.player.play()
            self.setWindowTitle(f"{self.config.ui.window_title} - {filepath.name}")
