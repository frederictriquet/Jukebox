"""Constants for the Cue Maker plugin."""

from enum import IntEnum


class TableColumn(IntEnum):
    """Column indices for the cue table."""

    OVERLAP = 0
    TIME = 1
    ARTIST = 2
    TITLE = 3
    CONFIDENCE = 4
    DURATION = 5


# Column headers
COLUMN_HEADERS = [
    "",
    "Time",
    "Artist",
    "Title",
    "Confidence",
    "Duration",
]

# Waveform marker colors
MARKER_COLORS = {
    "pending": "#FFD700",  # Gold
    "confirmed": "#00FF00",  # Green
    "rejected": "#FF0000",  # Red
    "manual": "#00BFFF",  # Deep Sky Blue
}
