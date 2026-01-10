"""Metadata editor plugin."""

from typing import Any

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QLineEdit, QWidget


class TabEventFilter(QObject):
    """Event filter to capture TAB key within metadata editor."""

    def __init__(self, metadata_widget: "MetadataEditorWidget"):
        """Initialize event filter."""
        super().__init__()
        self.metadata_widget = metadata_widget

    def eventFilter(self, obj: Any, event: Any) -> bool:  # noqa: N802
        """Filter events to handle TAB within metadata editor."""
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtWidgets import QApplication

        if event.type() == QEvent.Type.KeyPress:
            # Get the widget that currently has focus
            focused_widget = QApplication.focusWidget()

            if event.key() == Qt.Key.Key_Tab:
                # Check if current focus is within metadata editor fields
                if focused_widget in self.metadata_widget.editable_fields:
                    # Already in metadata fields
                    current_index = self.metadata_widget.editable_fields.index(focused_widget)

                    # If on last field, clear focus (triggers save)
                    if current_index == len(self.metadata_widget.editable_fields) - 1:
                        focused_widget.clearFocus()
                        return True  # Block TAB from propagating
                    else:
                        # Go to next field
                        next_index = current_index + 1
                        self.metadata_widget.editable_fields[next_index].setFocus()
                        return True  # Block TAB from propagating
                else:
                    # Not in metadata fields, go to first field (Artist)
                    self.metadata_widget.editable_fields[0].setFocus()
                    return True  # Block TAB from propagating

            elif (
                event.key() == Qt.Key.Key_Backtab
                and focused_widget in self.metadata_widget.editable_fields
            ):
                # Shift+Tab: go backwards
                current_index = self.metadata_widget.editable_fields.index(focused_widget)
                prev_index = (current_index - 1) % len(self.metadata_widget.editable_fields)
                self.metadata_widget.editable_fields[prev_index].setFocus()
                return True  # Block Shift+TAB from propagating

        return False  # Let other events continue


class MetadataEditorPlugin:
    """Edit track metadata for currently playing track."""

    name = "metadata_editor"
    version = "1.0.0"
    description = "Edit track metadata (artist, title, album)"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None
        self.editor_widget: MetadataEditorWidget | None = None
        self.current_track_id: int | None = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to track loaded event
        from jukebox.core.event_bus import Events

        context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)

    def register_ui(self, ui_builder: Any) -> None:
        """Register metadata editor widget."""
        self.editor_widget = MetadataEditorWidget()
        self.editor_widget.save_clicked.connect(self._on_save_metadata)

        # Add below player controls in main layout
        ui_builder.add_bottom_widget(self.editor_widget)

    def _on_track_loaded(self, track_id: int) -> None:
        """Handle track loaded event."""
        if not self.editor_widget:
            return

        self.current_track_id = track_id

        # Get track metadata from database
        track = self.context.database.conn.execute(
            """SELECT artist, title, album, album_artist, genre, year
               FROM tracks WHERE id = ?""",
            (track_id,),
        ).fetchone()

        if track:
            self.editor_widget.set_metadata(
                artist=track["artist"] or "",
                title=track["title"] or "",
                album=track["album"] or "",
                album_artist=track["album_artist"] or "",
                genre=track["genre"] or "",
                year=str(track["year"]) if track["year"] else "",
            )

    def _on_save_metadata(
        self, artist: str, title: str, album: str, album_artist: str, genre: str, year: str
    ) -> None:
        """Save metadata to database and file tags."""
        if self.current_track_id is None:
            return

        # Get filepath from database
        track = self.context.database.conn.execute(
            "SELECT filepath FROM tracks WHERE id = ?", (self.current_track_id,)
        ).fetchone()

        if not track:
            return

        filepath = track["filepath"]

        # Convert year to int or None
        year_int = int(year) if year.isdigit() else None

        # Update database
        self.context.database.conn.execute(
            """UPDATE tracks
               SET artist = ?, title = ?, album = ?, album_artist = ?, genre = ?, year = ?
               WHERE id = ?""",
            (artist, title, album, album_artist, genre, year_int, self.current_track_id),
        )
        self.context.database.conn.commit()

        # Update file tags using mutagen
        try:
            from pathlib import Path

            import mutagen
            from mutagen.easyid3 import EasyID3

            file_path = Path(filepath)
            extension = file_path.suffix.lower()

            # Sanitize and limit tag values (max 500 chars per field)
            max_tag_length = 500

            def sanitize_tag(value: str) -> str:
                """Sanitize tag value - limit length and strip problematic chars."""
                if not value:
                    return ""
                # Limit length
                value = value[:max_tag_length]
                # Strip null bytes and control chars
                value = "".join(char for char in value if ord(char) >= 32 or char in "\n\t")
                return value.strip()

            # Sanitize all values
            artist = sanitize_tag(artist)
            title = sanitize_tag(title)
            album = sanitize_tag(album)
            album_artist = sanitize_tag(album_artist)
            genre = sanitize_tag(genre)
            year = sanitize_tag(year)

            # Use EasyID3 for MP3 files (simpler API)
            if extension == ".mp3":
                try:
                    audio = EasyID3(filepath)
                except mutagen.id3.ID3NoHeaderError:
                    # No tags yet, add them
                    audio = mutagen.File(filepath, easy=True)
                    audio.add_tags()

                if artist:
                    audio["artist"] = [artist]
                if title:
                    audio["title"] = [title]
                if album:
                    audio["album"] = [album]
                if album_artist:
                    audio["albumartist"] = [album_artist]
                if genre:
                    audio["genre"] = [genre]
                if year:
                    audio["date"] = [year]

                audio.save()

            elif extension in [".flac", ".aiff", ".aif", ".wav"]:
                # Use mutagen.File for FLAC and other formats
                audio = mutagen.File(filepath)
                if audio is not None:
                    if artist:
                        audio["artist"] = [artist]
                    if title:
                        audio["title"] = [title]
                    if album:
                        audio["album"] = [album]
                    if album_artist:
                        audio["albumartist"] = [album_artist]
                    if genre:
                        audio["genre"] = [genre]
                    if year:
                        audio["date"] = [year]

                    audio.save()

        except Exception as e:
            import logging

            logging.error(f"Failed to write tags to file {filepath}: {e}")

        # Update track list display
        main_window = self.context.app
        if hasattr(main_window, "_load_tracks_from_db"):
            main_window._load_tracks_from_db()

    def register_shortcuts(self, shortcut_manager: Any) -> None:
        """Register keyboard shortcuts."""
        pass

    def shutdown(self) -> None:
        """Cleanup."""
        pass


class MetadataEditorWidget(QWidget):
    """Widget to edit track metadata."""

    from PySide6.QtCore import Signal

    save_clicked = Signal(str, str, str, str, str, str)  # artist, title, album, album_artist, genre, year

    def __init__(self) -> None:
        """Initialize widget."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI."""
        layout = QGridLayout()
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(5)

        # Artist
        layout.addWidget(QLabel("Artist:"), 0, 0)
        self.artist_edit = QLineEdit()
        layout.addWidget(self.artist_edit, 0, 1)

        # Title
        layout.addWidget(QLabel("Title:"), 0, 2)
        self.title_edit = QLineEdit()
        layout.addWidget(self.title_edit, 0, 3)

        # Album
        layout.addWidget(QLabel("Album:"), 1, 0)
        self.album_edit = QLineEdit()
        layout.addWidget(self.album_edit, 1, 1)

        # Album Artist
        layout.addWidget(QLabel("Album Artist:"), 1, 2)
        self.album_artist_edit = QLineEdit()
        layout.addWidget(self.album_artist_edit, 1, 3)

        # Genre
        layout.addWidget(QLabel("Genre:"), 2, 0)
        self.genre_edit = QLineEdit()
        layout.addWidget(self.genre_edit, 2, 1)

        # Year
        layout.addWidget(QLabel("Year:"), 2, 2)
        self.year_edit = QLineEdit()
        self.year_edit.setMaximumWidth(80)
        layout.addWidget(self.year_edit, 2, 3, alignment=Qt.AlignmentFlag.AlignLeft)

        self.setLayout(layout)
        self.setMaximumHeight(100)

        # Store all editable fields for tab cycling
        self.editable_fields = [
            self.artist_edit,
            self.title_edit,
            self.album_edit,
            self.album_artist_edit,
            self.genre_edit,
            self.year_edit,
        ]

        # Connect editingFinished to auto-save
        self.artist_edit.editingFinished.connect(self._on_field_changed)
        self.title_edit.editingFinished.connect(self._on_field_changed)
        self.album_edit.editingFinished.connect(self._on_field_changed)
        self.album_artist_edit.editingFinished.connect(self._on_field_changed)
        self.genre_edit.editingFinished.connect(self._on_field_changed)
        self.year_edit.editingFinished.connect(self._on_field_changed)

        # Set tab order within widget
        self.setTabOrder(self.artist_edit, self.title_edit)
        self.setTabOrder(self.title_edit, self.album_edit)
        self.setTabOrder(self.album_edit, self.album_artist_edit)
        self.setTabOrder(self.album_artist_edit, self.genre_edit)
        self.setTabOrder(self.genre_edit, self.year_edit)
        self.setTabOrder(self.year_edit, self.artist_edit)  # Loop back

        # Install event filter on application to capture TAB
        from PySide6.QtWidgets import QApplication

        self.tab_filter = TabEventFilter(self)
        app = QApplication.instance()
        if app:
            app.installEventFilter(self.tab_filter)

    def set_metadata(
        self, artist: str, title: str, album: str, album_artist: str, genre: str, year: str
    ) -> None:
        """Set metadata values in fields."""
        self.artist_edit.setText(artist)
        self.title_edit.setText(title)
        self.album_edit.setText(album)
        self.album_artist_edit.setText(album_artist)
        self.genre_edit.setText(genre)
        self.year_edit.setText(year)

    def _on_field_changed(self) -> None:
        """Handle field editing finished - auto-save."""
        self.save_clicked.emit(
            self.artist_edit.text(),
            self.title_edit.text(),
            self.album_edit.text(),
            self.album_artist_edit.text(),
            self.genre_edit.text(),
            self.year_edit.text(),
        )
