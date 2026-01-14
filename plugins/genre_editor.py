"""Genre editor plugin with custom code-based genre system."""

import logging
import re
from typing import Any


class GenreEditorPlugin:
    """Edit genre using keyboard shortcuts for code toggles."""

    name = "genre_editor"
    version = "1.0.0"
    description = "Genre editor with code-based system"
    modes = ["curating"]  # Only active in curating mode

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None
        self.current_track_id: int | None = None
        self.current_genre: str = ""
        self.shortcuts: list[Any] = []  # Keep references to shortcuts
        self.shortcut_manager: Any = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to track loaded event
        from jukebox.core.event_bus import Events

        context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)
        # Subscribe to settings changes to reload shortcuts
        context.subscribe("plugin_settings_changed", self._on_settings_changed)

    def register_ui(self, ui_builder: Any) -> None:
        """Register UI (just keyboard shortcuts)."""
        pass

    def register_shortcuts(self, shortcut_manager: Any) -> None:
        """Register genre code shortcuts."""
        # Store reference to shortcut manager for later reloading
        self.shortcut_manager = shortcut_manager
        self._register_all_shortcuts()

    def _register_all_shortcuts(self) -> None:
        """Register all shortcuts from config."""
        if not self.shortcut_manager:
            return

        # Get genre codes from config
        genre_config = self.context.config.genre_editor

        for code_config in genre_config.codes:
            shortcut = self.shortcut_manager.register(
                code_config.key,
                lambda c=code_config.code: self._toggle_code(c),
                plugin_name=self.name,
            )
            self.shortcuts.append(shortcut)

        # Register rating shortcut
        shortcut = self.shortcut_manager.register(
            genre_config.rating_key, self._cycle_rating, plugin_name=self.name
        )
        self.shortcuts.append(shortcut)

    def _on_track_loaded(self, track_id: int) -> None:
        """Load current genre when track loads."""
        self.current_track_id = track_id

        # Get genre from database
        track = self.context.database.conn.execute(
            "SELECT genre FROM tracks WHERE id = ?", (track_id,)
        ).fetchone()

        # Validate genre format - if invalid, reset to empty
        if track and track["genre"]:
            genre = track["genre"]
            # Validate against pattern (same as GenreStyler)
            # Note: *0 is not allowed, only *1 to *5
            genre_pattern = r"^([A-Z])(-[A-Z])*(-\*[1-5])?$"
            if re.match(genre_pattern, genre):
                self.current_genre = genre
            else:
                # Invalid genre - reset to empty
                logging.info(f"Invalid genre format '{genre}' for track {track_id}, resetting to empty")
                self.current_genre = ""
        else:
            self.current_genre = ""

    def _on_settings_changed(self) -> None:
        """Reload shortcuts when settings change."""
        logging.info("[Genre Editor] Reloading shortcuts after settings change")

        # Unregister all current shortcuts
        for shortcut in self.shortcuts:
            if hasattr(shortcut, "key"):
                key_seq = shortcut.key().toString()
                if self.shortcut_manager:
                    self.shortcut_manager.unregister(key_seq)
        self.shortcuts.clear()

        # Reload config from database
        self._reload_config_from_db()

        # Re-register shortcuts with new config
        self._register_all_shortcuts()

    def _reload_config_from_db(self) -> None:
        """Reload genre_editor config from database."""
        db = self.context.database

        # Load genre codes
        codes_json = db.conn.execute(
            "SELECT setting_value FROM plugin_settings WHERE plugin_name = ? AND setting_key = ?",
            ("genre_editor", "genre_codes"),
        ).fetchone()

        if codes_json:
            import json
            try:
                codes_data = json.loads(codes_json["setting_value"])
                # Update config with new codes
                from jukebox.core.config import GenreCodeConfig
                self.context.config.genre_editor.codes = [
                    GenreCodeConfig(**code) for code in codes_data
                ]
            except (json.JSONDecodeError, ValueError) as e:
                logging.error(f"Failed to parse genre codes config: {e}")

        # Load rating key
        rating_key = db.conn.execute(
            "SELECT setting_value FROM plugin_settings WHERE plugin_name = ? AND setting_key = ?",
            ("genre_editor", "rating_key"),
        ).fetchone()
        if rating_key:
            self.context.config.genre_editor.rating_key = rating_key["setting_value"]

    def _toggle_code(self, code: str) -> None:
        """Toggle a genre code in the current genre."""
        if self.current_track_id is None:
            return

        # Parse current genre (format: "CODE1-CODE2-*3")
        parts = self.current_genre.split("-") if self.current_genre else []

        # Separate codes and rating
        codes = [p for p in parts if not p.startswith("*")]
        rating_parts = [p for p in parts if p.startswith("*")]
        rating = rating_parts[0] if rating_parts else ""

        # Toggle code
        if code in codes:
            codes.remove(code)
        else:
            codes.append(code)
            codes.sort()  # Keep codes alphabetically sorted

        # Rebuild genre
        new_genre = "-".join(codes)
        if rating:
            new_genre = f"{new_genre}-{rating}" if new_genre else rating

        self._save_genre(new_genre)

    def _cycle_rating(self) -> None:
        """Cycle through ratings: none -> *1 -> *2 -> *3 -> *4 -> *5 -> none."""
        if self.current_track_id is None:
            return

        # Parse current genre
        parts = self.current_genre.split("-") if self.current_genre else []
        codes = [p for p in parts if not p.startswith("*")]
        rating_parts = [p for p in parts if p.startswith("*")]

        # Determine next rating
        if not rating_parts:
            new_rating = "*1"
        else:
            current = rating_parts[0]
            match = re.match(r"\*(\d)", current)
            if match:
                current_num = int(match.group(1))
                if current_num >= 5:
                    new_rating = ""  # Cycle back to no rating
                else:
                    new_rating = f"*{current_num + 1}"
            else:
                new_rating = "*1"

        # Rebuild genre
        new_genre = "-".join(codes)
        if new_rating:
            new_genre = f"{new_genre}-{new_rating}" if new_genre else new_rating

        self._save_genre(new_genre)

    def _save_genre(self, new_genre: str) -> None:
        """Save genre to database and file tags."""
        if self.current_track_id is None:
            return

        self.current_genre = new_genre

        # Get filepath
        track = self.context.database.conn.execute(
            "SELECT filepath FROM tracks WHERE id = ?", (self.current_track_id,)
        ).fetchone()

        if not track:
            return

        filepath = track["filepath"]

        # Update database
        self.context.database.conn.execute(
            "UPDATE tracks SET genre = ? WHERE id = ?", (new_genre, self.current_track_id)
        )
        self.context.database.conn.commit()

        # Emit event to update track list display
        from pathlib import Path
        self.context.emit("track_metadata_updated", filepath=Path(filepath))

        # Update file tags
        try:
            from mutagen import File
            from mutagen.easyid3 import EasyID3
            from mutagen.id3 import ID3NoHeaderError

            if filepath.lower().endswith(".mp3"):
                # Use EasyID3 for MP3
                try:
                    audio = EasyID3(filepath)
                except ID3NoHeaderError:
                    audio = File(filepath, easy=True)
                    audio.add_tags()

                if new_genre:
                    audio["genre"] = [new_genre]
                elif "genre" in audio:
                    del audio["genre"]

                audio.save()
            else:
                # Use generic mutagen for other formats
                audio = File(filepath)
                if audio is None:
                    logging.warning(f"Unsupported file format: {filepath}")
                    return

                if new_genre:
                    audio["genre"] = [new_genre]
                elif "genre" in audio:
                    del audio["genre"]

                audio.save()

            logging.info(f"Saved genre '{new_genre}' for track {self.current_track_id}")

        except Exception as e:
            logging.error(f"Failed to save genre to file: {e}")

        # Note: We don't emit TRACKS_ADDED here to avoid reloading the entire track list
        # The track list display will update on next full reload

    def activate(self, mode: str) -> None:
        """Activate plugin for this mode."""
        # Enable all shortcuts
        for shortcut in self.shortcuts:
            shortcut.setEnabled(True)
        logging.debug(f"[Genre Editor] Activated for {mode} mode")

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for this mode."""
        # Disable all shortcuts
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
        logging.debug(f"[Genre Editor] Deactivated for {mode} mode")

    def shutdown(self) -> None:
        """Cleanup on application exit."""
        pass

    def get_settings_schema(self) -> dict[str, Any]:
        """Return settings schema for configuration UI.

        Returns:
            Dict mapping setting keys to their configuration
        """
        return {
            "genre_codes": {
                "label": "Genre Codes",
                "type": "list",
                "item_schema": {
                    "code": {"label": "Code", "type": "string"},
                    "name": {"label": "Name", "type": "string"},
                    "key": {"label": "Shortcut", "type": "shortcut"},
                },
                "default": [
                    {"code": code.code, "name": code.name, "key": code.key}
                    for code in self.context.config.genre_editor.codes
                ],
            },
            "rating_key": {
                "label": "Rating Shortcut",
                "type": "shortcut",
                "default": self.context.config.genre_editor.rating_key,
            },
        }
