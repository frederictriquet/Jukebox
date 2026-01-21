"""Metadata editor plugin."""

import logging
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QLineEdit, QWidget


class TabEventFilter(QObject):
    """Event filter to capture TAB key within metadata editor."""

    def __init__(self, metadata_widget: "MetadataEditorWidget"):
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
                # Check if current focus is within metadata editor fields
                if focused_widget in self.metadata_widget.field_widgets:
                    # Already in metadata fields
                    current_index = self.metadata_widget.field_widgets.index(focused_widget)

                    # If on last field, clear focus (triggers save)
                    if current_index == len(self.metadata_widget.field_widgets) - 1:
                        focused_widget.clearFocus()
                        return True  # Block TAB from propagating
                    else:
                        # Go to next field
                        next_index = current_index + 1
                        self.metadata_widget.field_widgets[next_index].setFocus()
                        return True  # Block TAB from propagating
                else:
                    # Not in metadata fields, go to first field
                    if self.metadata_widget.field_widgets:
                        self.metadata_widget.field_widgets[0].setFocus()
                    return True  # Block TAB from propagating

            elif (
                event.key() == Qt.Key.Key_Backtab
                and focused_widget in self.metadata_widget.field_widgets
            ):
                # Shift+Tab: go backwards
                current_index = self.metadata_widget.field_widgets.index(focused_widget)
                prev_index = (current_index - 1) % len(self.metadata_widget.field_widgets)
                self.metadata_widget.field_widgets[prev_index].setFocus()
                return True  # Block Shift+TAB from propagating

        return False  # Let other events continue


class MetadataEditorPlugin:
    """Edit track metadata for currently playing track."""

    name = "metadata_editor"
    version = "2.0.0"
    description = "Edit track metadata (configurable fields)"
    modes = ["curating"]  # Only active in curating mode

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None
        self.editor_widget: MetadataEditorWidget | None = None
        self.tab_event_filter: TabEventFilter | None = None
        self.current_track_id: int | None = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to track loaded event
        from jukebox.core.event_bus import Events

        context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)

    def register_ui(self, ui_builder: Any) -> None:
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

        # Map config tags to database columns
        tag_to_db_column = {
            "artist": "artist",
            "title": "title",
            "album": "album",
            "albumartist": "album_artist",  # DB uses underscore
            "genre": "genre",
            "date": "year",  # DB uses 'year' column
        }

        # Get track metadata from database
        field_configs = self.context.config.metadata_editor.fields
        db_columns = [tag_to_db_column.get(f.tag, f.tag) for f in field_configs]
        track = self.context.database.get_track_by_id(track_id)

        if track:
            # Extract values and map back to tag names
            values = {}
            for idx, config in enumerate(field_configs):
                db_value = track[db_columns[idx]]
                # Convert year integer to string if needed
                if db_value is not None:
                    values[config.tag] = str(db_value) if isinstance(db_value, int) else db_value
                else:
                    values[config.tag] = ""
            self.editor_widget.set_metadata(values)

    def _on_save_metadata(self, field_values: dict[str, str]) -> None:
        """Save metadata to database and file tags."""
        if self.current_track_id is None:
            return

        # Get filepath from database
        track = self.context.database.get_track_by_id(self.current_track_id)

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

        # Map config tags to database columns
        tag_to_db_column = {
            "artist": "artist",
            "title": "title",
            "album": "album",
            "albumartist": "album_artist",  # DB uses underscore
            "genre": "genre",
            "date": "year",  # DB uses 'year' column
        }

        # Update database with mapped column names
        db_updates = {}
        for tag, value in sanitized_values.items():
            db_column = tag_to_db_column.get(tag, tag)
            # Convert year to integer if it's a number
            if db_column == "year" and value.isdigit():
                db_updates[db_column] = int(value)
            else:
                db_updates[db_column] = value

        self.context.database.update_track_metadata(self.current_track_id, db_updates)

        # Update file tags
        from jukebox.utils.tag_writer import save_audio_tags

        success = save_audio_tags(filepath, sanitized_values)
        if success:
            logging.info(f"Saved metadata for track {self.current_track_id}")
        else:
            logging.error(f"Failed to save file tags: {filepath}")

        # Note: We don't emit TRACKS_ADDED here to avoid reloading the entire track list
        # The track list display will update on next full reload

    def activate(self, mode: str) -> None:
        """Activate plugin for this mode."""
        if self.editor_widget:
            self.editor_widget.setVisible(True)
        # Enable TAB event filter
        if self.tab_event_filter:
            self.tab_event_filter.setEnabled(True)
        logging.debug(f"[Metadata Editor] Activated for {mode} mode")

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for this mode."""
        if self.editor_widget:
            self.editor_widget.setVisible(False)
        # Disable TAB event filter
        if self.tab_event_filter:
            self.tab_event_filter.setEnabled(False)
        logging.debug(f"[Metadata Editor] Deactivated for {mode} mode")

    def shutdown(self) -> None:
        """Cleanup on application exit. No cleanup needed for this plugin."""
        ...


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
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI dynamically based on field configuration."""
        layout = QGridLayout()
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(5)

        # Create widgets for each configured field
        # Layout: 2 columns, filling row by row
        for idx, config in enumerate(self.field_configs):
            row = idx // 2  # Integer division: 0,1 -> row 0; 2,3 -> row 1, etc.
            col_pair = (idx % 2) * 2  # 0 for first column pair (0,1), 2 for second (2,3)

            # Add label
            label = QLabel(f"{config.label}:")
            layout.addWidget(label, row, col_pair)

            # Add line edit
            line_edit = QLineEdit()
            if config.width:
                line_edit.setMaximumWidth(config.width)
                layout.addWidget(line_edit, row, col_pair + 1, alignment=Qt.AlignmentFlag.AlignLeft)
            else:
                layout.addWidget(line_edit, row, col_pair + 1)

            # Store widget
            self.field_widgets.append(line_edit)
            self.field_map[config.tag] = line_edit

            # Connect auto-save
            line_edit.editingFinished.connect(self._on_field_changed)

        self.setLayout(layout)
        self.setMaximumHeight(100)

        # Setup tab order
        for i in range(len(self.field_widgets) - 1):
            self.setTabOrder(self.field_widgets[i], self.field_widgets[i + 1])
        if self.field_widgets:
            self.setTabOrder(self.field_widgets[-1], self.field_widgets[0])  # Loop back

        # Install event filter on application to capture TAB
        from PySide6.QtWidgets import QApplication

        self.tab_filter = TabEventFilter(self)
        app = QApplication.instance()
        if app:
            app.installEventFilter(self.tab_filter)

    def set_metadata(self, values: dict[str, str]) -> None:
        """Set metadata values in fields.

        Args:
            values: Dict mapping tag names to values
        """
        for tag, value in values.items():
            if tag in self.field_map:
                self.field_map[tag].setText(value)

    def _on_field_changed(self) -> None:
        """Handle field editing finished - auto-save."""
        # Collect all field values
        values = {}
        for config in self.field_configs:
            widget = self.field_map.get(config.tag)
            if widget:
                values[config.tag] = widget.text()

        self.save_clicked.emit(values)
