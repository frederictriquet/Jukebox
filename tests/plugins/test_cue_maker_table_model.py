"""Tests for cue maker table model."""

from PySide6.QtCore import QModelIndex, Qt

from plugins.cue_maker.constants import INDICATOR_GAP, INDICATOR_OVERLAP, TableColumn
from plugins.cue_maker.model import CueEntry, EntryStatus
from plugins.cue_maker.table_model import CueTableModel


class TestCueTableModel:
    """Test CueTableModel class."""

    def test_initialization(self, qapp) -> None:  # type: ignore
        """Test model initializes with empty sheet."""
        model = CueTableModel()
        assert model.rowCount() == 0
        assert model.columnCount() == 7
        assert model.sheet is not None
        assert len(model.sheet.entries) == 0

    def test_row_count_reflects_entries(self, qapp) -> None:  # type: ignore
        """Test rowCount returns number of entries."""
        model = CueTableModel()
        assert model.rowCount() == 0

        model.sheet.entries.append(CueEntry(0, "Artist", "Title", 1.0, 180000))
        # Note: manual append doesn't notify, so count is stale until model reset
        # Use add_manual_entry for real updates
        model.beginResetModel()
        model.endResetModel()
        assert model.rowCount() == 1

    def test_column_count(self, qapp) -> None:  # type: ignore
        """Test columnCount returns 7 columns."""
        model = CueTableModel()
        assert model.columnCount() == 7

    def test_header_data_horizontal(self, qapp) -> None:  # type: ignore
        """Test horizontal headers."""
        model = CueTableModel()
        headers = [
            "",
            "Time",
            "Artist",
            "Title",
            "Confidence",
            "Duration",
            "",
        ]
        for col, expected in enumerate(headers):
            result = model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            assert result == expected

    def test_header_data_invalid_column(self, qapp) -> None:  # type: ignore
        """Test headerData with invalid column returns None."""
        model = CueTableModel()
        result = model.headerData(99, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        assert result is None

    def test_data_display_role(self, qapp) -> None:  # type: ignore
        """Test data returns formatted display strings."""
        model = CueTableModel()
        entry = CueEntry(
            start_time_ms=185000,  # 3:05
            artist="Test Artist",
            title="Test Title",
            confidence=0.95,
            duration_ms=240000,  # 4:00
        )
        model.load_entries([entry])

        idx_time = model.index(0, TableColumn.TIME)
        idx_artist = model.index(0, TableColumn.ARTIST)
        idx_title = model.index(0, TableColumn.TITLE)
        idx_confidence = model.index(0, TableColumn.CONFIDENCE)
        idx_duration = model.index(0, TableColumn.DURATION)

        assert model.data(idx_time, Qt.ItemDataRole.DisplayRole) == "03:05"
        assert model.data(idx_artist, Qt.ItemDataRole.DisplayRole) == "Test Artist"
        assert model.data(idx_title, Qt.ItemDataRole.DisplayRole) == "Test Title"
        assert model.data(idx_confidence, Qt.ItemDataRole.DisplayRole) == "95%"
        assert model.data(idx_duration, Qt.ItemDataRole.DisplayRole) == "04:00"

    def test_data_user_role(self, qapp) -> None:  # type: ignore
        """Test data returns raw values for UserRole."""
        model = CueTableModel()
        entry = CueEntry(
            start_time_ms=185000,
            artist="Artist",
            title="Title",
            confidence=0.75,
            duration_ms=240000,
        )
        model.load_entries([entry])

        idx_time = model.index(0, TableColumn.TIME)
        idx_confidence = model.index(0, TableColumn.CONFIDENCE)
        idx_duration = model.index(0, TableColumn.DURATION)

        assert model.data(idx_time, Qt.ItemDataRole.UserRole) == 185000
        assert model.data(idx_confidence, Qt.ItemDataRole.UserRole) == 0.75
        assert model.data(idx_duration, Qt.ItemDataRole.UserRole) == 240000

    def test_data_invalid_index(self, qapp) -> None:  # type: ignore
        """Test data with invalid index returns None."""
        model = CueTableModel()
        invalid_idx = QModelIndex()
        assert model.data(invalid_idx, Qt.ItemDataRole.DisplayRole) is None

    def test_flags_editable_columns(self, qapp) -> None:  # type: ignore
        """Test time, artist, title are editable."""
        model = CueTableModel()
        model.load_entries([CueEntry(0, "A", "T", 1.0, 0)])

        idx_time = model.index(0, TableColumn.TIME)
        idx_artist = model.index(0, TableColumn.ARTIST)
        idx_title = model.index(0, TableColumn.TITLE)

        assert Qt.ItemFlag.ItemIsEditable in model.flags(idx_time)
        assert Qt.ItemFlag.ItemIsEditable in model.flags(idx_artist)
        assert Qt.ItemFlag.ItemIsEditable in model.flags(idx_title)

    def test_flags_non_editable_columns(self, qapp) -> None:  # type: ignore
        """Test confidence, duration, actions are not editable."""
        model = CueTableModel()
        model.load_entries([CueEntry(0, "A", "T", 1.0, 0)])

        idx_confidence = model.index(0, TableColumn.CONFIDENCE)
        idx_duration = model.index(0, TableColumn.DURATION)

        assert Qt.ItemFlag.ItemIsEditable not in model.flags(idx_confidence)
        assert Qt.ItemFlag.ItemIsEditable not in model.flags(idx_duration)

    def test_set_data_time_valid(self, qapp) -> None:  # type: ignore
        """Test setData updates time with valid MM:SS format."""
        model = CueTableModel()
        model.load_entries([CueEntry(0, "A", "T", 1.0, 0)])

        idx = model.index(0, TableColumn.TIME)
        result = model.setData(idx, "02:30", Qt.ItemDataRole.EditRole)

        assert result is True
        assert model.sheet.entries[0].start_time_ms == 150000  # 2:30 in ms

    def test_set_data_time_invalid(self, qapp) -> None:  # type: ignore
        """Test setData rejects invalid time format."""
        model = CueTableModel()
        model.load_entries([CueEntry(60000, "A", "T", 1.0, 0)])

        idx = model.index(0, TableColumn.TIME)
        result = model.setData(idx, "invalid", Qt.ItemDataRole.EditRole)

        assert result is False
        assert model.sheet.entries[0].start_time_ms == 60000  # Unchanged

    def test_set_data_artist(self, qapp) -> None:  # type: ignore
        """Test setData updates artist."""
        model = CueTableModel()
        model.load_entries([CueEntry(0, "Old Artist", "T", 1.0, 0)])

        idx = model.index(0, TableColumn.ARTIST)
        result = model.setData(idx, "New Artist", Qt.ItemDataRole.EditRole)

        assert result is True
        assert model.sheet.entries[0].artist == "New Artist"

    def test_set_data_title(self, qapp) -> None:  # type: ignore
        """Test setData updates title."""
        model = CueTableModel()
        model.load_entries([CueEntry(0, "A", "Old Title", 1.0, 0)])

        idx = model.index(0, TableColumn.TITLE)
        result = model.setData(idx, "New Title", Qt.ItemDataRole.EditRole)

        assert result is True
        assert model.sheet.entries[0].title == "New Title"

    def test_set_data_invalid_column(self, qapp) -> None:  # type: ignore
        """Test setData on non-editable column returns False."""
        model = CueTableModel()
        model.load_entries([CueEntry(0, "A", "T", 1.0, 0)])

        idx = model.index(0, TableColumn.CONFIDENCE)
        result = model.setData(idx, 0.99, Qt.ItemDataRole.EditRole)

        assert result is False

    def test_load_entries_empty(self, qapp) -> None:  # type: ignore
        """Test load_entries with empty list."""
        model = CueTableModel()
        model.load_entries([])

        assert model.rowCount() == 0

    def test_load_entries_multiple(self, qapp) -> None:  # type: ignore
        """Test load_entries with multiple entries."""
        model = CueTableModel()
        entries = [
            CueEntry(60000, "A1", "T1", 0.9, 180000),
            CueEntry(30000, "A2", "T2", 0.85, 120000),  # Earlier time
            CueEntry(90000, "A3", "T3", 0.95, 150000),
        ]
        model.load_entries(entries)

        assert model.rowCount() == 3
        # Should be sorted by time
        assert model.sheet.entries[0].start_time_ms == 30000
        assert model.sheet.entries[1].start_time_ms == 60000
        assert model.sheet.entries[2].start_time_ms == 90000

    def test_set_metadata(self, qapp) -> None:  # type: ignore
        """Test set_metadata updates sheet metadata."""
        model = CueTableModel()
        model.set_metadata("/path/to/mix.mp3", "My Mix", "DJ Name")

        assert model.sheet.mix_filepath == "/path/to/mix.mp3"
        assert model.sheet.mix_title == "My Mix"
        assert model.sheet.mix_artist == "DJ Name"

    def test_add_manual_entry(self, qapp) -> None:  # type: ignore
        """Test add_manual_entry creates MANUAL entry."""
        model = CueTableModel()
        model.load_entries([CueEntry(60000, "A1", "T1", 0.9, 180000)])

        model.add_manual_entry(30000, "Manual Artist", "Manual Title")

        assert model.rowCount() == 2
        # Should be sorted by time
        assert model.sheet.entries[0].start_time_ms == 30000
        assert model.sheet.entries[0].artist == "Manual Artist"
        assert model.sheet.entries[0].title == "Manual Title"
        assert model.sheet.entries[0].status == EntryStatus.MANUAL
        assert model.sheet.entries[0].confidence == 0.0

    def test_remove_entry_valid(self, qapp) -> None:  # type: ignore
        """Test remove_entry removes entry at index."""
        model = CueTableModel()
        model.load_entries(
            [
                CueEntry(30000, "A1", "T1", 0.9, 180000),
                CueEntry(60000, "A2", "T2", 0.85, 120000),
                CueEntry(90000, "A3", "T3", 0.95, 150000),
            ]
        )

        model.remove_entry(1)  # Remove middle entry

        assert model.rowCount() == 2
        assert model.sheet.entries[0].artist == "A1"
        assert model.sheet.entries[1].artist == "A3"

    def test_remove_entry_invalid_index(self, qapp) -> None:  # type: ignore
        """Test remove_entry with invalid index does nothing."""
        model = CueTableModel()
        model.load_entries([CueEntry(60000, "A", "T", 0.9, 180000)])

        model.remove_entry(10)  # Out of bounds

        assert model.rowCount() == 1  # Unchanged

    def test_get_entry_valid(self, qapp) -> None:  # type: ignore
        """Test get_entry returns entry at row."""
        model = CueTableModel()
        entry = CueEntry(60000, "Artist", "Title", 0.9, 180000)
        model.load_entries([entry])

        result = model.get_entry(0)

        assert result is not None
        assert result.artist == "Artist"
        assert result.title == "Title"

    def test_get_entry_invalid(self, qapp) -> None:  # type: ignore
        """Test get_entry returns None for invalid row."""
        model = CueTableModel()
        model.load_entries([CueEntry(60000, "A", "T", 0.9, 180000)])

        result = model.get_entry(10)

        assert result is None

    def test_clear(self, qapp) -> None:  # type: ignore
        """Test clear removes all entries."""
        model = CueTableModel()
        model.load_entries(
            [
                CueEntry(30000, "A1", "T1", 0.9, 180000),
                CueEntry(60000, "A2", "T2", 0.85, 120000),
            ]
        )

        model.clear()

        assert model.rowCount() == 0
        assert len(model.sheet.entries) == 0

    def test_has_confirmed_entries_true(self, qapp) -> None:  # type: ignore
        """Test has_confirmed_entries returns True when entries exist."""
        model = CueTableModel()
        model.load_entries([CueEntry(30000, "A1", "T1", 0.9, 180000)])

        assert model.has_confirmed_entries() is True

    def test_has_confirmed_entries_empty(self, qapp) -> None:  # type: ignore
        """Test has_confirmed_entries returns False when empty."""
        model = CueTableModel()
        assert model.has_confirmed_entries() is False

    def test_entry_status_indicator_overlap(self, qapp) -> None:  # type: ignore
        """Test _entry_status_indicator returns overlap indicator for overlapping entries."""
        model = CueTableModel()
        # Entry 1: 0-180s, Entry 2: 120-300s (overlap at 120-180s)
        entries = [
            CueEntry(0, "A1", "T1", 0.9, 180000),
            CueEntry(120000, "A2", "T2", 0.85, 180000),
        ]
        model.load_entries(entries)

        idx = model.index(0, TableColumn.OVERLAP)
        assert model.data(idx, Qt.ItemDataRole.DisplayRole) == INDICATOR_OVERLAP
        idx1 = model.index(1, TableColumn.OVERLAP)
        assert model.data(idx1, Qt.ItemDataRole.DisplayRole) == INDICATOR_OVERLAP

    def test_entry_status_indicator_gap(self, qapp) -> None:  # type: ignore
        """Test _entry_status_indicator returns gap indicator when there is a gap."""
        model = CueTableModel()
        # Entry 1: 0-120s, Entry 2: 180-300s (gap from 120-180s)
        entries = [
            CueEntry(0, "A1", "T1", 0.9, 120000),
            CueEntry(180000, "A2", "T2", 0.85, 120000),
        ]
        model.load_entries(entries)

        # First entry has gap with next
        idx0 = model.index(0, TableColumn.OVERLAP)
        assert model.data(idx0, Qt.ItemDataRole.DisplayRole) == INDICATOR_GAP

        # Second entry has gap with previous
        idx1 = model.index(1, TableColumn.OVERLAP)
        assert model.data(idx1, Qt.ItemDataRole.DisplayRole) == INDICATOR_GAP

    def test_entry_status_indicator_clean(self, qapp) -> None:  # type: ignore
        """Test _entry_status_indicator returns empty for contiguous entries."""
        model = CueTableModel()
        # Entry 1: 0-120s, Entry 2: 120-240s (perfectly contiguous)
        entries = [
            CueEntry(0, "A1", "T1", 0.9, 120000),
            CueEntry(120000, "A2", "T2", 0.85, 120000),
        ]
        model.load_entries(entries)

        idx0 = model.index(0, TableColumn.OVERLAP)
        assert model.data(idx0, Qt.ItemDataRole.DisplayRole) == ""
        idx1 = model.index(1, TableColumn.OVERLAP)
        assert model.data(idx1, Qt.ItemDataRole.DisplayRole) == ""

    def test_update_duration(self, qapp) -> None:  # type: ignore
        """Test update_duration modifies entry duration and emits dataChanged."""
        model = CueTableModel()
        model.load_entries([CueEntry(0, "A", "T", 1.0, 180000)])

        model.update_duration(0, 240000)

        assert model.sheet.entries[0].duration_ms == 240000

    def test_update_duration_invalid_row(self, qapp) -> None:  # type: ignore
        """Test update_duration with invalid row does nothing."""
        model = CueTableModel()
        model.load_entries([CueEntry(0, "A", "T", 1.0, 180000)])

        model.update_duration(10, 240000)

        assert model.sheet.entries[0].duration_ms == 180000  # Unchanged
