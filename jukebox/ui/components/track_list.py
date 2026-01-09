"""Track list widget."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem


class TrackList(QListWidget):
    """Widget for displaying audio tracks."""

    track_selected = Signal(Path)

    def __init__(self, parent=None):  # type: ignore
        """Initialize track list.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

    def add_track(
        self, filepath: Path, title: str | None = None, artist: str | None = None
    ) -> None:
        """Add a track to the list.

        Args:
            filepath: Path to audio file
            title: Track title (optional)
            artist: Track artist (optional)
        """
        # Format display text
        if title and artist:
            display = f"{artist} - {title}"
        elif title:
            display = title
        else:
            display = filepath.name

        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, filepath)
        item.setToolTip(str(filepath))
        self.addItem(item)

    def add_tracks(self, filepaths: list[Path]) -> None:
        """Add multiple tracks.

        Args:
            filepaths: List of paths to audio files
        """
        for filepath in filepaths:
            self.add_track(filepath)

    def clear_tracks(self) -> None:
        """Clear all tracks."""
        self.clear()

    def get_selected_track(self) -> Path | None:
        """Get currently selected track.

        Returns:
            Path to selected track or None
        """
        current = self.currentItem()
        if current:
            data = current.data(Qt.ItemDataRole.UserRole)
            return Path(data) if data is not None else None
        return None

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle track double-click.

        Args:
            item: Clicked list item
        """
        filepath = item.data(Qt.ItemDataRole.UserRole)
        if filepath:
            self.track_selected.emit(filepath)
