"""Statistics plugin."""

from typing import Any

from PySide6.QtWidgets import QMessageBox


class StatsPlugin:
    """Library statistics plugin."""

    name = "stats"
    version = "1.0.0"
    description = "Show library statistics"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

    def register_ui(self, ui_builder: Any) -> None:
        """Register UI."""
        menu = ui_builder.get_or_create_menu("&Library")
        ui_builder.add_menu_action(menu, "Statistics...", self._show_stats)

    def _show_stats(self) -> None:
        """Show statistics."""
        db = self.context.database

        total = db.conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        duration = db.conn.execute("SELECT SUM(duration_seconds) FROM tracks").fetchone()[0] or 0

        hours = int(duration / 3600)
        minutes = int((duration % 3600) / 60)

        msg = f"Total Tracks: {total}\nTotal Duration: {hours}h {minutes}m"
        QMessageBox.information(None, "Library Statistics", msg)

    def shutdown(self) -> None:
        """Cleanup on application exit. No cleanup needed for this plugin."""
        ...
