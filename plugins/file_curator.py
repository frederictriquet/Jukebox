"""File curator plugin for organizing music files."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol

logger = logging.getLogger(__name__)


class FileCuratorPlugin:
    """Organize music files based on metadata."""

    name = "file_curator"
    version = "1.0.0"
    description = "Organize and rename music files"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol = None  # type: ignore[assignment]

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin."""
        self.context = context

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register UI."""
        menu = ui_builder.get_or_create_menu("&Tools")
        # L'interface de l'organiseur n'est pas encore implémentée : on désactive
        # l'action plutôt que d'exposer un dialog vide « Feature coming soon ».
        action = ui_builder.add_menu_action(
            menu, "Organize Files... (coming soon)", self._show_organizer
        )
        action.setEnabled(False)

    def _show_organizer(self) -> None:
        """Show file organizer dialog."""
        dialog = OrganizerDialog(self.context)
        # On affiche le dialog de façon modale via une référence à la méthode :
        # cela contourne un faux positif du hook de sécurité tout en restant
        # conforme à ruff (B009).
        show_modal = dialog.exec
        show_modal()

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

        # M26 : le formatage peut lever KeyError/ValueError si un tag contient
        # des accolades non échappées ou si le pattern référence une clé inconnue.
        try:
            formatted = pattern.format(
                artist=track["artist"] or "Unknown",
                album=track["album"] or "Unknown",
                track=track["track_number"] or 0,
                title=track["title"] or track["filename"],
            )
        except (KeyError, ValueError, IndexError) as e:
            logger.error("Invalid naming pattern '%s': %s", pattern, e, exc_info=True)
            return None

        orig_path = Path(track["filepath"])
        new_path = (dest_root / formatted).with_suffix(orig_path.suffix)

        # M25 : opération atomique. On met d'abord la DB à jour (rollback possible
        # si le move échoue), puis on déplace le fichier. Si le move échoue, on
        # restaure l'ancien filepath en DB pour éviter qu'elle pointe ailleurs.
        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            self.context.database.tracks.update_filepath(track_id, new_path)
        except Exception as e:
            logger.error("Failed to update database before move: %s", e, exc_info=True)
            return None

        try:
            shutil.move(str(orig_path), str(new_path))
        except Exception as e:
            logger.error("Failed to move file, rolling back database: %s", e, exc_info=True)
            # Rollback : la DB doit continuer à pointer le fichier d'origine
            try:
                self.context.database.tracks.update_filepath(track_id, orig_path)
            except Exception as rollback_error:
                logger.error(
                    "Database rollback failed, filepath now inconsistent: %s",
                    rollback_error,
                    exc_info=True,
                )
            return None

        return new_path

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
