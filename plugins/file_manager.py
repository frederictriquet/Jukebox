"""File manager plugin for moving/renaming/deleting tracks."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QPushButton

from jukebox.core.config import FileManagerDestinationConfig
from jukebox.core.event_bus import Events
from jukebox.core.mode_manager import AppMode
from jukebox.core.settings_sync_mixin import SettingsSyncMixin, SyncedJsonList, SyncedSetting
from jukebox.core.shortcut_mixin import ShortcutMixin

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol


class FileManagerPlugin(SettingsSyncMixin, ShortcutMixin):
    """Manage files: move, rename, and delete tracks."""

    name = "file_manager"
    version = "1.0.0"
    description = "File management with keyboard shortcuts"
    modes = [AppMode.CURATING.value, AppMode.JUKEBOX.value]  # Active in both modes

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol = None  # type: ignore[assignment]
        self.current_track_id: int | None = None
        self.current_filepath: Path | None = None
        self.remove_button: QPushButton | None = None
        self._init_shortcut_mixin()

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to track loaded event
        context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)
        # Subscribe to settings changes to reload shortcuts
        context.subscribe(Events.PLUGIN_SETTINGS_CHANGED, self._on_settings_changed)

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register UI elements."""
        main_window = self.context.app
        # Couplage tolérant : si la fenêtre principale n'expose pas de barre de
        # controls (refactor, mode headless…), on n'ajoute simplement pas le bouton.
        controls = getattr(main_window, "controls", None)
        if controls is None:
            logging.warning("[File Manager] main_window.controls absent, bouton Remove non ajouté")
            return

        if controls.layout():
            # Add remove button for jukebox mode (removes from library but keeps file)
            self.remove_button = QPushButton("Remove")
            self.remove_button.setToolTip("Remove track from library (keeps file on disk)")
            self.remove_button.clicked.connect(self._remove_from_library)
            self.remove_button.setMaximumWidth(70)

            # Set initial visibility based on current mode
            current_mode = self.context.config.ui.mode
            self.remove_button.setVisible(current_mode == AppMode.JUKEBOX.value)

            layout = controls.layout()
            # Find the stretch item and insert button before it
            stretch_index = -1
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item and item.spacerItem():
                    stretch_index = i
                    break

            # If stretch found, insert before it; otherwise append
            if stretch_index >= 0:
                ui_builder.insert_widget_in_layout(layout, stretch_index, self.remove_button)
            else:
                layout.addWidget(self.remove_button)

    def _register_plugin_shortcuts(self) -> None:
        """Register file management shortcuts."""
        # Get file manager config
        file_config = self.context.config.file_manager

        # Register destination shortcuts (move + rename)
        for dest_config in file_config.destinations:
            shortcut = self.shortcut_manager.register(
                dest_config.key,
                lambda d=dest_config: self._move_to_destination(d),
                plugin_name=self.name,
            )
            self.shortcuts.append(shortcut)

        # Register trash shortcut (move without rename)
        if file_config.trash_directory:
            shortcut = self.shortcut_manager.register(
                file_config.trash_key,
                self._move_to_trash,
                plugin_name=self.name,
            )
            self.shortcuts.append(shortcut)

    def _on_track_loaded(self, track_id: int) -> None:
        """Load current track when track loads."""
        self.current_track_id = track_id

        # Get filepath from database
        track = self.context.database.tracks.get_by_id(track_id)
        self.current_filepath = Path(track["filepath"]) if track else None
        logging.debug(
            "[File Manager] Track loaded: id=%s, filepath=%s", track_id, self.current_filepath
        )

    _synced_settings = [
        SyncedSetting("trash_directory", str),
        SyncedSetting("trash_key", str),
    ]
    _synced_json_lists = [
        SyncedJsonList("destinations", "destinations", FileManagerDestinationConfig),
    ]

    def _reload_plugin_config(self) -> None:
        """Reload file_manager config from database."""
        self._sync_settings_from_db()

    def _move_to_destination(self, dest_config: Any) -> None:
        """Move current track to destination and rename it 'artist - title.extension'."""
        if not self.current_track_id or not self.current_filepath:
            logging.warning("[File Manager] No track loaded")
            return

        if not self.current_filepath.exists():
            logging.error("Source file does not exist: %s", self.current_filepath)
            self.context.emit(Events.STATUS_MESSAGE, message="Error: File not found")
            return

        # Get track metadata for renaming
        track = self.context.database.tracks.get_by_id(self.current_track_id)

        if not track:
            logging.error("Track %s not found in database", self.current_track_id)
            return

        artist = track["artist"]
        title = track["title"]

        # Prevent copying if artist or title is unknown
        if not artist or not title:
            missing = []
            if not artist:
                missing.append("artist")
            if not title:
                missing.append("title")
            error_msg = f"Cannot copy: missing {' and '.join(missing)}"
            logging.warning(
                "[File Manager] %s for track %s", error_msg, self.current_track_id
            )
            self.context.emit(Events.STATUS_MESSAGE, message=error_msg)
            return

        extension = self.current_filepath.suffix

        # Build new filename: "artist - title.extension"
        new_filename = f"{artist} - {title}{extension}"
        # Sanitize filename (remove invalid characters)
        new_filename = self._sanitize_filename(new_filename)

        # Build destination path
        dest_dir = Path(dest_config.path).expanduser()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / new_filename

        # Check if destination already exists
        if dest_path.exists():
            logging.error("Destination file already exists: %s", dest_path)
            self.context.emit(
                Events.STATUS_MESSAGE, message=f"Error: File already exists in {dest_config.name}"
            )
            return

        try:
            # Save filepath before copying
            old_filepath = self.current_filepath
            old_track_id = self.current_track_id

            # Copy and rename file to destination
            shutil.copy2(str(self.current_filepath), str(dest_path))
            logging.info("Copied %s -> %s", old_filepath, dest_path)

            # M27 : vérifier l'intégrité de la copie avant de supprimer la source.
            # Sans ce contrôle, une copie tronquée suivie d'un unlink détruit les données.
            source_size = old_filepath.stat().st_size
            dest_size = dest_path.stat().st_size
            if source_size != dest_size:
                logging.error(
                    "Copy integrity check failed: source=%s bytes, "
                    "dest=%s bytes. Aborting before deletion.",
                    source_size,
                    dest_size,
                )
                # Nettoyer la copie corrompue, ne pas toucher à la source
                dest_path.unlink(missing_ok=True)
                self.context.emit(
                    Events.STATUS_MESSAGE, message="Error: copy integrity check failed"
                )
                return

            # Delete from database (waveform and analysis removed by CASCADE)
            self.context.database.tracks.delete(old_track_id)
            logging.info("Deleted track %s from database", old_track_id)

            # Delete original file from disk
            old_filepath.unlink()
            logging.info("Deleted original file: %s", old_filepath)

            # Reset current track BEFORE emitting event
            # (because event handlers might load a new track)
            self.current_track_id = None
            self.current_filepath = None

            # Remove from track list and play next (via event)
            self.context.emit(Events.TRACK_DELETED, filepath=old_filepath)

            # Show status message
            self.context.emit(
                Events.STATUS_MESSAGE,
                message=f"Copied to {dest_config.name}: {new_filename}",
            )

        except Exception as e:
            logging.error("Failed to move file: %s", e, exc_info=True)
            self.context.emit(Events.STATUS_MESSAGE, message=f"Error moving file: {e}")

    def _move_to_trash(self) -> None:
        """Move current track to trash, remove from database and tracklist, play next."""
        if not self.current_track_id or not self.current_filepath:
            logging.warning("[File Manager] No track loaded")
            return

        if not self.current_filepath.exists():
            logging.error("Source file does not exist: %s", self.current_filepath)
            self.context.emit(Events.STATUS_MESSAGE, message="Error: File not found")
            return

        # Get trash directory from config
        trash_dir = Path(self.context.config.file_manager.trash_directory).expanduser()
        trash_dir.mkdir(parents=True, exist_ok=True)

        # Keep original filename
        dest_path = trash_dir / self.current_filepath.name

        # Check if destination already exists
        if dest_path.exists():
            logging.error("File already exists in trash: %s", dest_path)
            self.context.emit(Events.STATUS_MESSAGE, message="Error: File already exists in trash")
            return

        try:
            # Save filepath before moving
            old_filepath = self.current_filepath

            # Move file to trash
            shutil.move(str(self.current_filepath), str(dest_path))
            logging.info("Moved to trash: %s -> %s", old_filepath, dest_path)

            # Delete from database (and waveform_cache via CASCADE)
            track_id = self.current_track_id
            self.context.database.tracks.delete(track_id)
            logging.info("Deleted track %s from database", track_id)

            # Reset current track BEFORE emitting event
            # (because event handlers might load a new track)
            self.current_track_id = None
            self.current_filepath = None

            # Remove from track list and play next (via event)
            self.context.emit(Events.TRACK_DELETED, filepath=old_filepath)

            # Show status message
            self.context.emit(
                Events.STATUS_MESSAGE,
                message=f"Deleted: {old_filepath.name}",
            )

        except Exception as e:
            logging.error("Failed to move file to trash: %s", e, exc_info=True)
            self.context.emit(Events.STATUS_MESSAGE, message=f"Error moving to trash: {e}")

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename by removing invalid characters."""
        # Replace invalid characters with underscore
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename

    def _remove_from_library(self) -> None:
        """Remove current track from library (DB only, keeps file on disk).

        Used in jukebox mode to remove a track without deleting the file.
        """
        if not self.current_track_id or not self.current_filepath:
            logging.warning("[File Manager] No track loaded")
            return

        try:
            # Save filepath before removing
            old_filepath = self.current_filepath
            filename = old_filepath.name
            track_id = self.current_track_id

            # Delete from database (and waveform_cache via CASCADE)
            self.context.database.tracks.delete(track_id)
            logging.info(
                "Removed track %s from database (file kept: %s)", track_id, old_filepath
            )

            # Reset current track BEFORE emitting event
            self.current_track_id = None
            self.current_filepath = None

            # Remove from track list and play next (via event)
            self.context.emit(Events.TRACK_DELETED, filepath=old_filepath)

            # Show status message
            self.context.emit(
                Events.STATUS_MESSAGE,
                message=f"Removed from library: {filename}",
            )

        except Exception as e:
            logging.error("Failed to remove track from library: %s", e, exc_info=True)
            self.context.emit(Events.STATUS_MESSAGE, message=f"Error removing track: {e}")

    def activate(self, mode: str) -> None:
        """Activate plugin for this mode."""
        if mode == AppMode.CURATING.value:
            # Enable shortcuts for curating mode
            self._activate_shortcuts()
            # Hide remove button in curating mode
            if self.remove_button:
                self.remove_button.setVisible(False)
        elif mode == AppMode.JUKEBOX.value:
            # Disable curating shortcuts in jukebox mode
            self._deactivate_shortcuts()
            # Show remove button in jukebox mode
            if self.remove_button:
                self.remove_button.setVisible(True)
        logging.debug("[File Manager] Activated for %s mode", mode)

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for this mode."""
        if mode == AppMode.CURATING.value:
            # Disable shortcuts when leaving curating mode
            self._deactivate_shortcuts()
        elif mode == AppMode.JUKEBOX.value:
            # Hide remove button when leaving jukebox mode
            if self.remove_button:
                self.remove_button.setVisible(False)
        logging.debug("[File Manager] Deactivated for %s mode", mode)

    def shutdown(self) -> None:
        """Cleanup on application exit. No cleanup needed for this plugin."""
        ...

    def get_settings_schema(self) -> dict[str, Any]:
        """Return settings schema for configuration UI.

        Returns:
            Dict mapping setting keys to their configuration
        """
        return {
            "destinations": {
                "label": "Destinations",
                "type": "list",
                "item_schema": {
                    "name": {"label": "Name", "type": "string"},
                    "path": {"label": "Path", "type": "directory"},
                    "key": {"label": "Shortcut", "type": "shortcut"},
                },
                "default": [
                    {"name": dest.name, "path": dest.path, "key": dest.key}
                    for dest in self.context.config.file_manager.destinations
                ],
            },
            "trash_directory": {
                "label": "Trash Directory",
                "type": "directory",
                "default": self.context.config.file_manager.trash_directory,
            },
            "trash_key": {
                "label": "Trash Shortcut",
                "type": "shortcut",
                "default": self.context.config.file_manager.trash_key,
            },
        }
