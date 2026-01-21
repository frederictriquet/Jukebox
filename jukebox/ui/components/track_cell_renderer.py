"""Cell renderer for track list columns."""

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap


class CellRenderer:
    """Dispatch rendering to column-specific stylers."""

    def __init__(self, columns: list[str], genre_names: dict[str, str] | None = None):
        """Initialize renderer with column names.

        Args:
            columns: List of column names
            genre_names: Mapping of genre codes to full names (optional)
        """
        self.columns = columns
        self.stylers = {
            "waveform": WaveformStyler(),
            "stats": StatsStyler(),
            "filename": FilenameStyler(),
            "genre": GenreStyler(genre_names or {}),
            "rating": RatingStyler(),
            "duration": DurationStyler(),
        }

    def get_style(self, track: dict[str, Any], column: int, role: int) -> Any:
        """Get styled value for a cell.

        Args:
            track: Track data dict
            column: Column index
            role: Qt role (DisplayRole, ForegroundRole, etc.)

        Returns:
            Styled value for the role
        """
        if column >= len(self.columns):
            return None

        column_name = self.columns[column]
        styler = self.stylers.get(column_name)

        if styler:
            data = track.get(column_name)
            return styler.get_style(data, role, track)

        # Default: just return raw data
        if role == Qt.ItemDataRole.DisplayRole:
            return str(track.get(column_name, ""))

        return None


class Styler:
    """Base styler for a column."""

    def get_style(self, data: Any, role: int, track: dict[str, Any]) -> Any:
        """Get styled value for a role."""
        if role == Qt.ItemDataRole.DisplayRole:
            return self.display(data, track)
        elif role == Qt.ItemDataRole.ToolTipRole:
            return self.tooltip(data, track)
        elif role == Qt.ItemDataRole.ForegroundRole:
            return self.foreground(data, track)
        elif role == Qt.ItemDataRole.BackgroundRole:
            return self.background(data, track)
        elif role == Qt.ItemDataRole.DecorationRole:
            return self.decoration(data, track)
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return self.alignment(data, track)
        return None

    def display(self, data: Any, track: dict[str, Any]) -> str:
        """Display text."""
        return str(data) if data is not None else ""

    def tooltip(self, data: Any, track: dict[str, Any]) -> str | None:
        """Tooltip text."""
        return None

    def foreground(self, data: Any, track: dict[str, Any]) -> QColor | None:
        """Text color."""
        return None  # Use theme default

    def background(self, data: Any, track: dict[str, Any]) -> QColor | None:
        """Background color."""
        return None  # Use theme default

    def decoration(self, data: Any, track: dict[str, Any]) -> QColor | None:
        """Decoration (color indicator)."""
        return None

    def alignment(self, data: Any, track: dict[str, Any]) -> Qt.AlignmentFlag | None:
        """Text alignment."""
        return None  # Use default


class FilenameStyler(Styler):
    """Styler for filename column."""

    def display(self, data: Any, track: dict[str, Any]) -> str:
        """Display artist - title or filename."""
        artist = track.get("artist", "")
        title = track.get("title", "")

        if artist and title:
            return f"{artist} - {title}"
        elif title:
            return title
        else:
            return track["filepath"].name

    def tooltip(self, data: Any, track: dict[str, Any]) -> str:
        """Show full path."""
        return str(track["filepath"])


class GenreStyler(Styler):
    """Styler for genre column."""

    # Pattern to validate genre format (from PyQT project)
    # Note: *0 is not allowed, only *1 to *5
    GENRE_PATTERN = r"^([A-Z])(-[A-Z])*(-\*[1-5])?$"

    def __init__(self, genre_names: dict[str, str]):
        """Initialize with genre name mapping.

        Args:
            genre_names: Mapping of genre codes to full names
        """
        self.genre_names = genre_names

    def _is_valid_genre(self, genre: str) -> bool:
        """Check if genre matches the expected pattern."""
        import re

        return bool(re.match(self.GENRE_PATTERN, genre))

    def display(self, data: Any, track: dict[str, Any]) -> str:
        """Display genre codes without rating."""
        if not data:
            return ""

        # Validate genre format - show first chars if invalid
        if not self._is_valid_genre(data):
            # Show first 20 characters of invalid genre
            return data[:20] if len(data) > 20 else data

        # Parse genre (format: "C-D-P-*3")
        parts = data.split("-") if data else []
        codes = [p for p in parts if not p.startswith("*")]
        return "-".join(codes) if codes else ""

    def tooltip(self, data: Any, track: dict[str, Any]) -> str | None:
        """Show full genre names."""
        if not data:
            return None

        # Parse genre codes
        parts = data.split("-") if data else []
        codes = sorted([p for p in parts if not p.startswith("*")])

        # Map codes to full names
        full_names = [self.genre_names.get(code, code) for code in codes]

        return " - ".join(full_names) if full_names else None

    def decoration(self, data: Any, track: dict[str, Any]) -> QColor | None:
        """Red if no genre or invalid genre."""
        if not data:
            return QColor(Qt.GlobalColor.red)
        # Also show red for invalid genres
        if not self._is_valid_genre(data):
            return QColor(Qt.GlobalColor.red)
        return None


class RatingStyler(Styler):
    """Styler for rating column."""

    def display(self, data: Any, track: dict[str, Any]) -> str:
        """Display stars."""
        # Extract rating from genre (format: "C-D-*3")
        genre = track.get("genre", "")
        if not genre:
            return ""

        parts = genre.split("-")
        rating_parts = [p for p in parts if p.startswith("*")]

        if rating_parts:
            # Extract number after *
            rating_str = rating_parts[0][1:]  # Remove *
            try:
                rating = int(rating_str)
                return "* " * rating
            except ValueError:
                return ""

        return ""

    def decoration(self, data: Any, track: dict[str, Any]) -> QColor | None:
        """Red if no rating."""
        genre = track.get("genre", "")
        if not genre or "*" not in genre:
            return QColor(Qt.GlobalColor.red)
        return None


class DurationStyler(Styler):
    """Styler for duration column."""

    def display(self, data: Any, track: dict[str, Any]) -> str:
        """Display duration as MM:SS."""
        duration_seconds = track.get("duration_seconds")
        if duration_seconds is None:
            return ""

        minutes = int(duration_seconds // 60)
        seconds = int(duration_seconds % 60)
        return f"{minutes}:{seconds:02d}"

    def alignment(self, data: Any, track: dict[str, Any]) -> Qt.AlignmentFlag:
        """Right-align duration."""
        return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight


class WaveformStyler(Styler):
    """Styler for waveform column (mini waveform preview)."""

    # Cache for rendered waveforms (avoid re-rendering on every paint)
    _cache: dict[int, QPixmap] = {}

    def display(self, data: Any, track: dict[str, Any]) -> str:
        """Display simple indicator if no waveform."""
        waveform_data = track.get("waveform_data")
        if not waveform_data:
            return "--"  # No waveform yet
        return ""  # Waveform will be shown as pixmap

    def background(self, data: Any, track: dict[str, Any]) -> QColor:
        """Black background for waveform."""
        return QColor(Qt.GlobalColor.black)

    def decoration(self, data: Any, track: dict[str, Any]) -> QPixmap | None:
        """Generate mini waveform as pixmap (not icon)."""
        # Check if waveform data exists
        waveform_data = track.get("waveform_data")
        if not waveform_data:
            return None

        # Cache key based on filepath hash
        cache_key = hash(str(track.get("filepath")))
        if cache_key in WaveformStyler._cache:
            return WaveformStyler._cache[cache_key]

        # Create a mini waveform pixmap (200x16 for compact display)
        width, height = 200, 16
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.black)  # Black background

        painter = QPainter(pixmap)

        # Draw waveform (3 stacked bands)
        import numpy as np

        bass = waveform_data.get("bass", np.array([]))
        mid = waveform_data.get("mid", np.array([]))
        treble = waveform_data.get("treble", np.array([]))

        if len(bass) > 0 and len(mid) > 0 and len(treble) > 0:
            # Downsample to fit width
            step = max(1, len(bass) // width)
            bass_samples = bass[::step][:width]
            mid_samples = mid[::step][:width]
            treble_samples = treble[::step][:width]

            # Stack bands (cumulative)
            for i in range(min(len(bass_samples), width)):
                x = i
                y_bottom = height

                # Calculate cumulative heights
                bass_h = int(bass_samples[i] * height)
                mid_h = int((bass_samples[i] + mid_samples[i]) * height)
                treble_h = int((bass_samples[i] + mid_samples[i] + treble_samples[i]) * height)

                # Draw treble (white) - full height
                if treble_h > 0:
                    painter.fillRect(x, y_bottom - treble_h, 1, treble_h, QColor("#FFFFFF"))

                # Draw mid (green) - covers bass+mid
                if mid_h > 0:
                    painter.fillRect(x, y_bottom - mid_h, 1, mid_h, QColor("#00FF00"))

                # Draw bass (blue) - bottom layer
                if bass_h > 0:
                    painter.fillRect(x, y_bottom - bass_h, 1, bass_h, QColor("#0066FF"))

        painter.end()

        # Cache the result
        WaveformStyler._cache[cache_key] = pixmap

        return pixmap


class StatsStyler(Styler):
    """Styler for stats column (shows if audio analysis exists)."""

    def display(self, data: Any, track: dict[str, Any]) -> str:
        """Display checkmark if stats exist, dash otherwise."""
        has_stats = track.get("has_stats", False)
        return "✓" if has_stats else "-"

    def tooltip(self, data: Any, track: dict[str, Any]) -> str | None:
        """Show tooltip explaining the stats status."""
        has_stats = track.get("has_stats", False)
        if has_stats:
            return "Audio analysis complete"
        return "No audio analysis"

    def foreground(self, data: Any, track: dict[str, Any]) -> QColor | None:
        """Green if stats exist, gray otherwise."""
        has_stats = track.get("has_stats", False)
        if has_stats:
            return QColor("#00FF00")  # Green
        return QColor("#666666")  # Gray

    def alignment(self, data: Any, track: dict[str, Any]) -> Qt.AlignmentFlag:
        """Center-align the icon."""
        return Qt.AlignmentFlag.AlignCenter
