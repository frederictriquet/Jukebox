"""Duplicate finder plugin."""

from typing import Any

from PySide6.QtWidgets import QDialog, QListWidget, QMessageBox, QPushButton, QVBoxLayout


class DuplicateFinderPlugin:
    """Find duplicate tracks."""

    name = "duplicate_finder"
    version = "1.0.0"
    description = "Find duplicate tracks"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

    def register_ui(self, ui_builder: Any) -> None:
        """Register UI."""
        menu = ui_builder.add_menu("&Tools")
        ui_builder.add_menu_action(menu, "Find Duplicates...", self._find_duplicates)

    def _find_duplicates(self) -> None:
        """Find duplicate tracks."""
        tracks = self.context.database.get_all_tracks()

        # Group by title+artist
        groups: dict[tuple[str, str], list[Any]] = {}
        for track in tracks:
            key = ((track["title"] or "").lower(), (track["artist"] or "").lower())
            if key not in groups:
                groups[key] = []
            groups[key].append(track)

        # Filter duplicates
        duplicates = {k: v for k, v in groups.items() if len(v) > 1}

        if not duplicates:
            QMessageBox.information(None, "No Duplicates", "No duplicate tracks found.")
            return

        # Show dialog
        dialog = DuplicateDialog(duplicates)
        dialog.exec()

    def shutdown(self) -> None:
        """Cleanup."""
        pass


class DuplicateDialog(QDialog):
    """Dialog to show duplicates."""

    def __init__(self, duplicates: dict[tuple[str, str], list[Any]]):
        """Initialize dialog."""
        super().__init__()
        self.duplicates = duplicates
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI."""
        self.setWindowTitle("Duplicate Tracks")
        self.resize(600, 400)

        layout = QVBoxLayout()

        self.list_widget = QListWidget()
        for (title, artist), tracks in self.duplicates.items():
            item_text = f"{artist} - {title} ({len(tracks)} copies)"
            self.list_widget.addItem(item_text)

        layout.addWidget(self.list_widget)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self.setLayout(layout)
