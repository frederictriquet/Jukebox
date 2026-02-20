"""Table model for cue sheet entries."""

from __future__ import annotations

import logging

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)

from plugins.cue_maker.constants import (
    COLUMN_HEADERS,
    INDICATOR_GAP,
    INDICATOR_OVERLAP,
    TableColumn,
)
from plugins.cue_maker.model import CueEntry, CueSheet, EntryStatus

logger = logging.getLogger(__name__)

_INDEX_TYPE = QModelIndex | QPersistentModelIndex


class CueTableModel(QAbstractTableModel):
    """Table model wrapping a CueSheet for display in QTableView.

    Provides read/write access to cue entries with proper Qt model notifications.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize with empty cue sheet."""
        super().__init__(parent)
        self._sheet = CueSheet()

    @property
    def sheet(self) -> CueSheet:
        """Access the underlying cue sheet."""
        return self._sheet

    def rowCount(self, parent: _INDEX_TYPE | None = None) -> int:
        """Return number of entries."""
        return len(self._sheet.entries)

    def columnCount(self, parent: _INDEX_TYPE | None = None) -> int:
        """Return number of columns."""
        return len(COLUMN_HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        """Return column headers."""
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
            and 0 <= section < len(COLUMN_HEADERS)
        ):
            return COLUMN_HEADERS[section]
        return None

    def data(
        self, index: _INDEX_TYPE, role: int = Qt.ItemDataRole.DisplayRole
    ) -> str | float | None:
        """Return data for the given index and role."""
        if not index.isValid() or index.row() >= len(self._sheet.entries):
            return None

        entry = self._sheet.entries[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_data(entry, col)

        if role == Qt.ItemDataRole.UserRole:
            return self._raw_data(entry, col)

        return None

    def _display_data(self, entry: CueEntry, col: int) -> str:
        """Return formatted display string for a cell."""
        if col == TableColumn.OVERLAP:
            return self._entry_status_indicator(entry)
        if col == TableColumn.TIME:
            return entry.to_display_time()
        if col == TableColumn.ARTIST:
            return entry.artist
        if col == TableColumn.TITLE:
            return entry.title
        if col == TableColumn.CONFIDENCE:
            if entry.status == EntryStatus.MANUAL:
                return "Manual"
            return f"{entry.confidence:.0%}"
        if col == TableColumn.DURATION:
            return entry.duration_to_display()
        if col == TableColumn.ACTIONS:
            return ""
        return ""

    def _entry_status_indicator(self, entry: CueEntry) -> str:
        """Return status indicator for entry: overlap, gap, or empty.

        Returns:
            INDICATOR_OVERLAP if entry overlaps another entry,
            INDICATOR_GAP if there is a gap with a neighbor,
            empty string if clean.
        """
        entries = self._sheet.entries
        idx = entries.index(entry)
        start = entry.start_time_ms
        end = start + entry.duration_ms

        # Check overlap with any other entry
        for other in entries:
            if other is entry:
                continue
            other_start = other.start_time_ms
            other_end = other_start + other.duration_ms
            if start < other_end and end > other_start:
                return INDICATOR_OVERLAP

        # Check gap with previous neighbor
        if idx > 0:
            prev = entries[idx - 1]
            prev_end = prev.start_time_ms + prev.duration_ms
            if prev_end < start:
                return INDICATOR_GAP

        # Check gap with next neighbor
        if idx < len(entries) - 1:
            nxt = entries[idx + 1]
            if end < nxt.start_time_ms:
                return INDICATOR_GAP

        return ""

    def _raw_data(self, entry: CueEntry, col: int) -> int | float | str | None:
        """Return raw data for programmatic access."""
        if col == TableColumn.TIME:
            return entry.start_time_ms
        if col == TableColumn.CONFIDENCE:
            return entry.confidence
        if col == TableColumn.DURATION:
            return entry.duration_ms
        return None

    def flags(self, index: _INDEX_TYPE) -> Qt.ItemFlag:
        """Return item flags - time, artist, title are editable."""
        base = super().flags(index)
        col = index.column()
        if col in (TableColumn.TIME, TableColumn.ARTIST, TableColumn.TITLE):
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def setData(
        self, index: _INDEX_TYPE, value: object, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        """Handle cell edits for time, artist, title."""
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False

        row = index.row()
        col = index.column()
        if row >= len(self._sheet.entries):
            return False

        entry = self._sheet.entries[row]

        if col == TableColumn.TIME:
            from plugins.cue_maker.exporter import CueExporter

            ms = CueExporter.display_time_to_ms(str(value))
            if ms is not None:
                self._sheet.update_timestamp(row, ms)
                # Re-sort may have moved rows, refresh entire model
                self.layoutChanged.emit()
                return True
            return False

        if col == TableColumn.ARTIST:
            entry.artist = str(value)
            self.dataChanged.emit(index, index, [])
            return True

        if col == TableColumn.TITLE:
            entry.title = str(value)
            self.dataChanged.emit(index, index, [])
            return True

        return False

    # --- Public API ---

    def load_entries(self, entries: list[CueEntry]) -> None:
        """Replace all entries with new list from analysis."""
        self.beginResetModel()
        self._sheet.clear()
        for entry in entries:
            self._sheet.entries.append(entry)
        self._sheet.sort_by_time()
        self.endResetModel()

    def set_metadata(self, filepath: str, title: str, artist: str) -> None:
        """Set mix metadata on the cue sheet."""
        self._sheet.mix_filepath = filepath
        self._sheet.mix_title = title
        self._sheet.mix_artist = artist

    def add_manual_entry(self, start_time_ms: int, artist: str, title: str) -> CueEntry:
        """Add a manually created entry and return it."""
        entry = CueEntry(
            start_time_ms=start_time_ms,
            artist=artist,
            title=title,
            confidence=0.0,
            duration_ms=0,
            status=EntryStatus.MANUAL,
        )
        row = len(self._sheet.entries)
        self.beginInsertRows(QModelIndex(), row, row)
        self._sheet.entries.append(entry)
        self._sheet.sort_by_time()
        self.endInsertRows()
        # Sort may reorder, refresh
        self.layoutChanged.emit()
        return entry

    def remove_entry(self, row: int) -> None:
        """Remove entry at row index."""
        if 0 <= row < len(self._sheet.entries):
            self.beginRemoveRows(QModelIndex(), row, row)
            self._sheet.remove_entry(row)
            self.endRemoveRows()

    def update_duration(self, row: int, duration_ms: int) -> None:
        """Update duration of entry at row and refresh all rows.

        Changing one entry's duration can affect overlap/gap indicators
        on neighboring entries, so we refresh the entire model.
        """
        if 0 <= row < len(self._sheet.entries):
            self._sheet.update_duration(row, duration_ms)
            self._emit_all_data_changed()

    def update_start_time(self, row: int, start_time_ms: int) -> None:
        """Update start time of entry at row (in ms) and re-sort.

        Works directly in milliseconds to avoid MM:SS precision loss.
        """
        if 0 <= row < len(self._sheet.entries):
            self._sheet.update_timestamp(row, start_time_ms)
            self.layoutChanged.emit()

    def _emit_all_data_changed(self) -> None:
        """Emit dataChanged for all rows (e.g. after overlap/gap status changes)."""
        if self._sheet.entries:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._sheet.entries) - 1, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right)

    def get_entry(self, row: int) -> CueEntry | None:
        """Get entry at row, or None if invalid."""
        if 0 <= row < len(self._sheet.entries):
            return self._sheet.entries[row]
        return None

    def clear(self) -> None:
        """Clear all entries."""
        self.beginResetModel()
        self._sheet.clear()
        self.endResetModel()

    def has_entries(self) -> bool:
        """Check if there are any entries."""
        return len(self._sheet.entries) > 0
