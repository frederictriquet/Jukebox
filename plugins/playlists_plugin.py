"""Playlists plugin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol


class PlaylistsPlugin:
    """Playlist management plugin."""

    name = "playlists"
    version = "1.0.0"
    description = "Manage playlists"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol | None = None

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin."""
        self.context = context

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register UI."""
        # Load existing playlists into context menu
        self._update_context_menu()

    def _show_playlists(self) -> None:
        """Show playlist dialog."""
        dialog = PlaylistDialog(self.context)
        dialog.exec()

    def _update_context_menu(self) -> None:
        """Load playlists into track list context menu."""
        playlists = self.context.database.conn.execute(
            "SELECT * FROM playlists ORDER BY name"
        ).fetchall()
        self.context.app.track_list.set_playlists(playlists)

    def shutdown(self) -> None:
        """Cleanup on application exit. No cleanup needed for this plugin."""
        ...


class PlaylistDialog(QDialog):
    """Playlist management dialog."""

    def __init__(self, context: PluginContextProtocol):
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
        self.playlist_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlist_list.customContextMenuRequested.connect(self._show_context_menu)
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
            """
            SELECT p.*, COUNT(pt.track_id) AS track_count
            FROM playlists p
            LEFT JOIN playlist_tracks pt ON p.id = pt.playlist_id
            GROUP BY p.id
            ORDER BY p.name
            """
        ).fetchall()

        for playlist in playlists:
            count = playlist["track_count"]
            item = QListWidgetItem(f"{playlist['name']} ({count} track{'s' if count != 1 else ''})")
            item.setData(Qt.ItemDataRole.UserRole, playlist["id"])
            item.setData(Qt.ItemDataRole.UserRole + 1, playlist["name"])
            self.playlist_list.addItem(item)

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

        playlist_id = current.data(Qt.ItemDataRole.UserRole)
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

        playlist_id = current.data(Qt.ItemDataRole.UserRole)

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

        from jukebox.core.event_bus import Events

        # Emit event to load playlist tracks into track list
        track_filepaths = [Path(track["filepath"]) for track in tracks]
        self.context.emit(Events.LOAD_TRACK_LIST, filepaths=track_filepaths)

        self.close()

    def _show_context_menu(self, position: object) -> None:
        """Show right-click context menu on playlist list."""
        item = self.playlist_list.itemAt(position)  # type: ignore[arg-type]
        if not item:
            return

        menu = QMenu(self)

        load_action = QAction("Load", self)
        load_action.triggered.connect(self._load_playlist)
        menu.addAction(load_action)

        view_action = QAction("View", self)
        view_action.triggered.connect(self._view_playlist)
        menu.addAction(view_action)

        menu.addSeparator()

        export_action = QAction("Export to Engine DJ", self)
        export_action.triggered.connect(self._export_to_engine_dj)
        menu.addAction(export_action)

        menu.addSeparator()

        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(self._delete_playlist)
        menu.addAction(delete_action)

        menu.exec(self.playlist_list.mapToGlobal(position))  # type: ignore[arg-type]

    def _export_to_engine_dj(self) -> None:
        """Export selected playlist to Engine DJ database."""
        current = self.playlist_list.currentItem()
        if not current:
            return

        playlist_id = current.data(Qt.ItemDataRole.UserRole)
        playlist_name = current.data(Qt.ItemDataRole.UserRole + 1)

        from plugins.engine_dj_export import export_playlist_to_engine_dj

        export_playlist_to_engine_dj(self.context, playlist_id, playlist_name, parent=self)

    def _delete_playlist(self) -> None:
        """Delete playlist."""
        current = self.playlist_list.currentItem()
        if not current:
            return

        playlist_id = current.data(Qt.ItemDataRole.UserRole)

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
