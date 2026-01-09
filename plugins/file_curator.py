"""File curator plugin for organizing music files."""

import shutil
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout


class FileCuratorPlugin:
    """Organize music files based on metadata."""

    name = "file_curator"
    version = "1.0.0"
    description = "Organize and rename music files"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

    def register_ui(self, ui_builder: Any) -> None:
        """Register UI."""
        menu = ui_builder.add_menu("&Tools")
        ui_builder.add_menu_action(menu, "Organize Files...", self._show_organizer)

    def _show_organizer(self) -> None:
        """Show file organizer dialog."""
        dialog = OrganizerDialog(self.context)
        dialog.exec()

    def organize_file(
        self, track_id: int, dest_root: Path, pattern: str = "{artist}/{album}/{track:02d} - {title}"
    ) -> Path | None:
        """Organize a single file.

        Args:
            track_id: Track ID
            dest_root: Destination root directory
            pattern: Naming pattern

        Returns:
            New path or None if failed
        """
        track = self.context.database.get_track_by_id(track_id)
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
            self.context.database.conn.execute(
                "UPDATE tracks SET filepath = ?, filename = ? WHERE id = ?",
                (str(new_path), new_path.name, track_id),
            )
            self.context.database.conn.commit()

            return new_path

        except Exception as e:
            import logging

            logging.error(f"Failed to organize file: {e}")
            return None

    def shutdown(self) -> None:
        """Cleanup."""
        pass


class OrganizerDialog(QDialog):
    """Dialog for file organization."""

    def __init__(self, context: Any):
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
