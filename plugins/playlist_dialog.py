"""Playlist management dialog."""

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from jukebox.core.playlist_manager import PlaylistManager


class PlaylistDialog(QDialog):
    """Dialog for managing playlists."""

    playlist_loaded = Signal(int)  # playlist_id
    playlists_changed = Signal()  # playlist created/deleted

    def __init__(self, playlist_manager: PlaylistManager, parent: Any = None):
        """Initialize dialog."""
        super().__init__(parent)
        self.playlist_manager = playlist_manager
        self._init_ui()
        self._load_playlists()

    def _init_ui(self) -> None:
        """Initialize UI."""
        self.setWindowTitle("Playlists")
        self.resize(400, 300)

        layout = QVBoxLayout()

        # Playlist list
        self.playlist_list = QListWidget()
        layout.addWidget(self.playlist_list)

        # Buttons
        btn_layout = QHBoxLayout()

        new_btn = QPushButton("New")
        load_btn = QPushButton("Load")
        view_btn = QPushButton("View")
        delete_btn = QPushButton("Delete")
        close_btn = QPushButton("Close")

        new_btn.clicked.connect(self._create_playlist)
        load_btn.clicked.connect(self._load_playlist)
        view_btn.clicked.connect(self._view_playlist)
        delete_btn.clicked.connect(self._delete_playlist)
        close_btn.clicked.connect(self.close)

        btn_layout.addWidget(new_btn)
        btn_layout.addWidget(load_btn)
        btn_layout.addWidget(view_btn)
        btn_layout.addWidget(delete_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _load_playlists(self) -> None:
        """Load playlists."""
        self.playlist_list.clear()
        playlists = self.playlist_manager.get_all_playlists()

        for playlist in playlists:
            self.playlist_list.addItem(f"{playlist['name']} ({playlist['id']})")

    def _create_playlist(self) -> None:
        """Create new playlist."""
        name, ok = QInputDialog.getText(self, "New Playlist", "Playlist name:")

        if ok and name:
            try:
                self.playlist_manager.create_playlist(name)
                self._load_playlists()
                self.playlists_changed.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create playlist: {e}")

    def _view_playlist(self) -> None:
        """View playlist tracks."""
        current = self.playlist_list.currentItem()
        if not current:
            return

        text = current.text()
        playlist_id = int(text.split("(")[-1].rstrip(")"))

        tracks = self.playlist_manager.get_playlist_tracks(playlist_id)

        if not tracks:
            QMessageBox.information(self, "Playlist Empty", "No tracks in this playlist.")
            return

        track_list = "\n".join(
            [
                f"{t['artist']} - {t['title']}" if t["artist"] and t["title"] else t["filename"]
                for t in tracks
            ]
        )

        QMessageBox.information(self, f"Playlist Tracks ({len(tracks)})", track_list)

    def _load_playlist(self) -> None:
        """Load playlist tracks into main view."""
        current = self.playlist_list.currentItem()
        if not current:
            return

        text = current.text()
        playlist_id = int(text.split("(")[-1].rstrip(")"))

        self.playlist_loaded.emit(playlist_id)
        self.close()

    def _delete_playlist(self) -> None:
        """Delete selected playlist."""
        current = self.playlist_list.currentItem()
        if not current:
            return

        # Extract ID from text "Name (ID)"
        text = current.text()
        playlist_id = int(text.split("(")[-1].rstrip(")"))

        reply = QMessageBox.question(
            self,
            "Delete Playlist",
            "Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.playlist_manager.delete_playlist(playlist_id)
            self._load_playlists()
            self.playlists_changed.emit()
