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
    ACTIONS = 6


# Column headers
COLUMN_HEADERS = [
    "",
    "Time",
    "Artist",
    "Title",
    "Confidence",
    "Duration",
    "",
]

# Waveform marker colors
MARKER_COLORS = {
    "pending": "#FFD700",  # Gold
    "confirmed": "#00FF00",  # Green
    "rejected": "#FF0000",  # Red
    "manual": "#00BFFF",  # Deep Sky Blue
}

# Status indicators for entries
INDICATOR_OVERLAP = "⚠️"
INDICATOR_GAP = "\u2194"  # ↔ double arrow, gap between entries

# Action icons for the actions column
ACTION_DELETE = "\u2715"  # ✕
ACTION_INSERT = "+"
ACTION_SNAP_PREV = "\u23ee"  # ⏮
ACTION_SNAP_NEXT = "\u23ed"  # ⏭
