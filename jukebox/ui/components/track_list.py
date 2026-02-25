"""Track list widget with table view."""

import atexit
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    QThread,
    Signal,
)
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QMenu, QStyledItemDelegate, QStyleOptionViewItem, QTableView

from jukebox.core.duplicate_checker import DuplicateChecker
from jukebox.core.event_bus import Events
from jukebox.core.mode_manager import AppMode
from jukebox.ui.components.track_cell_renderer import CellRenderer

# Column configuration per mode
COLUMNS_JUKEBOX = ["waveform", "artist", "title", "genre", "rating", "duration", "stats"]
COLUMNS_CURATING = ["waveform", "filename", "genre", "rating", "duration", "stats", "duplicate"]
COLUMNS = COLUMNS_CURATING  # default (overridden by mode)

# Column widths (in pixels)
COLUMN_WIDTHS = {
    "waveform": 210,  # Waveform mini preview (200px waveform + padding)
    "filename": 350,
    "artist": 175,
    "title": 175,
    "genre": 80,
    "rating": 80,
    "duration": 80,
    "stats": 30,  # Small icon column
    "duplicate": 30,  # Duplicate status indicator (curating only)
}

# Row height
ROW_HEIGHT = 20


_live_workers: list["BackgroundCheckWorker"] = []
"""Module-level registry of active background workers for cleanup at exit."""


@atexit.register
def _cleanup_workers() -> None:
    """Ensure background workers are stopped at exit to avoid SIGABRT.

    QThread must be fully stopped before Python's finalizers run, otherwise
    Qt emits "QThread: Destroyed while thread is still running" and aborts.
    As a last resort, os._exit(0) is used to skip further teardown cleanly.
    """
    import os

    for worker in _live_workers:
        if worker.isRunning():
            worker.requestInterruption()
            worker.quit()
            if not worker.wait(2000):
                logging.warning("[BackgroundCheckWorker] Worker still alive at exit, forcing exit")
                # Skip remaining Python teardown to avoid SIGABRT from Qt
                os._exit(0)


class BackgroundCheckWorker(QThread):
    """Worker thread for duplicate checking.

    Runs the duplicate checker off the main thread so the UI stays responsive.
    Supports cancellation via requestInterruption().
    """

    results = Signal(list)  # [(filepath_str, status, match_info), ...]

    def __init__(
        self,
        duplicate_checker: DuplicateChecker,
        track_dicts: list[dict[str, Any]],
    ) -> None:
        super().__init__()
        self._duplicate_checker = duplicate_checker
        self._track_dicts = track_dicts
        _live_workers.append(self)

    def run(self) -> None:
        try:
            changes: list[tuple[str, str, str | None]] = []
            for track in self._track_dicts:
                if self.isInterruptionRequested():
                    return
                result = self._duplicate_checker.check(track)
                new_status = result.status.value
                new_match = result.match_info
                if (
                    track.get("duplicate_status") != new_status
                    or track.get("duplicate_match") != new_match
                ):
                    filepath_str = str(track.get("filepath", ""))
                    changes.append((filepath_str, new_status, new_match))

            if not self.isInterruptionRequested() and changes:
                self.results.emit(changes)
        finally:
            if self in _live_workers:
                _live_workers.remove(self)


class TrackListModel(QAbstractTableModel):
    """Model for track data."""

    # Signal emitted after a row is deleted (so others can safely query the model)
    row_deleted = Signal(int)  # deleted_row index (before deletion)

    def __init__(
        self,
        database: Any = None,
        event_bus: Any = None,
        config: Any = None,
        mode: str = "jukebox",
    ) -> None:
        """Initialize model.

        Args:
            database: Database instance (for refreshing track data)
            event_bus: Event bus instance (for subscribing to updates)
            config: Config instance (for genre names)
            mode: Application mode ("jukebox" or "curating")
        """
        super().__init__()
        self.tracks: list[dict[str, Any]] = []  # Full track data from database
        self.filepath_to_row: dict[Path, int] = {}  # Cache for fast lookup
        self._mode = mode

        # Build genre names mapping from config
        genre_names = {}
        if config and hasattr(config, "genre_editor"):
            for code_config in config.genre_editor.codes:
                genre_names[code_config.code] = code_config.name

        columns = COLUMNS_JUKEBOX if mode == AppMode.JUKEBOX.value else COLUMNS_CURATING
        self.cell_renderer = CellRenderer(columns, genre_names, mode)
        self.database = database
        self.event_bus = event_bus
        self._db_path = database.db_path if database else None

        # Duplicate checker — active only in curating mode
        # Index is lazy (built on first check) and invalidated on mode switch.
        # Duplicate check runs in a background thread (thread-safe: own DB connection).
        self._duplicate_checker: DuplicateChecker | None = None
        self._bg_worker: BackgroundCheckWorker | None = None
        self._bg_check_pending = False
        if mode == AppMode.CURATING.value and self._db_path:
            self._duplicate_checker = DuplicateChecker(self._db_path)

        # Subscribe to metadata updates (when genre/rating changes)
        if event_bus:
            # Listen for track metadata changes (emitted by genre_editor, metadata_editor)
            event_bus.subscribe(Events.TRACK_METADATA_UPDATED, self._on_track_metadata_updated)
            # Listen for waveform completion (emitted by waveform_visualizer)
            event_bus.subscribe(Events.WAVEFORM_COMPLETE, self._on_waveform_complete)
            # Listen for full audio analysis completion (emitted by audio_analyzer batch)
            event_bus.subscribe(Events.AUDIO_ANALYSIS_COMPLETE, self._on_stats_complete)
            # Listen for track deletion (emitted by file_manager)
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
            # rating is derived from genre (format: "C-D-*3"), RatingStyler reads from genre
            self.tracks[row]["rating"] = (
                track_db["genre"] or ""
            )  # intentional: rating parsed from genre
            self.tracks[row]["duration_seconds"] = track_db["duration_seconds"]

            # Emit dataChanged to update the view
            left_index = self.index(row, 0)
            right_index = self.index(row, self.columnCount() - 1)
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
            from jukebox.utils.waveform_serializer import deserialize_waveform

            try:
                waveform = deserialize_waveform(waveform_cache["waveform_data"])
                # Update track data
                self.tracks[row]["waveform_data"] = waveform

                # Clear cache for this track so it re-renders
                from jukebox.ui.components.track_cell_renderer import WaveformStyler

                cache_key = hash(str(filepath))
                WaveformStyler._cache.pop(cache_key, None)

                # Emit dataChanged to refresh the waveform column only
                waveform_index = self.index(row, 0)  # Waveform is column 0
                self.dataChanged.emit(waveform_index, waveform_index, [])
            except (ValueError, Exception) as e:
                logging.error(
                    f"[TrackListModel] Failed to update waveform for {filepath}: {e}", exc_info=True
                )

    def _on_stats_complete(self, track_id: int) -> None:
        """Handle full audio analysis completion event.

        Args:
            track_id: Database ID of the track with new stats
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

        # Check if audio analysis exists (with key stats)
        analysis = self.database.conn.execute(
            "SELECT tempo FROM audio_analysis WHERE track_id = ? AND tempo IS NOT NULL",
            (track_id,),
        ).fetchone()
        self.tracks[row]["has_stats"] = analysis is not None

        # Emit dataChanged to refresh the stats column only
        columns = self.cell_renderer.columns
        if "stats" in columns:
            stats_col = columns.index("stats")
            stats_index = self.index(row, stats_col)
            self.dataChanged.emit(stats_index, stats_index, [])

    def _on_track_deleted(self, filepath: Path, deleted_row: int | None = None) -> None:
        """Handle track deletion event.

        Args:
            filepath: Path of the track that was deleted
            deleted_row: Row that was deleted (optional, for logging)
        """
        logging.info(f"[TrackListModel] Received TRACK_DELETED for: {filepath}")

        # Find the row
        row = self.find_row_by_filepath(filepath)
        if row < 0:
            # Try with Path conversion in case of type mismatch
            if not isinstance(filepath, Path):
                filepath = Path(filepath)
                row = self.find_row_by_filepath(filepath)

            if row < 0:
                logging.warning(
                    f"[TrackListModel] Could not find row for deleted track: {filepath}"
                )
                logging.debug(
                    f"[TrackListModel] Known paths: {list(self.filepath_to_row.keys())[:5]}..."
                )
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

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:
        """Get number of rows."""
        return len(self.tracks)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:
        """Get number of columns."""
        return len(self.cell_renderer.columns)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        """Get header data."""
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                columns = self.cell_renderer.columns
                if section < len(columns):
                    return columns[section].capitalize()
                return ""
            elif orientation == Qt.Orientation.Vertical:
                # Row numbers in vertical header (like PyQT project)
                return f"{section + 1}/{len(self.tracks)}"
        return None

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
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
        # Load waveform and stats info from cache if available
        waveform = None
        has_stats = False
        if self.database:
            # Get track_id from filepath
            track_db = self.database.conn.execute(
                "SELECT id FROM tracks WHERE filepath = ?", (str(filepath),)
            ).fetchone()

            if track_db:
                track_id = track_db["id"]

                # Load waveform from cache
                waveform_cache = self.database.conn.execute(
                    "SELECT waveform_data FROM waveform_cache WHERE track_id = ?",
                    (track_id,),
                ).fetchone()

                if waveform_cache:
                    from jukebox.utils.waveform_serializer import deserialize_waveform

                    try:
                        waveform = deserialize_waveform(waveform_cache["waveform_data"])
                    except (ValueError, Exception) as e:
                        logging.error(
                            f"[TrackListModel] Failed to load waveform for {filepath}: {e}",
                            exc_info=True,
                        )

                # Check if audio analysis exists (with key stats)
                analysis = self.database.conn.execute(
                    "SELECT tempo FROM audio_analysis WHERE track_id = ? AND tempo IS NOT NULL",
                    (track_id,),
                ).fetchone()
                has_stats = analysis is not None

        track_dict: dict[str, Any] = {
            "filepath": filepath,
            "filename": filepath.name,  # For FilenameStyler
            "title": title,
            "artist": artist,
            "genre": genre or "",
            "rating": genre or "",  # RatingStyler extracts from genre
            "duration_seconds": duration_seconds,
            "waveform_data": waveform,
            "has_stats": has_stats,  # For StatsStyler
            "duplicate_status": "pending",  # Updated by background worker
            "duplicate_match": None,
            "file_missing": False,  # Updated asynchronously after UI display
        }

        row = len(self.tracks)
        self.beginInsertRows(QModelIndex(), row, row)
        self.tracks.append(track_dict)
        self.filepath_to_row[filepath] = row
        self.endInsertRows()

        # Schedule background checks (coalesced — runs once after all add_track calls)
        self._schedule_background_checks()

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

    def set_mode(self, mode: str) -> None:
        """Update the display mode, switching columns and refreshing the view.

        Args:
            mode: Application mode ("jukebox" or "curating")
        """
        if mode != self._mode:
            self._mode = mode
            new_columns = COLUMNS_JUKEBOX if mode == AppMode.JUKEBOX.value else COLUMNS_CURATING
            self.beginResetModel()
            self.cell_renderer.columns = new_columns
            self.cell_renderer.set_mode(mode)
            self.endResetModel()

            # Activate or invalidate duplicate checker when switching to curating
            # Index rebuilds lazily on first check (in background thread)
            if mode == AppMode.CURATING.value and self._db_path:
                if self._duplicate_checker is None:
                    self._duplicate_checker = DuplicateChecker(self._db_path)
                else:
                    self._duplicate_checker.invalidate_index()

    def _schedule_background_checks(self) -> None:
        """Schedule file-existence and duplicate checks.

        File check runs inline (fast for local files).
        Duplicate check runs in a background thread (slow: DB + fuzzy matching).
        Coalesced via _bg_check_pending flag + QTimer.singleShot(0).
        """
        if not self._bg_check_pending:
            self._bg_check_pending = True
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, self._run_background_checks)

    def _run_background_checks(self) -> None:
        """Run file check inline, then launch background worker for duplicates."""
        self._bg_check_pending = False
        if not self.tracks:
            return

        # Phase 1: file existence check (inline — fast for local files)
        changed = False
        for track in self.tracks:
            missing = not Path(track["filepath"]).exists()
            if track.get("file_missing") != missing:
                track["file_missing"] = missing
                changed = True
        if changed:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self.tracks) - 1, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right)

        # Phase 2: duplicate check in background thread (slow)
        if not self._duplicate_checker or self._mode != AppMode.CURATING.value:
            return

        # Stop previous worker if still running
        if self._bg_worker is not None and self._bg_worker.isRunning():
            self._bg_worker.requestInterruption()
            self._bg_worker.quit()
            self._bg_worker.wait(5000)
        self._bg_worker = None

        # Deep-copy track data for thread-safe duplicate check
        track_dicts = [dict(t) for t in self.tracks]

        worker = BackgroundCheckWorker(self._duplicate_checker, track_dicts)
        worker.results.connect(self._on_duplicate_check_results)
        self._bg_worker = worker
        worker.start()
        logging.debug(
            f"[TrackListModel] Background duplicate check started: {len(self.tracks)} tracks"
        )

    def _on_duplicate_check_results(self, results: list[tuple[str, str, str | None]]) -> None:
        """Apply duplicate-check results from the background worker.

        Results are keyed by filepath (not index) so they remain correct even if
        the track list was modified while the worker ran.
        """
        # Build a lookup: filepath_str -> (status, match_info)
        result_map = {fp: (status, match) for fp, status, match in results}

        for track in self.tracks:
            fp_str = str(track.get("filepath", ""))
            if fp_str in result_map:
                status, match_info = result_map[fp_str]
                track["duplicate_status"] = status
                track["duplicate_match"] = match_info

        try:
            dup_col = self.cell_renderer.columns.index("duplicate")
        except ValueError:
            return
        top_left = self.index(0, dup_col)
        bottom_right = self.index(len(self.tracks) - 1, dup_col)
        self.dataChanged.emit(top_left, bottom_right)
        logging.debug(
            f"[TrackListModel] Background duplicate check complete: {len(results)} changes"
        )


class ColorPreservingDelegate(QStyledItemDelegate):
    """Delegate that preserves ForegroundRole color even when the row is selected."""

    def initStyleOption(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:  # noqa: N802
        super().initStyleOption(option, index)
        # Get the ForegroundRole color from the model
        color = index.data(Qt.ItemDataRole.ForegroundRole)
        if color:
            # Preserve the color even when item is selected/highlighted
            # Note: palette is available at runtime but not in stubs
            option.palette.setColor(  # type: ignore[attr-defined]
                option.palette.HighlightedText, color  # type: ignore[attr-defined]
            )


class TrackList(QTableView):
    """Widget for displaying audio tracks as a table."""

    track_selected = Signal(Path)
    add_to_playlist_requested = Signal(Path, int)  # filepath, playlist_id
    files_dropped = Signal(list)  # List of Path objects (files and directories)

    def __init__(
        self,
        parent: Any = None,
        database: Any = None,
        event_bus: Any = None,
        config: Any = None,
        mode: str = "jukebox",
    ):
        """Initialize track list.

        Args:
            parent: Parent widget
            database: Database instance (for refreshing data)
            event_bus: Event bus instance (for subscribing to updates)
            config: Config instance (for genre names)
            mode: Application mode ("jukebox" or "curating")
        """
        super().__init__(parent)

        # Set model - store reference for direct access
        self._track_model = TrackListModel(database, event_bus, config, mode)
        self.setModel(self._track_model)

        # Table configuration
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.setShowGrid(False)  # No grid lines

        # Vertical header shows row numbers (n/total)
        self.verticalHeader().setVisible(True)
        self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)

        # Horizontal header configuration
        h_header = self.horizontalHeader()
        h_header.setStretchLastSection(False)  # Manual column sizing

        # Set column widths from configuration
        columns = COLUMNS_JUKEBOX if mode == AppMode.JUKEBOX.value else COLUMNS_CURATING
        for col_idx, col_name in enumerate(columns):
            self.setColumnWidth(col_idx, COLUMN_WIDTHS[col_name])
            if col_name in ("duplicate", "filename", "artist", "title"):
                self.setItemDelegateForColumn(col_idx, ColorPreservingDelegate(self))

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

    @property
    def track_model(self) -> TrackListModel:
        """Get the underlying TrackListModel (bypassing any proxy)."""
        return self._track_model

    def set_proxy_model(self, proxy: QSortFilterProxyModel) -> None:
        """Insert a proxy model between the source model and the view.

        Args:
            proxy: The proxy model to insert
        """
        proxy.setSourceModel(self._track_model)
        self.setModel(proxy)

    def remove_proxy_model(self) -> None:
        """Remove any proxy model and restore direct source model."""
        self.setModel(self._track_model)

    def select_track_by_filepath(self, filepath: Path) -> None:
        """Select a track by its filepath, handling proxy mapping if needed.

        Args:
            filepath: Path of the track to select
        """
        source_row = self._track_model.find_row_by_filepath(filepath)
        if source_row < 0:
            return

        model = self.model()
        if isinstance(model, QSortFilterProxyModel):
            # Map source row to proxy row
            source_index = self._track_model.index(source_row, 0)
            proxy_index = model.mapFromSource(source_index)
            if proxy_index.isValid():
                self.selectRow(proxy_index.row())
        else:
            self.selectRow(source_row)

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
        self._track_model.add_track(filepath, title, artist, genre, duration_seconds)

    def add_tracks(self, filepaths: list[Path]) -> None:
        """Add multiple tracks.

        Args:
            filepaths: List of paths to audio files
        """
        for filepath in filepaths:
            self.add_track(filepath)

    def clear_tracks(self) -> None:
        """Clear all tracks."""
        self._track_model.clear()

    def count(self) -> int:
        """Get number of visible tracks in the list.

        Returns:
            Number of tracks (filtered if proxy is active)
        """
        return self.model().rowCount()

    def item(self, row: int) -> Any:
        """Get item at row (for compatibility with tests).

        Args:
            row: Row index

        Returns:
            Object with text() method returning the display text
        """
        if 0 <= row < self._track_model.rowCount():
            # Return a simple object with text() method
            track = self._track_model.tracks[row]

            class _Item:
                def __init__(self, track_data: dict[str, Any]) -> None:
                    self._track = track_data

                def text(self) -> str:
                    artist = self._track.get("artist")
                    title = self._track.get("title")
                    if artist and title:
                        return f"{artist} - {title}"
                    elif title:
                        return str(title)
                    else:
                        return str(self._track["filepath"].name)

            return _Item(track)
        return None

    def setCurrentRow(self, row: int) -> None:  # noqa: N802
        """Select row by index (for compatibility with tests).

        Args:
            row: Row index to select
        """
        if 0 <= row < self.model().rowCount():
            self.selectRow(row)

    def get_selected_track(self) -> Path | None:
        """Get currently selected track.

        Returns:
            Path to selected track or None
        """
        index = self.selectionModel().currentIndex()
        if index.isValid():
            result = self.model().data(index, Qt.ItemDataRole.UserRole)
            if isinstance(result, Path):
                return result
        return None

    def set_playlists(self, playlists: list[Any]) -> None:
        """Set available playlists for context menu."""
        self.playlists = playlists

    def set_mode(self, mode: str) -> None:
        """Update the display mode and reconfigure columns.

        Args:
            mode: Application mode ("jukebox" or "curating")
        """
        self._track_model.set_mode(mode)
        # Reconfigure column widths and delegates for the new mode
        columns = self._track_model.cell_renderer.columns
        for col_idx, col_name in enumerate(columns):
            self.setColumnWidth(col_idx, COLUMN_WIDTHS[col_name])
            if col_name in ("duplicate", "filename", "artist", "title"):
                self.setItemDelegateForColumn(col_idx, ColorPreservingDelegate(self))

    def _on_row_clicked(self, index: QModelIndex) -> None:
        """Handle row click."""
        if index.isValid():
            filepath = self.model().data(index, Qt.ItemDataRole.UserRole)
            if filepath:
                self.track_selected.emit(filepath)

    def _show_context_menu(self, position: Any) -> None:
        """Show context menu on right-click."""
        index = self.indexAt(position)
        if not index.isValid():
            return

        filepath = self.model().data(index, Qt.ItemDataRole.UserRole)
        if not filepath:
            return

        # Check if file exists on disk
        row = self._track_model.find_row_by_filepath(filepath)
        file_missing = False
        if 0 <= row < len(self._track_model.tracks):
            file_missing = self._track_model.tracks[row].get("file_missing", False)

        menu = QMenu(self)

        if not file_missing:
            # File exists: show full context menu
            import sys

            file_manager_label = (
                "Show in Finder" if sys.platform == "darwin" else "Show in File Manager"
            )
            show_in_finder = QAction(file_manager_label, self)
            show_in_finder.triggered.connect(lambda: self._show_in_file_manager(filepath))
            menu.addAction(show_in_finder)

        copy_path = QAction("Copy Path", self)
        copy_path.triggered.connect(lambda: self._copy_path_to_clipboard(filepath))
        menu.addAction(copy_path)

        if not file_missing:
            # Add playlist submenu if playlists exist
            if self.playlists:
                menu.addSeparator()
                add_menu = menu.addMenu("Add to Playlist")
                for playlist in self.playlists:
                    action = QAction(playlist["name"], self)
                    action.triggered.connect(
                        lambda checked, p=playlist, fp=filepath: self._add_to_playlist(fp, p["id"])
                    )
                    add_menu.addAction(action)

            # Add plugin context menu actions
            main_window = self.window()
            if hasattr(main_window, "ui_builder"):
                plugin_actions = main_window.ui_builder.get_track_context_actions()
                if plugin_actions:
                    menu.addSeparator()
                    # Get track info from database for plugin callbacks
                    track_dict = self._get_track_dict(filepath)

                    for ctx_action in plugin_actions:
                        if ctx_action.separator_before:
                            menu.addSeparator()

                        action = QAction(ctx_action.text, self)
                        # Capture ctx_action and track_dict in closure
                        action.triggered.connect(
                            lambda checked, cb=ctx_action.callback, t=track_dict: cb(t)
                        )
                        menu.addAction(action)

        # Remove action — always available
        menu.addSeparator()
        remove_action = QAction("Remove from List", self)
        remove_action.triggered.connect(lambda: self._remove_track(filepath))
        menu.addAction(remove_action)

        menu.exec(self.mapToGlobal(position))

    def _show_in_file_manager(self, filepath: Path) -> None:
        """Open the platform file manager and select the file."""
        import subprocess
        import sys

        filepath_str = str(filepath) if isinstance(filepath, Path) else filepath
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", filepath_str])
        elif sys.platform == "win32":
            subprocess.run(["explorer", "/select,", filepath_str])
        else:
            # Linux: open the containing directory
            parent_dir = str(Path(filepath_str).parent)
            subprocess.run(["xdg-open", parent_dir])

    def _copy_path_to_clipboard(self, filepath: Path) -> None:
        """Copy file path to clipboard."""
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        filepath_str = str(filepath) if isinstance(filepath, Path) else filepath
        clipboard.setText(filepath_str)

    def _get_track_dict(self, filepath: Path) -> dict[str, Any]:
        """Get track information as dictionary for plugin callbacks.

        Args:
            filepath: Path to the track file

        Returns:
            Dictionary with track information
        """
        main_window = self.window()
        if hasattr(main_window, "database"):
            track = main_window.database.get_track_by_filepath(str(filepath))
            if track:
                return dict(track)

        # Fallback: return minimal info from filepath
        return {
            "filepath": str(filepath),
            "filename": filepath.name if isinstance(filepath, Path) else Path(filepath).name,
        }

    def _remove_track(self, filepath: Path) -> None:
        """Remove a track from the list and database."""
        # Delete from database if present
        main_window = self.window()
        if hasattr(main_window, "database"):
            main_window.database.tracks.delete_by_filepath(str(filepath))

        # Emit TRACK_DELETED so the model removes the row
        event_bus = self._track_model.event_bus
        if event_bus:
            event_bus.emit(Events.TRACK_DELETED, filepath=filepath)

    def _add_to_playlist(self, filepath: Path, playlist_id: int) -> None:
        """Add track to playlist."""
        self.add_to_playlist_requested.emit(filepath, playlist_id)

    def select_next_track(self) -> None:
        """Select and play next track in list."""
        current_index = self.selectionModel().currentIndex()
        current_row = current_index.row() if current_index.isValid() else -1

        model = self.model()
        if current_row < model.rowCount() - 1:
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
