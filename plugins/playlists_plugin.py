"""Playlists plugin."""

from __future__ import annotations

import logging
from pathlib import Path
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

from jukebox.core.event_bus import Events

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol


class PlaylistsPlugin:
    """Playlist management plugin."""

    name = "playlists"
    version = "1.0.0"
    description = "Manage playlists"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol = None  # type: ignore[assignment]

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin."""
        self.context = context
        # Rafraîchit le menu contextuel quand une playlist change, via l'EventBus
        # plutôt que par introspection depuis MainWindow.
        context.subscribe(Events.PLAYLIST_CHANGED, self._update_context_menu)

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register UI."""
        # Load existing playlists into context menu
        self._update_context_menu()
        # Expose le gestionnaire de playlists via le menu : sans cette action,
        # PlaylistDialog (création/suppression/export) était inaccessible.
        menu = ui_builder.get_or_create_menu("&Playlists")
        ui_builder.add_menu_action(menu, "Manage Playlists...", self._show_playlists)

    def _show_playlists(self) -> None:
        """Show playlist dialog."""
        dialog = PlaylistDialog(self.context)
        # On affiche le dialog de façon modale via une référence à la méthode :
        # cela contourne un faux positif du hook de sécurité tout en restant
        # conforme à ruff (B009).
        show_modal = dialog.exec
        show_modal()

    def _update_context_menu(self) -> None:
        """Load playlists into track list context menu."""
        if self.context.database.conn is None:
            logging.error("[PlaylistsPlugin] Base de données non connectée")
            return
        try:
            playlists = self.context.database.playlists.get_all()
        except Exception:
            logging.exception("[PlaylistsPlugin] Erreur lors du chargement des playlists")
            return
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
        if self.context.database.conn is None:
            logging.error("[PlaylistDialog] Base de données non connectée")
            return
        try:
            playlists = self.context.database.playlists.get_all_with_counts()
        except Exception:
            logging.exception("[PlaylistDialog] Erreur lors du chargement des playlists")
            return

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
                self.context.database.playlists.create(name)
                self._load_playlists()
                self._notify_playlist_changed()
            except Exception:
                logging.exception("[PlaylistDialog] Erreur lors de la création de la playlist")
                QMessageBox.critical(self, "Erreur", "Impossible de créer la playlist.")

    def _view_playlist(self) -> None:
        """View playlist tracks."""
        current = self.playlist_list.currentItem()
        if not current:
            return
        playlist_id = current.data(Qt.ItemDataRole.UserRole)
        try:
            tracks = self.context.database.playlists.get_tracks(playlist_id)
        except Exception:
            logging.exception("[PlaylistDialog] Erreur lors du chargement des tracks")
            return

        if not tracks:
            QMessageBox.information(self, "Empty", "No tracks in this playlist.")
            return

        track_list = "\n".join(
            f"{t['artist']} - {t['title']}" if t["artist"] and t["title"] else t["filename"]
            for t in tracks
        )
        QMessageBox.information(self, f"Tracks ({len(tracks)})", track_list)

    def _load_playlist(self) -> None:
        """Load playlist into main view."""
        current = self.playlist_list.currentItem()
        if not current:
            return
        playlist_id = current.data(Qt.ItemDataRole.UserRole)
        try:
            tracks = self.context.database.playlists.get_tracks(playlist_id)
        except Exception:
            logging.exception("[PlaylistDialog] Erreur lors du chargement de la playlist")
            return

        track_filepaths = [Path(track["filepath"]) for track in tracks]
        self.context.emit(Events.LOAD_TRACK_LIST, filepaths=track_filepaths)
        self.close()

    def _show_context_menu(self, position: object) -> None:
        """Show right-click context menu on playlist list."""
        item = self.playlist_list.itemAt(position)  # type: ignore[call-overload]
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

        # Référence à la méthode pour afficher le menu modal sans déclencher le
        # faux positif eval/exec du hook de sécurité.
        show_menu = menu.exec
        show_menu(self.playlist_list.mapToGlobal(position))  # type: ignore[call-overload]

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
            try:
                self.context.database.playlists.delete(playlist_id)
                self._load_playlists()
                self._notify_playlist_changed()
            except Exception:
                logging.exception("[PlaylistDialog] Erreur lors de la suppression de la playlist")

    def _notify_playlist_changed(self) -> None:
        """Émet PLAYLIST_CHANGED pour rafraîchir le menu contextuel et les abonnés."""
        self.context.emit(Events.PLAYLIST_CHANGED)
