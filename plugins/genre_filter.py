"""Genre filter plugin - filter tracks by genre in jukebox mode."""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from jukebox.core.event_bus import Events

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol


class GenreFilterState(IntEnum):
    """State of a genre filter button."""

    INDIFFERENT = 0
    ON = 1
    OFF = 2


class GenreFilterProxyModel(QSortFilterProxyModel):
    """Proxy model that filters tracks by genre."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._on_genres: set[str] = set()
        self._off_genres: set[str] = set()

    def set_filter(self, on_genres: set[str], off_genres: set[str]) -> None:
        """Update the genre filter and refresh.

        Args:
            on_genres: Genres that must be present
            off_genres: Genres that must be absent
        """
        self._on_genres = on_genres
        self._off_genres = off_genres
        self.invalidateFilter()

    def filterAcceptsRow(  # noqa: N802
        self,
        source_row: int,
        source_parent: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        """Check if a row passes the genre filter."""
        if not self._on_genres and not self._off_genres:
            return True

        source_model = self.sourceModel()
        if source_model is None:
            return True

        # Access tracks list on TrackListModel
        tracks: list[dict[str, Any]] = getattr(source_model, "tracks", [])
        if source_row >= len(tracks):
            return True

        track = tracks[source_row]
        genre_str = track.get("genre", "") or ""

        # Parse genre codes: e.g. "H-W-*3" → {"H", "W"}
        track_genres = set()
        for part in genre_str.split("-"):
            code = part.strip()
            if code and not code.startswith("*"):
                track_genres.add(code)

        # ON filter: track must contain ALL on_genres
        for g in self._on_genres:
            if g not in track_genres:
                return False

        # OFF filter: track must NOT contain any off_genres
        return all(g not in track_genres for g in self._off_genres)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Override vertical header to show proxy row numbers."""
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Vertical
        ):
            return f"{section + 1}/{self.rowCount()}"
        return super().headerData(section, orientation, role)


class GenreFilterButton(QPushButton):
    """Button that cycles between indifferent/on/off states."""

    _STYLES = {
        GenreFilterState.INDIFFERENT: "background-color: #555; color: #aaa;",
        GenreFilterState.ON: "background-color: #2d7a2d; color: white;",
        GenreFilterState.OFF: "background-color: #7a2d2d; color: white;",
    }

    def __init__(self, code: str, name: str, parent: Any = None) -> None:
        super().__init__(code, parent)
        self.code = code
        self.genre_name = name
        self.state = GenreFilterState.INDIFFERENT
        self.setFixedSize(28, 22)
        self.setToolTip(name)
        self._apply_style()
        self.clicked.connect(self._cycle)

    def _cycle(self) -> None:
        """Cycle state: indifferent → on → off → indifferent."""
        self.state = GenreFilterState((self.state + 1) % 3)
        self._apply_style()

    def _apply_style(self) -> None:
        """Apply style for current state."""
        self.setStyleSheet(self._STYLES[self.state])


class GenreFilterPlugin:
    """Genre filter plugin for jukebox mode."""

    name = "genre_filter"
    version = "1.0.0"
    description = "Filter tracks by genre with toggle buttons"
    modes = ["jukebox"]

    def __init__(self) -> None:
        self.context: PluginContextProtocol | None = None
        self.proxy: GenreFilterProxyModel | None = None
        self.buttons: list[GenreFilterButton] = []
        self.container: QWidget | None = None

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin."""
        self.context = context
        context.subscribe(Events.TRACKS_ADDED, self._on_tracks_added)

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register filter buttons in toolbar."""
        if not self.context:
            return

        config = self.context.config
        codes = config.genre_editor.codes

        # Sort codes alphabetically by code letter
        sorted_codes = sorted(codes, key=lambda c: c.code)

        # Create container widget
        self.container = QWidget()
        layout = QHBoxLayout(self.container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Create one button per genre code
        for code_config in sorted_codes:
            btn = GenreFilterButton(code_config.code, code_config.name)
            btn.clicked.connect(self._on_filter_changed)
            self.buttons.append(btn)
            layout.addWidget(btn)

        ui_builder.add_toolbar_widget(self.container)

        # Create proxy model and install it on the track list
        self.proxy = GenreFilterProxyModel()
        track_list = ui_builder.main_window.track_list
        track_list.set_proxy_model(self.proxy)

        logging.info(f"[Genre Filter] Registered {len(self.buttons)} filter buttons")

    def _on_filter_changed(self) -> None:
        """Collect button states and update the proxy filter."""
        on_genres: set[str] = set()
        off_genres: set[str] = set()

        for btn in self.buttons:
            if btn.state == GenreFilterState.ON:
                on_genres.add(btn.code)
            elif btn.state == GenreFilterState.OFF:
                off_genres.add(btn.code)

        if self.proxy:
            self.proxy.set_filter(on_genres, off_genres)

        if self.context:
            self.context.emit(
                Events.GENRE_FILTER_CHANGED,
                on_genres=on_genres,
                off_genres=off_genres,
            )

    def _on_tracks_added(self) -> None:
        """Re-invalidate the filter when tracks change."""
        if self.proxy:
            self.proxy.invalidateFilter()

    def activate(self, mode: str) -> None:
        """Activate plugin for this mode."""
        if self.container:
            self.container.setVisible(True)
        # Re-apply current filter
        self._on_filter_changed()
        logging.debug(f"[Genre Filter] Activated for {mode} mode")

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for this mode."""
        if self.container:
            self.container.setVisible(False)
        # Clear filter so all tracks are visible
        if self.proxy:
            self.proxy.set_filter(set(), set())
        logging.debug(f"[Genre Filter] Deactivated for {mode} mode")

    def shutdown(self) -> None:
        """Cleanup on plugin unload."""
        if self.context:
            track_list = self.context.app.track_list
            track_list.remove_proxy_model()
        self.proxy = None
        self.buttons.clear()
