"""Playlists plugin."""

from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class PlaylistsPlugin:
    """Playlist management plugin."""

    name = "playlists"
    version = "1.0.0"
    description = "Manage playlists"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

    def register_ui(self, ui_builder: Any) -> None:
        """Register UI."""
        # Add toolbar button
        from PySide6.QtWidgets import QPushButton

        btn = QPushButton("Playlists...")
        btn.clicked.connect(self._show_playlists)
        ui_builder.add_toolbar_widget(btn)

    def _show_playlists(self) -> None:
        """Show playlist dialog."""
        dialog = PlaylistDialog(self.context)
        dialog.exec()

    def shutdown(self) -> None:
        """Cleanup."""
        pass


class PlaylistDialog(QDialog):
    """Playlist management dialog."""

    def __init__(self, context: Any):
        """Initialize dialog."""
        super().__init__()
        self.context = context
        self._init_ui()
        self._load_playlists()

    def _init_ui(self) -> None:
        """Initialize UI."""
        self.setWindowTitle("Playlists")
        self.resize(400, 300)

        layout = QVBoxLayout()

        self.playlist_list = QListWidget()
        layout.addWidget(self.playlist_list)

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
        playlists = self.context.database.conn.execute(
            "SELECT * FROM playlists ORDER BY name"
        ).fetchall()

        for playlist in playlists:
            self.playlist_list.addItem(f"{playlist['name']} ({playlist['id']})")

    def _create_playlist(self) -> None:
        """Create new playlist."""
        name, ok = QInputDialog.getText(self, "New Playlist", "Playlist name:")

        if ok and name:
            try:
                self.context.database.conn.execute(
                    "INSERT INTO playlists (name) VALUES (?)", (name,)
                )
                self.context.database.conn.commit()
                self._load_playlists()
                self._update_context_menu()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed: {e}")

    def _view_playlist(self) -> None:
        """View playlist tracks."""
        current = self.playlist_list.currentItem()
        if not current:
            return

        playlist_id = int(current.text().split("(")[-1].rstrip(")"))
        tracks = self.context.database.conn.execute(
            """
            SELECT t.*
            FROM tracks t
            JOIN playlist_tracks pt ON t.id = pt.track_id
            WHERE pt.playlist_id = ?
            ORDER BY pt.position
        """,
            (playlist_id,),
        ).fetchall()

        if not tracks:
            QMessageBox.information(self, "Empty", "No tracks in this playlist.")
            return

        track_list = "\n".join(
            [
                f"{t['artist']} - {t['title']}" if t["artist"] and t["title"] else t["filename"]
                for t in tracks
            ]
        )

        QMessageBox.information(self, f"Tracks ({len(tracks)})", track_list)

    def _load_playlist(self) -> None:
        """Load playlist into main view."""
        current = self.playlist_list.currentItem()
        if not current:
            return

        playlist_id = int(current.text().split("(")[-1].rstrip(")"))

        # Load tracks into main track list
        tracks = self.context.database.conn.execute(
            """
            SELECT t.*
            FROM tracks t
            JOIN playlist_tracks pt ON t.id = pt.track_id
            WHERE pt.playlist_id = ?
            ORDER BY pt.position
        """,
            (playlist_id,),
        ).fetchall()

        from pathlib import Path

        self.context.app.track_list.clear_tracks()
        for track in tracks:
            self.context.app.track_list.add_track(
                Path(track["filepath"]), track["title"], track["artist"]
            )

        self.close()

    def _delete_playlist(self) -> None:
        """Delete playlist."""
        current = self.playlist_list.currentItem()
        if not current:
            return

        playlist_id = int(current.text().split("(")[-1].rstrip(")"))

        reply = QMessageBox.question(
            self, "Delete", "Sure?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.context.database.conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
            self.context.database.conn.commit()
            self._load_playlists()
            self._update_context_menu()

    def _update_context_menu(self) -> None:
        """Update track list context menu."""
        playlists = self.context.database.conn.execute(
            "SELECT * FROM playlists ORDER BY name"
        ).fetchall()
        self.context.app.track_list.set_playlists(playlists)
