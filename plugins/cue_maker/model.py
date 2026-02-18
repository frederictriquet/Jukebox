"""Data models for cue sheets."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EntryStatus(Enum):
    """Status of a cue entry."""

    PENDING = "pending"  # Awaiting user validation
    CONFIRMED = "confirmed"  # Confirmed by user
    REJECTED = "rejected"  # Rejected by user
    MANUAL = "manual"  # Manually added by user


@dataclass
class CueEntry:
    """A single entry in a cue sheet.

    Represents a track in a DJ mix with timing information and metadata.
    All time values are rounded to the nearest second (multiple of 1000ms)
    since cue sheets describe transitions that typically last 30+ seconds.
    """

    start_time_ms: int  # Position in the mix (milliseconds, rounded to second)
    artist: str  # Track artist
    title: str  # Track title
    confidence: float  # Match confidence 0.0-1.0 (1.0 for manual entries)
    duration_ms: int  # Estimated duration in the mix (rounded to second)
    status: EntryStatus = EntryStatus.PENDING
    filepath: str = ""  # Path to audio file (if available)
    track_id: int | None = None  # Database track ID (for shazamix matches)
    time_stretch_ratio: float = 1.0  # Detected tempo change (1.0 = no change)

    def __post_init__(self) -> None:
        """Round time values to the nearest second."""
        self.start_time_ms = round(self.start_time_ms / 1000) * 1000
        self.duration_ms = round(self.duration_ms / 1000) * 1000

    def to_display_time(self) -> str:
        """Convert start_time_ms to MM:SS format for display.

        Returns:
            Time string in MM:SS format
        """
        total_seconds = self.start_time_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def duration_to_display(self) -> str:
        """Convert duration_ms to MM:SS format for display.

        Returns:
            Duration string in MM:SS format
        """
        total_seconds = self.duration_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"


class CueSheet:
    """Model for a cue sheet - ordered list of cue entries.

    Manages the list of tracks in a DJ mix with timing and metadata.
    """

    def __init__(
        self,
        mix_filepath: str = "",
        mix_title: str = "",
        mix_artist: str = "",
    ) -> None:
        """Initialize cue sheet.

        Args:
            mix_filepath: Path to the mix audio file
            mix_title: Title of the mix
            mix_artist: Artist/DJ name
        """
        self.mix_filepath = mix_filepath
        self.mix_title = mix_title
        self.mix_artist = mix_artist
        self.entries: list[CueEntry] = []

    def add_entry(self, entry: CueEntry) -> None:
        """Add a cue entry and maintain time-sorted order.

        Args:
            entry: Cue entry to add
        """
        self.entries.append(entry)
        self.sort_by_time()

    def remove_entry(self, index: int) -> None:
        """Remove entry at index.

        Args:
            index: Index of entry to remove

        Raises:
            IndexError: If index is out of bounds
        """
        if 0 <= index < len(self.entries):
            self.entries.pop(index)

    def update_timestamp(self, index: int, new_time_ms: int) -> None:
        """Update timestamp of entry and re-sort.

        Args:
            index: Index of entry to update
            new_time_ms: New timestamp in milliseconds (rounded to second)

        Raises:
            IndexError: If index is out of bounds
        """
        if 0 <= index < len(self.entries):
            self.entries[index].start_time_ms = round(new_time_ms / 1000) * 1000
            self.sort_by_time()

    def update_duration(self, index: int, duration_ms: int) -> None:
        """Update duration of entry.

        Args:
            index: Index of entry to update
            duration_ms: New duration in milliseconds (rounded to second)
        """
        if 0 <= index < len(self.entries):
            self.entries[index].duration_ms = round(duration_ms / 1000) * 1000

    def set_status(self, index: int, status: EntryStatus) -> None:
        """Update status of entry.

        Args:
            index: Index of entry to update
            status: New status

        Raises:
            IndexError: If index is out of bounds
        """
        if 0 <= index < len(self.entries):
            self.entries[index].status = status

    def get_confirmed_entries(self) -> list[CueEntry]:
        """Get all entries for export, sorted by time.

        Returns:
            List of all entries sorted by time
        """
        return list(self.entries)

    def sort_by_time(self) -> None:
        """Sort entries by start_time_ms."""
        self.entries.sort(key=lambda e: e.start_time_ms)

    def clear(self) -> None:
        """Clear all entries."""
        self.entries.clear()
