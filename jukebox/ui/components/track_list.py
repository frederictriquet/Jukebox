"""Track list widget."""

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QMenu


class TrackList(QListWidget):
    """Widget for displaying audio tracks."""

    track_selected = Signal(Path)
    add_to_playlist_requested = Signal(Path, int)  # filepath, playlist_id

    def __init__(self, parent=None):  # type: ignore
        """Initialize track list.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.itemClicked.connect(self._on_item_clicked)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.playlists: list[Any] = []

    def add_track(
        self, filepath: Path, title: str | None = None, artist: str | None = None
    ) -> None:
        """Add a track to the list.

        Args:
            filepath: Path to audio file
            title: Track title (optional)
            artist: Track artist (optional)
        """
        # Format display text
        if title and artist:
            display = f"{artist} - {title}"
        elif title:
            display = title
        else:
            display = filepath.name

        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, filepath)
        item.setToolTip(str(filepath))
        self.addItem(item)

    def add_tracks(self, filepaths: list[Path]) -> None:
        """Add multiple tracks.

        Args:
            filepaths: List of paths to audio files
        """
        for filepath in filepaths:
            self.add_track(filepath)

    def clear_tracks(self) -> None:
        """Clear all tracks."""
        self.clear()

    def get_selected_track(self) -> Path | None:
        """Get currently selected track.

        Returns:
            Path to selected track or None
        """
        current = self.currentItem()
        if current:
            data = current.data(Qt.ItemDataRole.UserRole)
            return Path(data) if data is not None else None
        return None

    def set_playlists(self, playlists: list[Any]) -> None:
        """Set available playlists for context menu."""
        self.playlists = playlists

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle track click."""
        filepath = item.data(Qt.ItemDataRole.UserRole)
        if filepath:
            self.track_selected.emit(filepath)

    def _show_context_menu(self, position: Any) -> None:
        """Show context menu on right-click."""
        item = self.itemAt(position)
        if not item or not self.playlists:
            return

        menu = QMenu(self)
        add_menu = menu.addMenu("Add to Playlist")

        for playlist in self.playlists:
            action = QAction(playlist["name"], self)
            action.triggered.connect(
                lambda checked, p=playlist: self._add_to_playlist(item, p["id"])
            )
            add_menu.addAction(action)

        menu.exec(self.mapToGlobal(position))

    def _add_to_playlist(self, item: QListWidgetItem, playlist_id: int) -> None:
        """Add track to playlist."""
        filepath = item.data(Qt.ItemDataRole.UserRole)
        if filepath:
            self.add_to_playlist_requested.emit(filepath, playlist_id)

    def select_next_track(self) -> None:
        """Select and play next track in list."""
        current_row = self.currentRow()
        if current_row < self.count() - 1:
            next_row = current_row + 1
            self.setCurrentRow(next_row)
            item = self.item(next_row)
            if item:
                self._on_item_clicked(item)

    def select_previous_track(self) -> None:
        """Select and play previous track in list."""
        current_row = self.currentRow()
        if current_row > 0:
            prev_row = current_row - 1
            self.setCurrentRow(prev_row)
            item = self.item(prev_row)
            if item:
                self._on_item_clicked(item)
