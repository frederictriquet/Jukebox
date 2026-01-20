"""File manager plugin for moving/renaming/deleting tracks."""

import logging
import shutil
from pathlib import Path
from typing import Any

from jukebox.core.event_bus import Events


class FileManagerPlugin:
    """Manage files: move, rename, and delete tracks."""

    name = "file_manager"
    version = "1.0.0"
    description = "File management with keyboard shortcuts"
    modes = ["curating"]  # Only active in curating mode

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None
        self.current_track_id: int | None = None
        self.current_filepath: Path | None = None
        self.shortcuts: list[Any] = []
        self.shortcut_manager: Any = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to track loaded event
        context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)
        # Subscribe to settings changes to reload shortcuts
        context.subscribe(Events.PLUGIN_SETTINGS_CHANGED, self._on_settings_changed)

    def register_ui(self, ui_builder: Any) -> None:
        """Register UI (just keyboard shortcuts)."""
        pass

    def register_shortcuts(self, shortcut_manager: Any) -> None:
        """Register file management shortcuts."""
        # Store reference to shortcut manager for later reloading
        self.shortcut_manager = shortcut_manager
        self._register_all_shortcuts()

    def _register_all_shortcuts(self) -> None:
        """Register all shortcuts from config."""
        if not self.shortcut_manager:
            return

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
        track = self.context.database.conn.execute(
            "SELECT filepath FROM tracks WHERE id = ?", (track_id,)
        ).fetchone()

        self.current_filepath = Path(track["filepath"]) if track else None
        logging.debug(f"[File Manager] Track loaded: id={track_id}, filepath={self.current_filepath}")

    def _on_settings_changed(self) -> None:
        """Reload shortcuts when settings change."""
        logging.info("[File Manager] Reloading shortcuts after settings change")

        # Unregister all current shortcuts
        for shortcut in self.shortcuts:
            if hasattr(shortcut, "key") and hasattr(shortcut, "key"):
                key_seq = shortcut.key().toString()
                if self.shortcut_manager:
                    self.shortcut_manager.unregister(key_seq)
        self.shortcuts.clear()

        # Reload config from database
        self._reload_config_from_db()

        # Re-register shortcuts with new config
        self._register_all_shortcuts()

    def _reload_config_from_db(self) -> None:
        """Reload file_manager config from database."""
        # Get settings from database
        db = self.context.database

        # Load destinations
        destinations_json = db.conn.execute(
            "SELECT setting_value FROM plugin_settings WHERE plugin_name = ? AND setting_key = ?",
            ("file_manager", "destinations"),
        ).fetchone()

        if destinations_json:
            import json
            try:
                destinations_data = json.loads(destinations_json["setting_value"])
                # Update config with new destinations
                from jukebox.core.config import FileManagerDestinationConfig
                self.context.config.file_manager.destinations = [
                    FileManagerDestinationConfig(**dest) for dest in destinations_data
                ]
            except (json.JSONDecodeError, ValueError) as e:
                logging.error(f"Failed to parse destinations config: {e}")

        # Load trash directory
        trash_dir = db.conn.execute(
            "SELECT setting_value FROM plugin_settings WHERE plugin_name = ? AND setting_key = ?",
            ("file_manager", "trash_directory"),
        ).fetchone()
        if trash_dir:
            self.context.config.file_manager.trash_directory = trash_dir["setting_value"]

        # Load trash key
        trash_key = db.conn.execute(
            "SELECT setting_value FROM plugin_settings WHERE plugin_name = ? AND setting_key = ?",
            ("file_manager", "trash_key"),
        ).fetchone()
        if trash_key:
            self.context.config.file_manager.trash_key = trash_key["setting_value"]

    def _move_to_destination(self, dest_config: Any) -> None:
        """Move current track to destination and rename it 'artist - title.extension'."""
        if not self.current_track_id or not self.current_filepath:
            logging.warning("[File Manager] No track loaded")
            return

        if not self.current_filepath.exists():
            logging.error(f"Source file does not exist: {self.current_filepath}")
            self.context.emit(Events.STATUS_MESSAGE, message="Error: File not found")
            return

        # Get track metadata for renaming
        track = self.context.database.conn.execute(
            "SELECT artist, title FROM tracks WHERE id = ?", (self.current_track_id,)
        ).fetchone()

        if not track:
            logging.error(f"Track {self.current_track_id} not found in database")
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
            logging.warning(f"[File Manager] {error_msg} for track {self.current_track_id}")
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
            logging.error(f"Destination file already exists: {dest_path}")
            self.context.emit(
                Events.STATUS_MESSAGE, message=f"Error: File already exists in {dest_config.name}"
            )
            return

        try:
            # Save filepath before copying
            old_filepath = self.current_filepath

            # Copy file (keep original in curating mode)
            shutil.copy2(str(self.current_filepath), str(dest_path))
            logging.info(f"Copied {old_filepath} -> {dest_path}")

            # Add the copied file to the database in jukebox mode
            from jukebox.utils.metadata import MetadataExtractor

            metadata = MetadataExtractor.extract(dest_path)
            self.context.database.add_track(metadata, mode="jukebox")
            logging.info(f"Added {dest_path} to database in jukebox mode")

            # Delete original from database (track moved out of curating library)
            self.context.database.conn.execute(
                "DELETE FROM tracks WHERE id = ?",
                (self.current_track_id,),
            )
            self.context.database.conn.commit()
            logging.info(f"Deleted track {self.current_track_id} from database")

            # Delete original file from disk
            old_filepath.unlink()
            logging.info(f"Deleted original file: {old_filepath}")

            # Reset current track BEFORE emitting event
            # (because event handlers might load a new track)
            self.current_track_id = None
            self.current_filepath = None

            # Remove from track list and play next (via event)
            from jukebox.core.event_bus import Events

            self.context.emit(Events.TRACK_DELETED, filepath=old_filepath)

            # Show status message
            self.context.emit(
                Events.STATUS_MESSAGE,
                message=f"Copied to {dest_config.name}: {new_filename}",
            )

        except Exception as e:
            logging.error(f"Failed to move file: {e}")
            self.context.emit(Events.STATUS_MESSAGE, message=f"Error moving file: {e}")

    def _move_to_trash(self) -> None:
        """Move current track to trash, remove from database and tracklist, play next."""
        if not self.current_track_id or not self.current_filepath:
            logging.warning("[File Manager] No track loaded")
            return

        if not self.current_filepath.exists():
            logging.error(f"Source file does not exist: {self.current_filepath}")
            self.context.emit(Events.STATUS_MESSAGE, message="Error: File not found")
            return

        # Get trash directory from config
        trash_dir = Path(self.context.config.file_manager.trash_directory).expanduser()
        trash_dir.mkdir(parents=True, exist_ok=True)

        # Keep original filename
        dest_path = trash_dir / self.current_filepath.name

        # Check if destination already exists
        if dest_path.exists():
            logging.error(f"File already exists in trash: {dest_path}")
            self.context.emit(Events.STATUS_MESSAGE, message="Error: File already exists in trash")
            return

        try:
            # Save filepath before moving
            old_filepath = self.current_filepath

            # Move file to trash
            shutil.move(str(self.current_filepath), str(dest_path))
            logging.info(f"Moved to trash: {old_filepath} -> {dest_path}")

            # Delete from database (and waveform_cache via CASCADE)
            self.context.database.conn.execute(
                "DELETE FROM tracks WHERE id = ?",
                (self.current_track_id,),
            )
            self.context.database.conn.commit()
            logging.info(f"Deleted track {self.current_track_id} from database")

            # Reset current track BEFORE emitting event
            # (because event handlers might load a new track)
            self.current_track_id = None
            self.current_filepath = None

            # Remove from track list and play next (via event)
            from jukebox.core.event_bus import Events

            self.context.emit(Events.TRACK_DELETED, filepath=old_filepath)

            # Show status message
            self.context.emit(
                Events.STATUS_MESSAGE,
                message=f"Deleted: {old_filepath.name}",
            )

        except Exception as e:
            logging.error(f"Failed to move file to trash: {e}")
            self.context.emit(Events.STATUS_MESSAGE, message=f"Error moving to trash: {e}")

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename by removing invalid characters."""
        # Replace invalid characters with underscore
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename

    def activate(self, mode: str) -> None:
        """Activate plugin for this mode."""
        # Enable all shortcuts
        for shortcut in self.shortcuts:
            shortcut.setEnabled(True)
        logging.debug(f"[File Manager] Activated for {mode} mode")

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for this mode."""
        # Disable all shortcuts
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
        logging.debug(f"[File Manager] Deactivated for {mode} mode")

    def shutdown(self) -> None:
        """Cleanup on application exit."""
        pass

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
