"""Tests for cue maker model module."""

from plugins.cue_maker.model import CueEntry, CueSheet, EntryStatus


class TestEntryStatus:
    """Test EntryStatus enum."""

    def test_status_values(self) -> None:
        """Test that status values are correct strings."""
        assert EntryStatus.PENDING.value == "pending"
        assert EntryStatus.CONFIRMED.value == "confirmed"
        assert EntryStatus.REJECTED.value == "rejected"
        assert EntryStatus.MANUAL.value == "manual"


class TestCueEntry:
    """Test CueEntry dataclass."""

    def test_initialization_minimal(self) -> None:
        """Test entry initializes with minimal required fields."""
        entry = CueEntry(
            start_time_ms=60000,  # 1:00
            artist="Test Artist",
            title="Test Title",
            confidence=0.95,
            duration_ms=180000,  # 3:00
        )

        assert entry.start_time_ms == 60000
        assert entry.artist == "Test Artist"
        assert entry.title == "Test Title"
        assert entry.confidence == 0.95
        assert entry.duration_ms == 180000
        assert entry.status == EntryStatus.PENDING
        assert entry.filepath == ""
        assert entry.track_id is None
        assert entry.time_stretch_ratio == 1.0

    def test_initialization_full(self) -> None:
        """Test entry initializes with all fields."""
        entry = CueEntry(
            start_time_ms=120000,
            artist="Full Artist",
            title="Full Title",
            confidence=0.85,
            duration_ms=240000,
            status=EntryStatus.CONFIRMED,
            filepath="/path/to/track.mp3",
            track_id=42,
            time_stretch_ratio=1.05,
        )

        assert entry.status == EntryStatus.CONFIRMED
        assert entry.filepath == "/path/to/track.mp3"
        assert entry.track_id == 42
        assert entry.time_stretch_ratio == 1.05

    def test_to_display_time_zero(self) -> None:
        """Test display time for zero milliseconds."""
        entry = CueEntry(
            start_time_ms=0,
            artist="Artist",
            title="Title",
            confidence=1.0,
            duration_ms=0,
        )
        assert entry.to_display_time() == "00:00"

    def test_to_display_time_seconds_only(self) -> None:
        """Test display time for seconds only (no minutes)."""
        entry = CueEntry(
            start_time_ms=45000,  # 45 seconds
            artist="Artist",
            title="Title",
            confidence=1.0,
            duration_ms=0,
        )
        assert entry.to_display_time() == "00:45"

    def test_to_display_time_minutes_and_seconds(self) -> None:
        """Test display time for minutes and seconds."""
        entry = CueEntry(
            start_time_ms=185000,  # 3:05
            artist="Artist",
            title="Title",
            confidence=1.0,
            duration_ms=0,
        )
        assert entry.to_display_time() == "03:05"

    def test_to_display_time_large_value(self) -> None:
        """Test display time for large values (hours in minutes)."""
        entry = CueEntry(
            start_time_ms=3665000,  # 61:05
            artist="Artist",
            title="Title",
            confidence=1.0,
            duration_ms=0,
        )
        assert entry.to_display_time() == "61:05"

    def test_duration_to_display(self) -> None:
        """Test duration display conversion."""
        entry = CueEntry(
            start_time_ms=0,
            artist="Artist",
            title="Title",
            confidence=1.0,
            duration_ms=240000,  # 4:00
        )
        assert entry.duration_to_display() == "04:00"

    def test_duration_to_display_fractional_seconds(self) -> None:
        """Test duration with fractional seconds truncates."""
        entry = CueEntry(
            start_time_ms=0,
            artist="Artist",
            title="Title",
            confidence=1.0,
            duration_ms=185999,  # 3:05.999
        )
        assert entry.duration_to_display() == "03:05"


class TestCueSheet:
    """Test CueSheet class."""

    def test_initialization_empty(self) -> None:
        """Test cue sheet initializes empty with no parameters."""
        sheet = CueSheet()

        assert sheet.mix_filepath == ""
        assert sheet.mix_title == ""
        assert sheet.mix_artist == ""
        assert sheet.entries == []

    def test_initialization_with_metadata(self) -> None:
        """Test cue sheet initializes with metadata."""
        sheet = CueSheet(
            mix_filepath="/path/to/mix.mp3",
            mix_title="Test Mix",
            mix_artist="DJ Test",
        )

        assert sheet.mix_filepath == "/path/to/mix.mp3"
        assert sheet.mix_title == "Test Mix"
        assert sheet.mix_artist == "DJ Test"

    def test_add_entry_single(self) -> None:
        """Test adding a single entry."""
        sheet = CueSheet()
        entry = CueEntry(
            start_time_ms=60000,
            artist="Artist 1",
            title="Title 1",
            confidence=0.9,
            duration_ms=180000,
        )

        sheet.add_entry(entry)

        assert len(sheet.entries) == 1
        assert sheet.entries[0] == entry

    def test_add_entry_maintains_sort_order(self) -> None:
        """Test adding entries maintains chronological order."""
        sheet = CueSheet()

        entry1 = CueEntry(60000, "Artist 1", "Title 1", 0.9, 180000)
        entry2 = CueEntry(30000, "Artist 2", "Title 2", 0.85, 120000)
        entry3 = CueEntry(90000, "Artist 3", "Title 3", 0.95, 150000)

        sheet.add_entry(entry1)
        sheet.add_entry(entry2)  # Earlier time
        sheet.add_entry(entry3)  # Later time

        assert len(sheet.entries) == 3
        assert sheet.entries[0].start_time_ms == 30000
        assert sheet.entries[1].start_time_ms == 60000
        assert sheet.entries[2].start_time_ms == 90000

    def test_remove_entry_valid_index(self) -> None:
        """Test removing entry at valid index."""
        sheet = CueSheet()
        entry1 = CueEntry(30000, "Artist 1", "Title 1", 0.9, 180000)
        entry2 = CueEntry(60000, "Artist 2", "Title 2", 0.85, 120000)
        entry3 = CueEntry(90000, "Artist 3", "Title 3", 0.95, 150000)

        sheet.add_entry(entry1)
        sheet.add_entry(entry2)
        sheet.add_entry(entry3)

        sheet.remove_entry(1)  # Remove middle entry

        assert len(sheet.entries) == 2
        assert sheet.entries[0].artist == "Artist 1"
        assert sheet.entries[1].artist == "Artist 3"

    def test_remove_entry_invalid_index_negative(self) -> None:
        """Test removing entry with negative index does nothing."""
        sheet = CueSheet()
        entry = CueEntry(60000, "Artist", "Title", 0.9, 180000)
        sheet.add_entry(entry)

        sheet.remove_entry(-1)

        assert len(sheet.entries) == 1

    def test_remove_entry_invalid_index_too_large(self) -> None:
        """Test removing entry with out-of-bounds index does nothing."""
        sheet = CueSheet()
        entry = CueEntry(60000, "Artist", "Title", 0.9, 180000)
        sheet.add_entry(entry)

        sheet.remove_entry(10)

        assert len(sheet.entries) == 1

    def test_update_timestamp_maintains_sort(self) -> None:
        """Test updating timestamp re-sorts entries."""
        sheet = CueSheet()
        entry1 = CueEntry(30000, "Artist 1", "Title 1", 0.9, 180000)
        entry2 = CueEntry(60000, "Artist 2", "Title 2", 0.85, 120000)
        entry3 = CueEntry(90000, "Artist 3", "Title 3", 0.95, 150000)

        sheet.add_entry(entry1)
        sheet.add_entry(entry2)
        sheet.add_entry(entry3)

        # Move first entry to end
        sheet.update_timestamp(0, 120000)

        assert sheet.entries[0].artist == "Artist 2"  # 60000
        assert sheet.entries[1].artist == "Artist 3"  # 90000
        assert sheet.entries[2].artist == "Artist 1"  # 120000 (updated)

    def test_update_timestamp_invalid_index(self) -> None:
        """Test updating timestamp with invalid index does nothing."""
        sheet = CueSheet()
        entry = CueEntry(60000, "Artist", "Title", 0.9, 180000)
        sheet.add_entry(entry)

        sheet.update_timestamp(10, 90000)

        assert sheet.entries[0].start_time_ms == 60000

    def test_set_status_valid_index(self) -> None:
        """Test setting status at valid index."""
        sheet = CueSheet()
        entry = CueEntry(60000, "Artist", "Title", 0.9, 180000)
        sheet.add_entry(entry)

        sheet.set_status(0, EntryStatus.CONFIRMED)

        assert sheet.entries[0].status == EntryStatus.CONFIRMED

    def test_set_status_invalid_index(self) -> None:
        """Test setting status with invalid index does nothing."""
        sheet = CueSheet()
        entry = CueEntry(60000, "Artist", "Title", 0.9, 180000)
        sheet.add_entry(entry)

        sheet.set_status(10, EntryStatus.CONFIRMED)

        assert sheet.entries[0].status == EntryStatus.PENDING

    def test_get_confirmed_entries_empty(self) -> None:
        """Test getting confirmed entries from empty sheet."""
        sheet = CueSheet()
        confirmed = sheet.get_confirmed_entries()

        assert confirmed == []

    def test_get_confirmed_entries_returns_all(self) -> None:
        """Test getting all entries for export."""
        sheet = CueSheet()

        sheet.add_entry(CueEntry(30000, "Artist 1", "Title 1", 0.9, 180000))
        sheet.add_entry(CueEntry(60000, "Artist 2", "Title 2", 0.85, 120000))
        sheet.add_entry(CueEntry(90000, "Artist 3", "Title 3", 0.95, 150000))

        confirmed = sheet.get_confirmed_entries()

        assert len(confirmed) == 3

    def test_sort_by_time(self) -> None:
        """Test explicit sort by time."""
        sheet = CueSheet()

        # Add entries out of order, don't use add_entry (which auto-sorts)
        entry1 = CueEntry(90000, "Artist 1", "Title 1", 0.9, 180000)
        entry2 = CueEntry(30000, "Artist 2", "Title 2", 0.85, 120000)
        entry3 = CueEntry(60000, "Artist 3", "Title 3", 0.95, 150000)

        sheet.entries.append(entry1)
        sheet.entries.append(entry2)
        sheet.entries.append(entry3)

        # Manually sort
        sheet.sort_by_time()

        assert sheet.entries[0].start_time_ms == 30000
        assert sheet.entries[1].start_time_ms == 60000
        assert sheet.entries[2].start_time_ms == 90000

    def test_clear(self) -> None:
        """Test clearing all entries."""
        sheet = CueSheet()
        entry1 = CueEntry(30000, "Artist 1", "Title 1", 0.9, 180000)
        entry2 = CueEntry(60000, "Artist 2", "Title 2", 0.85, 120000)

        sheet.add_entry(entry1)
        sheet.add_entry(entry2)

        assert len(sheet.entries) == 2

        sheet.clear()

        assert len(sheet.entries) == 0
