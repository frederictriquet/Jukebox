"""Constants for the Cue Maker plugin."""

from enum import IntEnum


class TableColumn(IntEnum):
    """Column indices for the cue table."""

    TIME = 0
    ARTIST = 1
    TITLE = 2
    CONFIDENCE = 3
    DURATION = 4
    STATUS = 5
    ACTIONS = 6


# Column headers
COLUMN_HEADERS = [
    "Time",
    "Artist",
    "Title",
    "Confidence",
    "Duration",
    "Status",
    "Actions",
]

# Status colors (Qt stylesheet compatible)
STATUS_COLORS = {
    "pending": "#FFA500",  # Orange
    "confirmed": "#2d7a2d",  # Green
    "rejected": "#7a2d2d",  # Red
    "manual": "#2d5a7a",  # Blue
}

# Waveform marker colors
MARKER_COLORS = {
    "pending": "#FFD700",  # Gold
    "confirmed": "#00FF00",  # Green
    "rejected": "#FF0000",  # Red
    "manual": "#00BFFF",  # Deep Sky Blue
}
