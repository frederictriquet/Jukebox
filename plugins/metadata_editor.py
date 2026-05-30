"""Metadata editor plugin."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jukebox.core.event_bus import Events

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol


class TabEventFilter(QObject):
    """Event filter to capture TAB key within metadata editor."""

    def __init__(self, metadata_widget: MetadataEditorWidget):
        """Initialize event filter."""
        super().__init__()
        self.metadata_widget = metadata_widget
        self._enabled = True

    def setEnabled(self, enabled: bool) -> None:
        """Enable or disable the event filter."""
        self._enabled = enabled

    def eventFilter(self, obj: Any, event: Any) -> bool:  # noqa: N802
        """Filter events to handle TAB within metadata editor."""
        if not self._enabled:
            return False

        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtWidgets import QApplication

        if event.type() == QEvent.Type.KeyPress:
            # Get the widget that currently has focus
            focused_widget = QApplication.focusWidget()

            if event.key() == Qt.Key.Key_Tab:
                if isinstance(focused_widget, QLineEdit) and focused_widget in self.metadata_widget.field_widgets:
                    current_index = self.metadata_widget.field_widgets.index(focused_widget)
                    if current_index == len(self.metadata_widget.field_widgets) - 1:
                        focused_widget.clearFocus()
                    else:
                        self.metadata_widget.field_widgets[current_index + 1].setFocus()
                elif self.metadata_widget.field_widgets:
                    self.metadata_widget.field_widgets[0].setFocus()
                return True

            elif event.key() == Qt.Key.Key_Backtab and isinstance(focused_widget, QLineEdit) and focused_widget in self.metadata_widget.field_widgets:
                current_index = self.metadata_widget.field_widgets.index(focused_widget)
                prev_index = (current_index - 1) % len(self.metadata_widget.field_widgets)
                self.metadata_widget.field_widgets[prev_index].setFocus()
                return True

        return False  # Let other events continue


TAG_TO_DB_COLUMN = {
    "artist": "artist",
    "title": "title",
    "album": "album",
    "albumartist": "album_artist",
    "genre": "genre",
    "date": "year",
}


class MetadataEditorPlugin:
    """Edit track metadata for currently playing track."""

    name = "metadata_editor"
    version = "2.0.0"
    description = "Edit track metadata (configurable fields)"
    modes = ["curating"]  # Only active in curating mode

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol = None  # type: ignore[assignment]
        self.editor_widget: MetadataEditorWidget | None = None
        self.tab_event_filter: TabEventFilter | None = None
        self.current_track_id: int | None = None

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to track loaded event
        context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register metadata editor widget."""
        # Get field configuration
        field_configs = self.context.config.metadata_editor.fields

        self.editor_widget = MetadataEditorWidget(field_configs)
        self.editor_widget.save_clicked.connect(self._on_save_metadata)

        # Store reference to TAB event filter
        self.tab_event_filter = self.editor_widget.tab_filter

        # Add below player controls in main layout
        ui_builder.add_bottom_widget(self.editor_widget)

    def _on_track_loaded(self, track_id: int) -> None:
        """Handle track loaded event."""
        if not self.editor_widget:
            return

        self.current_track_id = track_id

        # Get track metadata from database
        field_configs = self.context.config.metadata_editor.fields
        db_columns = [TAG_TO_DB_COLUMN.get(f.tag, f.tag) for f in field_configs]
        track = self.context.database.tracks.get_by_id(track_id)

        if track:
            # Pass filepath for filename splitting
            self.editor_widget.set_current_filepath(track["filepath"])

            # Extract values and map back to tag names
            values = {}
            for idx, config in enumerate(field_configs):
                db_value = track[db_columns[idx]]
                # Convert year integer to string if needed
                if db_value is not None:
                    values[config.tag] = str(db_value) if isinstance(db_value, int) else db_value
                else:
                    values[config.tag] = ""
            # For comment: fallback to file tag if DB value is NULL (never imported)
            if "comment" in values and not values["comment"]:
                db_comment = track.get("comment")
                if db_comment is None:
                    from jukebox.utils.metadata import MetadataExtractor

                    try:
                        file_meta = MetadataExtractor.extract(Path(track["filepath"]))
                        comment = file_meta.get("comment", "") or ""
                    except Exception:
                        # M31 : ne pas avaler silencieusement l'erreur d'extraction
                        logging.warning(
                            "Failed to extract comment from %s, defaulting to empty",
                            track["filepath"],
                            exc_info=True,
                        )
                        comment = ""
                    self.context.database.tracks.update_metadata(track_id, {"comment": comment})
                    values["comment"] = comment

            self.editor_widget.set_metadata(values)

    def _on_save_metadata(self, field_values: dict[str, str]) -> None:
        """Save metadata to database and file tags."""
        if self.current_track_id is None:
            return

        # Get filepath from database
        track = self.context.database.tracks.get_by_id(self.current_track_id)

        if not track:
            return

        filepath = track["filepath"]

        # Sanitize metadata (max 500 chars per field, strip control chars)
        def sanitize(value: str) -> str:
            if not value:
                return ""
            # Strip control characters
            cleaned = "".join(char for char in value if ord(char) >= 32 or char in "\n\r\t")
            # Limit length
            return cleaned[:500]

        sanitized_values = {name: sanitize(value) for name, value in field_values.items()}

        # M32 : écrire d'abord le tag fichier, puis la DB. Si l'écriture fichier
        # échoue, on n'altère pas la DB afin d'éviter une divergence DB/fichier.
        from jukebox.utils.tag_writer import save_audio_tags

        success = save_audio_tags(filepath, sanitized_values)
        if not success:
            logging.error("Failed to save file tags: %s", filepath)
            # Retour visuel dans la status bar en cas d'échec de sauvegarde
            self.context.emit(
                Events.STATUS_MESSAGE,
                message=f"Erreur : impossible de sauvegarder les métadonnées dans {Path(filepath).name}",
            )
            return

        # Le fichier est à jour : on synchronise la DB avec les colonnes mappées
        db_updates = {}
        for tag, value in sanitized_values.items():
            db_column = TAG_TO_DB_COLUMN.get(tag, tag)
            # Convertir year en entier si c'est un nombre
            if db_column == "year" and value.isdigit():
                db_updates[db_column] = int(value)
            else:
                db_updates[db_column] = value

        self.context.database.tracks.update_metadata(self.current_track_id, db_updates)
        logging.info("Saved metadata for track %d", self.current_track_id)

        # Note: We don't emit TRACKS_ADDED here to avoid reloading the entire track list
        # The track list display will update on next full reload

    def activate(self, mode: str) -> None:
        """Activate plugin for this mode."""
        if self.editor_widget:
            self.editor_widget.setVisible(True)
        # Enable TAB event filter
        if self.tab_event_filter:
            self.tab_event_filter.setEnabled(True)
        logging.debug("[Metadata Editor] Activated for %s mode", mode)

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for this mode."""
        if self.editor_widget:
            self.editor_widget.setVisible(False)
        # Disable TAB event filter
        if self.tab_event_filter:
            self.tab_event_filter.setEnabled(False)
        logging.debug("[Metadata Editor] Deactivated for %s mode", mode)

    def shutdown(self) -> None:
        """Cleanup on application exit."""
        # Retire le filtre TAB de QApplication pour éviter une fuite mémoire
        # et un overhead sur tous les événements clavier (le widget peut être
        # encore visible au moment du shutdown, donc hideEvent n'a pas suffi).
        if self.tab_event_filter is not None:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app:
                app.removeEventFilter(self.tab_event_filter)


class MetadataEditorWidget(QWidget):
    """Widget to edit track metadata with dynamic fields."""

    save_clicked = Signal(dict)  # Emits dict of field_name -> value

    def __init__(self, field_configs: list[Any]) -> None:
        """Initialize widget.

        Args:
            field_configs: List of MetadataFieldConfig objects
        """
        super().__init__()
        self.field_configs = field_configs
        self.field_widgets: list[QLineEdit] = []
        self.field_map: dict[str, QLineEdit] = {}  # tag name -> widget
        self._current_filepath: Path | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI dynamically based on field configuration."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 5, 10, 5)
        main_layout.setSpacing(5)

        label_width = 65

        # Grid 4 colonnes : label | input | label | input
        grid = QGridLayout()
        grid.setSpacing(5)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 1)

        for idx, config in enumerate(self.field_configs):
            row = idx // 2
            col_pair = (idx % 2) * 2

            label = QLabel(f"{config.label}:")
            label.setFixedWidth(label_width)
            grid.addWidget(label, row, col_pair)

            line_edit = QLineEdit()
            if config.width:
                line_edit.setMaximumWidth(config.width)

            # Comment : col_span sur les 3 colonnes restantes
            is_last_alone = idx == len(self.field_configs) - 1 and idx % 2 == 0
            col_span = 3 if is_last_alone else 1

            if config.tag == "title":
                h = QHBoxLayout()
                h.setSpacing(5)
                h.setContentsMargins(0, 0, 0, 0)
                h.addWidget(line_edit, 1)
                self._split_btn = QPushButton("Name → Artist / Title")
                self._split_btn.setToolTip("Extraire Artist et Title du nom de fichier")
                self._split_btn.setStyleSheet("QPushButton { padding: 6px 8px; }")
                self._split_btn.clicked.connect(self._on_split_filename)
                h.addWidget(self._split_btn)
                grid.addLayout(h, row, col_pair + 1, 1, col_span)
            elif config.tag == "comment":
                h = QHBoxLayout()
                h.setSpacing(5)
                h.setContentsMargins(0, 0, 0, 0)
                h.addWidget(line_edit, 1)
                self._clear_btn = QPushButton("Clear")
                self._clear_btn.setToolTip("Clear comment")
                self._clear_btn.setStyleSheet("QPushButton { padding: 6px 8px; }")
                self._clear_btn.clicked.connect(lambda: self._clear_field("comment"))
                h.addWidget(self._clear_btn)
                grid.addLayout(h, row, col_pair + 1, 1, col_span)
            else:
                grid.addWidget(line_edit, row, col_pair + 1, 1, col_span)

            self.field_widgets.append(line_edit)
            self.field_map[config.tag] = line_edit
            line_edit.editingFinished.connect(self._on_field_changed)

        main_layout.addLayout(grid)

        self.setLayout(main_layout)
        self.setMaximumHeight(130)

        # Setup tab order
        for i in range(len(self.field_widgets) - 1):
            self.setTabOrder(self.field_widgets[i], self.field_widgets[i + 1])
        if self.field_widgets:
            self.setTabOrder(self.field_widgets[-1], self.field_widgets[0])  # Loop back

        self.tab_filter = TabEventFilter(self)

    def set_metadata(self, values: dict[str, str]) -> None:
        """Set metadata values in fields.

        Args:
            values: Dict mapping tag names to values
        """
        for tag, value in values.items():
            if tag in self.field_map:
                self.field_map[tag].setText(value)

    def set_current_filepath(self, filepath: str | Path) -> None:
        """Store the current track's filepath for filename splitting.

        Args:
            filepath: Path to the current audio file.
        """
        self._current_filepath = Path(filepath)

    def _clear_field(self, tag: str) -> None:
        """Clear a field and trigger save."""
        widget = self.field_map.get(tag)
        if widget:
            widget.clear()
            self._on_field_changed()

    def _on_split_filename(self) -> None:
        """Split filename 'Artist - Title.ext' into Artist and Title fields."""
        if not self._current_filepath:
            return

        stem = Path(self._current_filepath).stem
        if " - " not in stem:
            return

        artist, title = stem.split(" - ", 1)
        artist = artist.strip()
        title = title.strip()

        artist_widget = self.field_map.get("artist")
        title_widget = self.field_map.get("title")

        if artist_widget and artist:
            artist_widget.setText(artist)
        if title_widget and title:
            title_widget.setText(title)

        # Trigger auto-save
        self._on_field_changed()

    def showEvent(self, event: Any) -> None:  # noqa: N802
        """Installe le filtre TAB quand le widget devient visible."""
        super().showEvent(event)
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app:
            app.installEventFilter(self.tab_filter)

    def hideEvent(self, event: Any) -> None:  # noqa: N802
        """Retire le filtre TAB quand le widget est masqué."""
        super().hideEvent(event)
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app:
            app.removeEventFilter(self.tab_filter)

    def _on_field_changed(self) -> None:
        """Handle field editing finished - auto-save."""
        values = {}
        for config in self.field_configs:
            widget = self.field_map.get(config.tag)
            if widget:
                values[config.tag] = widget.text()

        self.save_clicked.emit(values)
