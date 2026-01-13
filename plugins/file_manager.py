"""File manager plugin for moving/renaming/deleting tracks."""

import logging
import shutil
from pathlib import Path
from typing import Any


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

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to track loaded event
        from jukebox.core.event_bus import Events

        context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)

    def register_ui(self, ui_builder: Any) -> None:
        """Register UI (just keyboard shortcuts)."""
        pass

    def register_shortcuts(self, shortcut_manager: Any) -> None:
        """Register file management shortcuts."""
        # Get file manager config
        file_config = self.context.config.file_manager

        # Register destination shortcuts (move + rename)
        for dest_config in file_config.destinations:
            shortcut = shortcut_manager.register(
                dest_config.key,
                lambda d=dest_config: self._move_to_destination(d),
                plugin_name=self.name,
            )
            self.shortcuts.append(shortcut)

        # Register trash shortcut (move without rename)
        if file_config.trash_directory:
            shortcut = shortcut_manager.register(
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

    def _move_to_destination(self, dest_config: Any) -> None:
        """Move current track to destination and rename it 'artist - title.extension'."""
        if not self.current_track_id or not self.current_filepath:
            logging.warning("No track loaded")
            return

        if not self.current_filepath.exists():
            logging.error(f"Source file does not exist: {self.current_filepath}")
            self.context.emit("status_message", message=f"Error: File not found")
            return

        # Get track metadata for renaming
        track = self.context.database.conn.execute(
            "SELECT artist, title FROM tracks WHERE id = ?", (self.current_track_id,)
        ).fetchone()

        if not track:
            logging.error(f"Track {self.current_track_id} not found in database")
            return

        artist = track["artist"] or "Unknown Artist"
        title = track["title"] or "Unknown Title"
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
                "status_message", message=f"Error: File already exists in {dest_config.name}"
            )
            return

        try:
            # Save filepath before moving
            old_filepath = self.current_filepath

            # Move file
            shutil.move(str(self.current_filepath), str(dest_path))
            logging.info(f"Moved {old_filepath} -> {dest_path}")

            # Delete from database (track moved out of library)
            self.context.database.conn.execute(
                "DELETE FROM tracks WHERE id = ?",
                (self.current_track_id,),
            )
            self.context.database.conn.commit()
            logging.info(f"Deleted track {self.current_track_id} from database")

            # Remove from track list and play next (via event)
            from jukebox.core.event_bus import Events

            self.context.emit(Events.TRACK_DELETED, filepath=old_filepath)

            # Show status message
            self.context.emit(
                "status_message",
                message=f"Moved to {dest_config.name}: {new_filename}",
            )

            # Reset current track
            self.current_track_id = None
            self.current_filepath = None

        except Exception as e:
            logging.error(f"Failed to move file: {e}")
            self.context.emit("status_message", message=f"Error moving file: {e}")

    def _move_to_trash(self) -> None:
        """Move current track to trash, remove from database and tracklist, play next."""
        if not self.current_track_id or not self.current_filepath:
            logging.warning("No track loaded")
            return

        if not self.current_filepath.exists():
            logging.error(f"Source file does not exist: {self.current_filepath}")
            self.context.emit("status_message", message=f"Error: File not found")
            return

        # Get trash directory from config
        trash_dir = Path(self.context.config.file_manager.trash_directory).expanduser()
        trash_dir.mkdir(parents=True, exist_ok=True)

        # Keep original filename
        dest_path = trash_dir / self.current_filepath.name

        # Check if destination already exists
        if dest_path.exists():
            logging.error(f"File already exists in trash: {dest_path}")
            self.context.emit("status_message", message=f"Error: File already exists in trash")
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

            # Remove from track list and play next (via event)
            from jukebox.core.event_bus import Events

            self.context.emit(Events.TRACK_DELETED, filepath=old_filepath)

            # Show status message
            self.context.emit(
                "status_message",
                message=f"Deleted: {old_filepath.name}",
            )

            # Reset current track
            self.current_track_id = None
            self.current_filepath = None

        except Exception as e:
            logging.error(f"Failed to move file to trash: {e}")
            self.context.emit("status_message", message=f"Error moving to trash: {e}")

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
