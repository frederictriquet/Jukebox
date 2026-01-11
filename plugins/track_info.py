"""Track info display plugin."""

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class TrackInfoPlugin:
    """Display current track information."""

    name = "track_info"
    version = "1.0.0"
    description = "Display current track info (position, duration, bitrate, size)"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None
        self.info_widget: TrackInfoWidget | None = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to track events
        from jukebox.core.event_bus import Events

        context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)
        context.subscribe("position_update", self._on_position_update)

    def register_ui(self, ui_builder: Any) -> None:
        """Register track info widget."""
        self.info_widget = TrackInfoWidget()

        # Get player controls and insert info widget between stop and volume
        main_window = self.context.app
        controls = main_window.controls
        layout = controls.layout()
        # Insert after stop button (index 3) and before volume slider
        # Layout: play (0), pause (1), stop (2), spacer (3), volume label (4), volume (5)
        # We want to insert at index 4 (before volume label)
        ui_builder.insert_widget_in_layout(layout, 4, self.info_widget)

    def _on_track_loaded(self, track_id: int) -> None:
        """Handle track loaded event."""
        if not self.info_widget:
            return

        # Get track info from database
        track = self.context.database.conn.execute(
            """SELECT title, artist, duration_seconds, bitrate, file_size
               FROM tracks WHERE id = ?""",
            (track_id,),
        ).fetchone()

        if track:
            duration_str = self._format_duration(track["duration_seconds"] or 0)
            bitrate_str = f"{track['bitrate'] // 1000}kbps" if track["bitrate"] else "N/A"
            size_str = self._format_size(track["file_size"] or 0)

            self.info_widget.set_track_info(
                duration=duration_str, bitrate=bitrate_str, filesize=size_str
            )

    def _on_position_update(self, position: float) -> None:
        """Handle position update."""
        if not self.info_widget:
            return

        # Get current track duration
        current_file = self.context.player.current_file
        if current_file:
            track = self.context.database.conn.execute(
                "SELECT duration_seconds FROM tracks WHERE filepath = ?",
                (str(current_file),),
            ).fetchone()

            if track and track["duration_seconds"]:
                current_time = position * track["duration_seconds"]
                self.info_widget.set_position(self._format_duration(current_time))

    def _format_duration(self, seconds: float) -> str:
        """Format duration as MM:SS."""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def _format_size(self, bytes_size: int) -> str:
        """Format file size."""
        if bytes_size < 1024:
            return f"{bytes_size}B"
        elif bytes_size < 1024 * 1024:
            return f"{bytes_size / 1024:.1f}KB"
        else:
            return f"{bytes_size / (1024 * 1024):.1f}MB"

    def register_shortcuts(self, shortcut_manager: Any) -> None:
        """Register keyboard shortcuts."""
        pass

    def shutdown(self) -> None:
        """Cleanup."""
        pass


class TrackInfoWidget(QWidget):
    """Widget to display track information."""

    def __init__(self) -> None:
        """Initialize widget."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI."""
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(15)

        # Position / Duration
        self.position_label = QLabel("00:00")
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.position_label)

        layout.addWidget(QLabel("/"))

        self.duration_label = QLabel("00:00")
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.duration_label)

        # Separator
        layout.addWidget(QLabel("|"))

        # Bitrate
        self.bitrate_label = QLabel("N/A")
        self.bitrate_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.bitrate_label)

        # Separator
        layout.addWidget(QLabel("|"))

        # File size
        self.filesize_label = QLabel("N/A")
        self.filesize_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.filesize_label)

        self.setLayout(layout)

    def set_track_info(self, duration: str, bitrate: str, filesize: str) -> None:
        """Set track metadata info."""
        self.duration_label.setText(duration)
        self.bitrate_label.setText(bitrate)
        self.filesize_label.setText(filesize)

    def set_position(self, position: str) -> None:
        """Set current position."""
        self.position_label.setText(position)
