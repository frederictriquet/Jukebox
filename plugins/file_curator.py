"""File curator plugin for organizing music files."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol


class FileCuratorPlugin:
    """Organize music files based on metadata."""

    name = "file_curator"
    version = "1.0.0"
    description = "Organize and rename music files"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol | None = None

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin."""
        self.context = context

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register UI."""
        menu = ui_builder.get_or_create_menu("&Tools")
        ui_builder.add_menu_action(menu, "Organize Files...", self._show_organizer)

    def _show_organizer(self) -> None:
        """Show file organizer dialog."""
        dialog = OrganizerDialog(self.context)
        dialog.exec()

    def organize_file(
        self,
        track_id: int,
        dest_root: Path,
        pattern: str = "{artist}/{album}/{track:02d} - {title}",
    ) -> Path | None:
        """Organize a single file.

        Args:
            track_id: Track ID
            dest_root: Destination root directory
            pattern: Naming pattern

        Returns:
            New path or None if failed
        """
        track = self.context.database.tracks.get_by_id(track_id)
        if not track:
            return None

        # Format new path
        try:
            new_path = dest_root / pattern.format(
                artist=track["artist"] or "Unknown",
                album=track["album"] or "Unknown",
                track=track["track_number"] or 0,
                title=track["title"] or track["filename"],
            )

            orig_path = Path(track["filepath"])
            new_path = new_path.with_suffix(orig_path.suffix)

            # Create directories
            new_path.parent.mkdir(parents=True, exist_ok=True)

            # Move file
            shutil.move(str(orig_path), str(new_path))

            # Update database
            self.context.database.tracks.update_filepath(track_id, new_path)

            return new_path

        except Exception as e:
            import logging

            logging.error(f"Failed to organize file: {e}")
            return None

    def shutdown(self) -> None:
        """Cleanup on application exit. No cleanup needed for this plugin."""
        ...


class OrganizerDialog(QDialog):
    """Dialog for file organization."""

    def __init__(self, context: PluginContextProtocol):
        """Initialize dialog."""
        super().__init__()
        self.context = context
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI."""
        self.setWindowTitle("Organize Files")
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Pattern: {artist}/{album}/{track:02d} - {title}"))
        layout.addWidget(QLabel("Feature coming soon..."))

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self.setLayout(layout)
