"""Genre editor plugin with custom code-based genre system."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jukebox.core.config import GenreCodeConfig
from jukebox.core.event_bus import Events
from jukebox.core.settings_sync_mixin import SettingsSyncMixin, SyncedJsonList, SyncedSetting
from jukebox.core.shortcut_mixin import ShortcutMixin
from jukebox.ui.components.track_cell_renderer import GENRE_PATTERN

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol


class GenreEditorPlugin(SettingsSyncMixin, ShortcutMixin):
    """Edit genre using keyboard shortcuts for code toggles."""

    name = "genre_editor"
    version = "1.0.0"
    description = "Genre editor with code-based system"
    modes = ["jukebox", "curating"]

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol = None  # type: ignore[assignment]
        self.current_track_id: int | None = None
        self.current_genre: str = ""
        self._init_shortcut_mixin()

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to track loaded event
        context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)
        # Subscribe to settings changes to reload shortcuts
        context.subscribe(Events.PLUGIN_SETTINGS_CHANGED, self._on_settings_changed)

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register UI (just keyboard shortcuts)."""
        pass

    def _register_plugin_shortcuts(self) -> None:
        """Register genre code shortcuts."""
        if self.context is None:
            return
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
        if self.context is None:
            return

        # Get genre from database
        track = self.context.database.tracks.get_by_id(track_id)

        # Validate genre format - if invalid, reset to empty
        if track and track["genre"]:
            genre = track["genre"]
            # Validation via le pattern partagé avec GenreStyler
            if GENRE_PATTERN.match(genre):
                self.current_genre = genre
            else:
                # Invalid genre - reset to empty
                logging.info(
                    "Invalid genre format '%s' for track %s, resetting to empty", genre, track_id
                )
                self.current_genre = ""
        else:
            self.current_genre = ""

    _synced_settings = [
        SyncedSetting("rating_key", str),
    ]
    _synced_json_lists = [
        SyncedJsonList("genre_codes", "codes", GenreCodeConfig),
    ]

    def _reload_plugin_config(self) -> None:
        """Reload genre_editor config from database."""
        if self.context is None:
            return
        # Conserver les hashtags du YAML avant que le sync DB ne les écrase
        # (la DB ne stocke pas les hashtags car ils ne sont pas exposés dans l'UI de settings)
        yaml_hashtags = {gc.code: gc.hashtags for gc in self.context.config.genre_editor.codes}
        self._sync_settings_from_db()
        # Restaurer les hashtags si la DB a des codes sans hashtags
        for gc in self.context.config.genre_editor.codes:
            if not gc.hashtags and gc.code in yaml_hashtags:
                gc.hashtags = yaml_hashtags[gc.code]

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
                new_rating = "" if current_num >= 5 else f"*{current_num + 1}"
            else:
                new_rating = "*1"

        # Rebuild genre
        new_genre = "-".join(codes)
        if new_rating:
            new_genre = f"{new_genre}-{new_rating}" if new_genre else new_rating

        self._save_genre(new_genre)

    def _save_genre(self, new_genre: str) -> None:
        """Save genre to database and file tags."""
        if self.current_track_id is None or self.context is None:
            return

        self.current_genre = new_genre

        # Get filepath
        track = self.context.database.tracks.get_by_id(self.current_track_id)

        if not track:
            return

        filepath = track["filepath"]

        # M29 : écrire d'abord le tag fichier, puis la DB. Si l'écriture fichier
        # échoue, on n'altère pas la DB afin d'éviter une divergence DB/fichier.
        from jukebox.utils.tag_writer import save_audio_tags

        success = save_audio_tags(filepath, {"genre": new_genre})
        if not success:
            logging.error("Failed to save genre to file: %s", filepath)
            # Retour visuel dans la status bar en cas d'échec de sauvegarde
            self.context.emit(
                Events.STATUS_MESSAGE,
                message=f"Erreur : impossible de sauvegarder le genre dans {Path(filepath).name}",
            )
            return

        # Le fichier est à jour : on synchronise la DB et l'affichage
        self.context.database.tracks.update_metadata(self.current_track_id, {"genre": new_genre})
        self.context.emit(Events.TRACK_METADATA_UPDATED, filepath=Path(filepath))
        logging.info("Saved genre '%s' for track %s", new_genre, self.current_track_id)

        # Note: We don't emit TRACKS_ADDED here to avoid reloading the entire track list
        # The track list display will update on next full reload

    def activate(self, mode: str) -> None:
        """Activate plugin for this mode."""
        self._activate_shortcuts()
        logging.debug("[Genre Editor] Activated for %s mode", mode)

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for this mode."""
        self._deactivate_shortcuts()
        logging.debug("[Genre Editor] Deactivated for %s mode", mode)

    def shutdown(self) -> None:
        """Cleanup on application exit. No cleanup needed for this plugin."""
        ...

    def get_settings_schema(self) -> dict[str, Any]:
        """Return settings schema for configuration UI.

        Returns:
            Dict mapping setting keys to their configuration
        """
        if self.context is None:
            return {}
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
