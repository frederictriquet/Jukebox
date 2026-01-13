"""Track list widget with table view."""

from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QMenu, QTableView

from jukebox.ui.components.track_cell_renderer import CellRenderer

# Column configuration
COLUMNS = ["waveform", "filename", "genre", "rating", "duration"]


class TrackListModel(QAbstractTableModel):
    """Model for track data."""

    # Signal emitted after a row is deleted (so others can safely query the model)
    row_deleted = Signal(int)  # deleted_row index (before deletion)

    def __init__(self, database: Any = None, event_bus: Any = None, config: Any = None) -> None:
        """Initialize model.

        Args:
            database: Database instance (for refreshing track data)
            event_bus: Event bus instance (for subscribing to updates)
            config: Config instance (for genre names)
        """
        super().__init__()
        self.tracks: list[dict[str, Any]] = []  # Full track data from database
        self.filepath_to_row: dict[Path, int] = {}  # Cache for fast lookup

        # Build genre names mapping from config
        genre_names = {}
        if config and hasattr(config, "genre_editor"):
            for code_config in config.genre_editor.codes:
                genre_names[code_config.code] = code_config.name

        self.cell_renderer = CellRenderer(COLUMNS, genre_names)
        self.database = database
        self.event_bus = event_bus

        # Subscribe to metadata updates (when genre/rating changes)
        if event_bus:
            # Listen for track metadata changes (emitted by genre_editor, metadata_editor)
            event_bus.subscribe("track_metadata_updated", self._on_track_metadata_updated)
            # Listen for waveform completion (emitted by waveform_visualizer)
            event_bus.subscribe("audio_analysis_complete", self._on_waveform_complete)
            # Listen for track deletion (emitted by file_manager)
            from jukebox.core.event_bus import Events

            event_bus.subscribe(Events.TRACK_DELETED, self._on_track_deleted)

    def _on_track_metadata_updated(self, filepath: Path) -> None:
        """Handle track metadata update event.

        Args:
            filepath: Path of the track that was updated
        """
        # Find the row
        row = self.find_row_by_filepath(filepath)
        if row < 0 or not self.database:
            return

        # Refresh track data from database
        track_db = self.database.conn.execute(
            "SELECT genre, duration_seconds FROM tracks WHERE filepath = ?",
            (str(filepath),),
        ).fetchone()

        if track_db and row < len(self.tracks):
            # Update the track data
            self.tracks[row]["genre"] = track_db["genre"] or ""
            self.tracks[row]["rating"] = track_db["genre"] or ""
            self.tracks[row]["duration_seconds"] = track_db["duration_seconds"]
            self.tracks[row]["duration"] = track_db["duration_seconds"]

            # Emit dataChanged to update the view
            left_index = self.index(row, 0)
            right_index = self.index(row, len(COLUMNS) - 1)
            self.dataChanged.emit(left_index, right_index, [])

    def _on_waveform_complete(self, track_id: int) -> None:
        """Handle waveform completion event.

        Args:
            track_id: Database ID of the track with new waveform
        """
        if not self.database:
            return

        # Get filepath from track_id
        track_db = self.database.conn.execute(
            "SELECT filepath FROM tracks WHERE id = ?", (track_id,)
        ).fetchone()

        if not track_db:
            return

        filepath = Path(track_db["filepath"])
        row = self.find_row_by_filepath(filepath)

        if row < 0 or row >= len(self.tracks):
            return

        # Load the new waveform from cache
        waveform_cache = self.database.conn.execute(
            "SELECT waveform_data FROM waveform_cache WHERE track_id = ?", (track_id,)
        ).fetchone()

        if waveform_cache:
            import logging
            import pickle

            try:
                waveform_preview = pickle.loads(waveform_cache["waveform_data"])
                # Update track data
                self.tracks[row]["waveform"] = waveform_preview
                self.tracks[row]["waveform_preview"] = waveform_preview

                # Clear cache for this track so it re-renders
                from jukebox.ui.components.track_cell_renderer import WaveformStyler
                cache_key = hash(str(filepath))
                WaveformStyler._cache.pop(cache_key, None)

                # Emit dataChanged to refresh the waveform column
                waveform_index = self.index(row, 0)  # Waveform is column 0
                self.dataChanged.emit(waveform_index, waveform_index, [])
            except Exception as e:
                logging.error(f"[TrackListModel] Failed to update waveform for {filepath}: {e}", exc_info=True)

    def _on_track_deleted(self, filepath: Path, deleted_row: int | None = None) -> None:
        """Handle track deletion event.

        Args:
            filepath: Path of the track that was deleted
            deleted_row: Row that was deleted (optional, for logging)
        """
        import logging

        # Find the row
        row = self.find_row_by_filepath(filepath)
        if row < 0:
            logging.warning(f"[TrackListModel] Could not find row for deleted track: {filepath}")
            return

        logging.info(f"[TrackListModel] Deleting row {row} (total rows: {len(self.tracks)})")

        # Save deleted row before removing
        deleted_row_index = row

        # Remove from model
        self.beginRemoveRows(QModelIndex(), row, row)
        self.tracks.pop(row)
        self.endRemoveRows()

        logging.info(f"[TrackListModel] Row deleted, remaining rows: {len(self.tracks)}")

        # Rebuild filepath_to_row cache (row indices changed)
        self.filepath_to_row.clear()
        for idx, track in enumerate(self.tracks):
            self.filepath_to_row[track["filepath"]] = idx

        # Emit signal so MainWindow can safely query the updated model
        self.row_deleted.emit(deleted_row_index)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Get number of rows."""
        return len(self.tracks)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Get number of columns."""
        return len(COLUMNS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        """Get header data."""
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return COLUMNS[section].capitalize()
            elif orientation == Qt.Orientation.Vertical:
                # Row numbers in vertical header (like PyQT project)
                return f"{section + 1}/{len(self.tracks)}"
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Get data for index and role."""
        if not index.isValid() or index.row() >= len(self.tracks):
            return None

        track = self.tracks[index.row()]

        # UserRole returns filepath for all columns
        if role == Qt.ItemDataRole.UserRole:
            return track.get("filepath")

        # Delegate to CellRenderer for all display/styling roles
        return self.cell_renderer.get_style(track, index.column(), role)

    def add_track(
        self,
        filepath: Path,
        title: str | None = None,
        artist: str | None = None,
        genre: str | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        """Add a track to the model."""
        # Load waveform preview from cache if available
        waveform_preview = None
        if self.database:
            # Get track_id from filepath
            track_db = self.database.conn.execute(
                "SELECT id FROM tracks WHERE filepath = ?", (str(filepath),)
            ).fetchone()

            if track_db:
                # Load waveform from cache
                waveform_cache = self.database.conn.execute(
                    "SELECT waveform_data FROM waveform_cache WHERE track_id = ?",
                    (track_db["id"],),
                ).fetchone()

                if waveform_cache:
                    import logging
                    import pickle

                    try:
                        waveform_preview = pickle.loads(waveform_cache["waveform_data"])
                    except Exception as e:
                        logging.error(f"[TrackListModel] Failed to load waveform for {filepath}: {e}", exc_info=True)

        row = len(self.tracks)
        self.beginInsertRows(QModelIndex(), row, row)
        self.tracks.append({
            "filepath": filepath,
            "filename": filepath.name,  # For FilenameStyler
            "title": title,
            "artist": artist,
            "genre": genre or "",
            "rating": genre or "",  # RatingStyler extracts from genre
            "duration": duration_seconds,
            "duration_seconds": duration_seconds,
            "waveform": waveform_preview,  # For WaveformStyler
            "waveform_preview": waveform_preview,
        })
        self.filepath_to_row[filepath] = row
        self.endInsertRows()

    def clear(self) -> None:
        """Clear all tracks."""
        self.beginResetModel()
        self.tracks.clear()
        self.filepath_to_row.clear()
        self.endResetModel()

    def find_row_by_filepath(self, filepath: Path) -> int:
        """Find row index by filepath (O(1) lookup).

        Args:
            filepath: Path to find

        Returns:
            Row index or -1 if not found
        """
        return self.filepath_to_row.get(filepath, -1)


class TrackList(QTableView):
    """Widget for displaying audio tracks as a table."""

    track_selected = Signal(Path)
    add_to_playlist_requested = Signal(Path, int)  # filepath, playlist_id
    files_dropped = Signal(list)  # List of Path objects (files and directories)

    def __init__(self, parent: Any = None, database: Any = None, event_bus: Any = None, config: Any = None):
        """Initialize track list.

        Args:
            parent: Parent widget
            database: Database instance (for refreshing data)
            event_bus: Event bus instance (for subscribing to updates)
            config: Config instance (for genre names)
        """
        super().__init__(parent)

        # Set model
        model = TrackListModel(database, event_bus, config)
        self.setModel(model)

        # Table configuration
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.setShowGrid(False)  # No grid lines

        # Vertical header shows row numbers (n/total)
        self.verticalHeader().setVisible(True)
        self.verticalHeader().setDefaultSectionSize(20)  # Compact rows

        # Horizontal header configuration
        h_header = self.horizontalHeader()
        h_header.setStretchLastSection(False)  # Manual column sizing

        # Column widths
        self.setColumnWidth(0, 210)  # Waveform mini preview (200px waveform + padding)
        self.setColumnWidth(1, 350)  # Filename
        self.setColumnWidth(2, 80)   # Genre
        self.setColumnWidth(3, 80)   # Rating
        self.setColumnWidth(4, 80)   # Duration

        # Never take keyboard focus - global shortcuts always active
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Connect signals
        self.clicked.connect(self._on_row_clicked)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Playlists for context menu
        self.playlists: list[Any] = []

    def add_track(
        self,
        filepath: Path,
        title: str | None = None,
        artist: str | None = None,
        genre: str | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        """Add a track to the list.

        Args:
            filepath: Path to audio file
            title: Track title (optional)
            artist: Track artist (optional)
            genre: Track genre (optional)
            duration_seconds: Track duration in seconds (optional)
        """
        model = self.model()
        if isinstance(model, TrackListModel):
            model.add_track(filepath, title, artist, genre, duration_seconds)

    def add_tracks(self, filepaths: list[Path]) -> None:
        """Add multiple tracks.

        Args:
            filepaths: List of paths to audio files
        """
        for filepath in filepaths:
            self.add_track(filepath)

    def clear_tracks(self) -> None:
        """Clear all tracks."""
        model = self.model()
        if isinstance(model, TrackListModel):
            model.clear()

    def get_selected_track(self) -> Path | None:
        """Get currently selected track.

        Returns:
            Path to selected track or None
        """
        index = self.selectionModel().currentIndex()
        if index.isValid():
            return self.model().data(index, Qt.ItemDataRole.UserRole)
        return None

    def set_playlists(self, playlists: list[Any]) -> None:
        """Set available playlists for context menu."""
        self.playlists = playlists

    def _on_row_clicked(self, index: QModelIndex) -> None:
        """Handle row click."""
        if index.isValid():
            filepath = self.model().data(index, Qt.ItemDataRole.UserRole)
            if filepath:
                self.track_selected.emit(filepath)

    def _show_context_menu(self, position: Any) -> None:
        """Show context menu on right-click."""
        index = self.indexAt(position)
        if not index.isValid() or not self.playlists:
            return

        filepath = self.model().data(index, Qt.ItemDataRole.UserRole)
        if not filepath:
            return

        menu = QMenu(self)
        add_menu = menu.addMenu("Add to Playlist")

        for playlist in self.playlists:
            action = QAction(playlist["name"], self)
            action.triggered.connect(
                lambda checked, p=playlist, fp=filepath: self._add_to_playlist(fp, p["id"])
            )
            add_menu.addAction(action)

        menu.exec(self.mapToGlobal(position))

    def _add_to_playlist(self, filepath: Path, playlist_id: int) -> None:
        """Add track to playlist."""
        self.add_to_playlist_requested.emit(filepath, playlist_id)

    def select_next_track(self) -> None:
        """Select and play next track in list."""
        current_index = self.selectionModel().currentIndex()
        current_row = current_index.row() if current_index.isValid() else -1

        model = self.model()
        if isinstance(model, TrackListModel) and current_row < model.rowCount() - 1:
            next_row = current_row + 1
            self.selectRow(next_row)
            # Emit signal
            next_index = model.index(next_row, 0)
            filepath = model.data(next_index, Qt.ItemDataRole.UserRole)
            if filepath:
                self.track_selected.emit(filepath)

    def select_previous_track(self) -> None:
        """Select and play previous track in list."""
        current_index = self.selectionModel().currentIndex()
        current_row = current_index.row() if current_index.isValid() else -1

        if current_row > 0:
            prev_row = current_row - 1
            self.selectRow(prev_row)
            # Emit signal
            model = self.model()
            prev_index = model.index(prev_row, 0)
            filepath = model.data(prev_index, Qt.ItemDataRole.UserRole)
            if filepath:
                self.track_selected.emit(filepath)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        """Handle drag enter event."""
        import logging

        logging.info(f"Drag enter: hasUrls={event.mimeData().hasUrls()}")
        if event.mimeData().hasUrls():
            event.accept()
            logging.info("Drag accepted")
        else:
            event.ignore()
            logging.info("Drag rejected")

    def dragMoveEvent(self, event: Any) -> None:  # noqa: N802
        """Handle drag move event."""
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        """Handle drop event."""
        import logging

        logging.info("Drop event received")
        if not event.mimeData().hasUrls():
            event.ignore()
            logging.warning("No URLs in drop event")
            return

        # Collect all paths (files and directories)
        paths = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            logging.info(f"Dropped path: {path}, exists={path.exists()}")
            if path.exists():
                paths.append(path)

        if paths:
            logging.info(f"Emitting files_dropped with {len(paths)} paths")
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()
            logging.warning("No valid paths in drop event")
