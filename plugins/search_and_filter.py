"""Search and filter plugin - unified management of search bar and genre filters.

This plugin manages genre filter buttons in a centralized way. The buttons can be
placed either in the toolbar (jukebox mode) or in the drawer with the search bar
(cue_maker mode), through a unified API.

The search bar is provided by MainWindow. This plugin:
- Manages genre filter buttons
- Provides filter proxy model for searching + genre filtering
- Offers get_container() method for flexible placement

Events:
- Subscribes to: TRACKS_ADDED
- Emits: GENRE_FILTER_CHANGED
"""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from jukebox.core.event_bus import Events

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol


class GenreFilterState(IntEnum):
    """State of a genre filter button."""

    INDIFFERENT = 0
    ON = 1
    OFF = 2


class GenreFilterProxyModel(QSortFilterProxyModel):
    """Proxy model that filters tracks by genre and search."""

    def __init__(self, parent: Any = None) -> None:
        """Initialize the proxy model."""
        super().__init__(parent)
        self._on_genres: set[str] = set()
        self._off_genres: set[str] = set()
        self._search_text: str = ""

    def set_search_text(self, text: str) -> None:
        """Set the search text filter."""
        self._search_text = text.lower()
        self.invalidateFilter()

    def set_genre_filter(self, on_genres: set[str], off_genres: set[str]) -> None:
        """Set the genre filter."""
        self._on_genres = on_genres
        self._off_genres = off_genres
        self.invalidateFilter()

    def filterAcceptsRow(  # noqa: N802
        self,
        source_row: int,
        source_parent: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        """Check if a row passes both search and genre filters."""
        source_model = self.sourceModel()
        if source_model is None:
            return True

        tracks: list[dict[str, Any]] = getattr(source_model, "tracks", [])
        if source_row >= len(tracks):
            return True

        track = tracks[source_row]

        # Search filter
        if self._search_text:
            artist = (track.get("artist") or "").lower()
            title = (track.get("title") or "").lower()
            if self._search_text not in artist and self._search_text not in title:
                return False

        # Genre filter
        if not self._on_genres and not self._off_genres:
            return True

        genre_str = track.get("genre", "") or ""
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


class GenreFilterButton(QPushButton):
    """Button that cycles through indifferent/on/off states."""

    _STYLES = {
        GenreFilterState.INDIFFERENT: (
            "background-color: #555; color: #aaa; font-weight: bold; font-size: 13px;"
        ),
        GenreFilterState.ON: (
            "background-color: #2d7a2d; color: white; font-weight: bold; font-size: 13px;"
        ),
        GenreFilterState.OFF: (
            "background-color: #7a2d2d; color: white; font-weight: bold; font-size: 13px;"
        ),
    }

    def __init__(self, code: str, name: str, parent: Any = None) -> None:
        """Initialize a genre filter button."""
        super().__init__(code, parent)
        self.code = code
        self.genre_name = name
        self.state = GenreFilterState.INDIFFERENT
        self.setFixedSize(32, 26)
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


class SearchAndFilterPlugin:
    """Centralized search and genre filter plugin.

    Manages genre filter buttons with unified control. Provides both:
    - Buttons for toolbar (jukebox/curating modes)
    - Buttons for drawer (cue_maker mode)

    The search bar is managed by MainWindow. This plugin syncs the search
    text with genre filtering in the proxy model.

    Active in: jukebox, cue_maker modes
    """

    name = "search_and_filter"
    version = "1.0.0"
    description = "Centralized search and genre filter management"
    modes = ["jukebox", "cue_maker"]

    def __init__(self) -> None:
        """Initialize plugin state."""
        self.context: PluginContextProtocol | None = None
        self.proxy: GenreFilterProxyModel | None = None
        self.genre_buttons: list[GenreFilterButton] = []
        self.toolbar_container: QWidget | None = None
        self._track_list: Any = None
        self._toolbar: Any = None  # Reference to the toolbar for removal/re-addition

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin with application context."""
        self.context = context
        context.subscribe(Events.TRACKS_ADDED, self._on_tracks_added)
        logging.info("[Search & Filter] Plugin initialized")

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register UI elements (genre buttons in toolbar)."""
        if not self.context:
            return

        # Create genre buttons in toolbar
        self._create_toolbar_buttons()
        ui_builder.add_toolbar_widget(self.toolbar_container)

        # Store reference to toolbar for later manipulation (hiding/removing)
        main_window = ui_builder.main_window
        if hasattr(main_window, "_plugin_toolbar"):
            self._toolbar = main_window._plugin_toolbar
            logging.debug("[Search & Filter] Stored toolbar reference")

        # Create proxy model and install on track list
        self.proxy = GenreFilterProxyModel()
        self._track_list = ui_builder.main_window.track_list
        self._track_list.set_proxy_model(self.proxy)

        # Connect search bar to proxy (search bar exists in main_window)
        if hasattr(main_window, "search_bar"):
            main_window.search_bar.search_triggered.connect(self._on_search)

        logging.info(
            "[Search & Filter] Registered with %d genre buttons", len(self.genre_buttons)
        )

    def _create_toolbar_buttons(self) -> None:
        """Create genre filter buttons for toolbar."""
        if not self.context or self.toolbar_container:
            return

        config = self.context.config
        codes = config.genre_editor.codes
        sorted_codes = sorted(codes, key=lambda c: c.code)

        # Container
        self.toolbar_container = QWidget()
        layout = QHBoxLayout(self.toolbar_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Genre buttons
        for code_config in sorted_codes:
            btn = GenreFilterButton(code_config.code, code_config.name)
            btn.clicked.connect(self._on_filter_changed)
            self.genre_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

    def get_button_container(self) -> QWidget:
        """Get a container with genre filter buttons (for drawer or other layouts).

        Returns a NEW container with copies of the button logic, not the toolbar buttons.
        """
        if not self.context:
            return QWidget()

        config = self.context.config
        codes = config.genre_editor.codes
        sorted_codes = sorted(codes, key=lambda c: c.code)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Create buttons
        for code_config in sorted_codes:
            btn = GenreFilterButton(code_config.code, code_config.name)
            btn.clicked.connect(self._on_filter_changed)
            layout.addWidget(btn)

        layout.addStretch()
        return container

    def _on_search(self, text: str) -> None:
        """Handle search text change from main search bar."""
        if self.proxy:
            self.proxy.set_search_text(text)

    def _on_filter_changed(self) -> None:
        """Handle genre filter button change."""
        on_genres: set[str] = set()
        off_genres: set[str] = set()

        # Collect state from ALL buttons (both toolbar and any other instances)
        for btn in self.genre_buttons:
            if btn.state == GenreFilterState.ON:
                on_genres.add(btn.code)
            elif btn.state == GenreFilterState.OFF:
                off_genres.add(btn.code)

        if self.proxy:
            self.proxy.set_genre_filter(on_genres, off_genres)

        if self.context:
            self.context.emit(
                Events.GENRE_FILTER_CHANGED,
                on_genres=on_genres,
                off_genres=off_genres,
            )

    def _on_tracks_added(self) -> None:
        """Re-invalidate filter when tracks change."""
        if self.proxy:
            self.proxy.invalidateFilter()

    def activate(self, mode: str) -> None:
        """Activate plugin for the given mode."""
        # Create buttons if needed
        if not self.toolbar_container and self.context:
            self._create_toolbar_buttons()

        # Show/hide toolbar buttons based on mode
        # In cue_maker mode, buttons are shown in drawer instead (not toolbar)
        if self.toolbar_container:
            if mode == "cue_maker":
                # REMOVE the container from toolbar completely
                # This removes it from the widget hierarchy, making it invisible
                if self.toolbar_container.parent():
                    self.toolbar_container.setParent(None)
                    logging.info(
                        "[Search & Filter] Removed toolbar buttons from toolbar for %s mode", mode
                    )
            else:
                # Re-add the container to toolbar for other modes (jukebox, curating)
                # If it was removed, re-add it to the toolbar
                if self._toolbar and not self.toolbar_container.parent():
                    self._toolbar.addWidget(self.toolbar_container)
                    logging.info(
                        "[Search & Filter] Re-added toolbar buttons to toolbar for %s mode", mode
                    )
                # Ensure visibility
                self.toolbar_container.setVisible(True)

        # Re-apply current filter
        self._on_filter_changed()
        logging.info("[Search & Filter] Activated for %s mode", mode)

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin."""
        # Note: deactivate() is called when LEAVING a mode
        # If leaving cue_maker → we're going to jukebox/curating, so buttons should be shown
        # This is handled by activate() of the new mode, not here

        # Clear filter so all tracks are visible
        if self.proxy:
            self.proxy.set_genre_filter(set(), set())
            self.proxy.set_search_text("")
        logging.info("[Search & Filter] Deactivated from %s mode", mode)

    def shutdown(self) -> None:
        """Cleanup resources."""
        if self._track_list:
            self._track_list.remove_proxy_model()
        self._track_list = None
        self.proxy = None
        self.genre_buttons.clear()
