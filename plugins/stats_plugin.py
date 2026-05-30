"""Statistics plugin."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol

logger = logging.getLogger(__name__)


class StatsPlugin:
    """Library statistics plugin."""

    name = "stats"
    version = "1.0.0"
    description = "Show library statistics"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol = None  # type: ignore[assignment]

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin."""
        self.context = context

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register UI."""
        menu = ui_builder.get_or_create_menu("&Library")
        ui_builder.add_menu_action(menu, "Statistics...", self._show_stats)

    def _show_stats(self) -> None:
        """Show statistics."""
        db = self.context.database

        try:
            stats = db.tracks.get_stats()
            total = stats["total_tracks"]
            duration = stats["total_duration_seconds"]
        except Exception:
            logger.error("[Stats] Échec de la lecture des statistiques en base", exc_info=True)
            QMessageBox.warning(
                None,
                "Library Statistics",
                "Impossible de lire les statistiques : la base de données est inaccessible.",
            )
            return

        hours = int(duration / 3600)
        minutes = int((duration % 3600) / 60)

        msg = f"Total Tracks: {total}\nTotal Duration: {hours}h {minutes}m"
        QMessageBox.information(None, "Library Statistics", msg)

    def shutdown(self) -> None:
        """Cleanup on application exit. No cleanup needed for this plugin."""
        ...
