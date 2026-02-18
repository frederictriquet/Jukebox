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

from plugins.cue_maker.constants import COLUMN_HEADERS, TableColumn
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
            return "⚠️" if self._has_overlap(entry) else ""
        if col == TableColumn.TIME:
            return entry.to_display_time()
        if col == TableColumn.ARTIST:
            return entry.artist
        if col == TableColumn.TITLE:
            return entry.title
        if col == TableColumn.CONFIDENCE:
            return f"{entry.confidence:.0%}"
        if col == TableColumn.DURATION:
            return entry.duration_to_display()
        return ""

    def _has_overlap(self, entry: CueEntry) -> bool:
        """Check if entry's interval overlaps with any other entry."""
        start = entry.start_time_ms
        end = start + entry.duration_ms
        for other in self._sheet.entries:
            if other is entry:
                continue
            other_start = other.start_time_ms
            other_end = other_start + other.duration_ms
            if start < other_end and end > other_start:
                return True
        return False

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

    def add_manual_entry(self, start_time_ms: int, artist: str, title: str) -> None:
        """Add a manually created entry."""
        entry = CueEntry(
            start_time_ms=start_time_ms,
            artist=artist,
            title=title,
            confidence=1.0,
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

    def remove_entry(self, row: int) -> None:
        """Remove entry at row index."""
        if 0 <= row < len(self._sheet.entries):
            self.beginRemoveRows(QModelIndex(), row, row)
            self._sheet.remove_entry(row)
            self.endRemoveRows()

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

    def has_confirmed_entries(self) -> bool:
        """Check if there are entries ready for export."""
        return len(self._sheet.entries) > 0
