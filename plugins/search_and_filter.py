"""Search and filter plugin - unified management of search bar and genre filters.

This plugin manages genre filter buttons in a centralized way and installs a
proxy model on the track list for real-time filtering. It operates in two modes:

- **jukebox/curating modes**: genre buttons live in `genre_buttons_area` (below
  the search bar in the main layout), managed as `genre_buttons`.
- **cue_maker mode**: genre buttons live in the BottomDrawer, created on demand
  via `get_drawer_genre_buttons_container()` and tracked as `_drawer_buttons`.

In cue_maker mode, search and genre filtering are handled entirely by the
GenreFilterProxyModel — the database FTS5 is bypassed. This avoids the DB
returning 0 tracks when queried with mode="cue_maker".

Button state (ON/OFF/INDIFFERENT) is persisted across mode switches via the
`_genre_states` dict, which is updated by `_on_filter_changed()` and restored
when a new button set is created (toolbar or drawer).

Events:
- Subscribes to: TRACKS_ADDED
- Emits: GENRE_FILTER_CHANGED
"""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QSortFilterProxyModel
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

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
            filename = (track.get("filename") or "").lower()
            if (
                self._search_text not in artist
                and self._search_text not in title
                and self._search_text not in filename
            ):
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

    Maintains two independent sets of genre filter buttons:

    - ``genre_buttons`` / ``toolbar_container``: created once in ``register_ui``
      and placed in ``main_window.genre_buttons_area``. Used in jukebox and
      curating modes.
    - ``_drawer_buttons``: created on each call to
      ``get_drawer_genre_buttons_container()``, placed inside the cue_maker
      BottomDrawer. Automatically cleared when the drawer container is destroyed.

    Both sets share ``_genre_states`` (dict[code → GenreFilterState]) to persist
    button ON/OFF state across mode switches. ``_on_filter_changed()`` always reads
    from the *active* set (drawer when present, toolbar otherwise) and saves the
    resulting state back to ``_genre_states``.

    The ``GenreFilterProxyModel`` is installed once in ``register_ui`` and remains
    active for the lifetime of the plugin. In cue_maker mode it is the sole
    filtering mechanism (DB FTS5 is not used).

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
        # Toolbar button set — lives in genre_buttons_area (jukebox/curating modes)
        self.genre_buttons: list[GenreFilterButton] = []
        self.toolbar_container: QWidget | None = None
        # Drawer button set — created on demand for cue_maker BottomDrawer
        self._drawer_buttons: list[GenreFilterButton] = []
        # Persisted state across mode switches: {genre_code: GenreFilterState}
        self._genre_states: dict[str, GenreFilterState] = {}
        self._track_list: Any = None

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin with application context."""
        self.context = context
        context.subscribe(Events.TRACKS_ADDED, self._on_tracks_added)
        logging.info("[Search & Filter] Plugin initialized")

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register UI elements (proxy model, search connection, genre buttons below searchbar).

        Genre buttons with "Genres" label are created and added below the searchbar.
        """
        if not self.context:
            return

        # Create proxy model and install on track list
        self.proxy = GenreFilterProxyModel()
        main_window = ui_builder.main_window
        self._track_list = main_window.track_list
        self._track_list.set_proxy_model(self.proxy)

        # Connect search bar to proxy
        if hasattr(main_window, "search_bar"):
            main_window.search_bar.search_triggered.connect(self._on_search)

        # Create buttons container
        self._create_toolbar_buttons()

        # Add genre buttons to the genre_buttons_area placeholder in main_window
        if hasattr(main_window, "genre_buttons_area") and self.toolbar_container:
            area = main_window.genre_buttons_area
            area_layout = QVBoxLayout(area)
            area_layout.setContentsMargins(0, 0, 0, 0)
            area_layout.setSpacing(0)
            area_layout.addWidget(self.toolbar_container)
            area.setFixedHeight(30)  # Show area now that it has content
            logging.info("[Search & Filter] Added genre buttons to genre_buttons_area")

        logging.info("[Search & Filter] Registered with %d genre buttons", len(self.genre_buttons))

    def get_drawer_genre_buttons_container(self) -> QWidget:
        """Get a SEPARATE container with genre buttons for drawer.

        Creates a NEW set of buttons tracked in _drawer_buttons.
        Restores saved state from _genre_states for persistence across mode switches.
        When the container is destroyed, _drawer_buttons is auto-cleared.
        """
        if not self.context:
            return QWidget()

        config = self.context.config
        codes = config.genre_editor.codes
        sorted_codes = sorted(codes, key=lambda c: c.code)

        # Container with horizontal layout (label + NEW buttons on same line)
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Add "Genres" label
        label = QLabel("Genres")
        label.setStyleSheet("font-weight: bold; font-size: 12px; color: #aaa;")
        layout.addWidget(label)

        # Create NEW buttons tracked in _drawer_buttons
        self._drawer_buttons = []
        for code_config in sorted_codes:
            btn = GenreFilterButton(code_config.code, code_config.name)
            # Restore saved state
            if code_config.code in self._genre_states:
                btn.state = self._genre_states[code_config.code]
                btn._apply_style()
            btn.clicked.connect(self._on_filter_changed)
            self._drawer_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # Auto-clear drawer buttons when container is destroyed
        container.destroyed.connect(self._clear_drawer_buttons)

        return container

    def _create_toolbar_buttons(self) -> None:
        """Create genre filter buttons container (displayed below searchbar, not in toolbar)."""
        if not self.context or self.toolbar_container:
            return

        config = self.context.config
        codes = config.genre_editor.codes
        sorted_codes = sorted(codes, key=lambda c: c.code)

        # Container with horizontal layout (label + buttons on same line)
        self.toolbar_container = QWidget()
        layout = QHBoxLayout(self.toolbar_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Add "Genres" label
        label = QLabel("Genres")
        label.setStyleSheet("font-weight: bold; font-size: 12px; color: #aaa;")
        layout.addWidget(label)

        # Genre buttons
        for code_config in sorted_codes:
            btn = GenreFilterButton(code_config.code, code_config.name)
            btn.clicked.connect(self._on_filter_changed)
            self.genre_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

    def _on_search(self, text: str) -> None:
        """Handle search text change from main search bar."""
        if self.proxy:
            self.proxy.set_search_text(text)

    def _on_filter_changed(self) -> None:
        """Handle genre filter button change."""
        on_genres: set[str] = set()
        off_genres: set[str] = set()

        # Use drawer buttons when they exist (cue_maker mode), otherwise toolbar buttons
        active_buttons = self._drawer_buttons if self._drawer_buttons else self.genre_buttons

        for btn in active_buttons:
            if btn.state == GenreFilterState.ON:
                on_genres.add(btn.code)
            elif btn.state == GenreFilterState.OFF:
                off_genres.add(btn.code)

        # Save state for persistence across mode switches
        self._genre_states = {btn.code: btn.state for btn in active_buttons}

        if self.proxy:
            self.proxy.set_genre_filter(on_genres, off_genres)

        if self.context:
            self.context.emit(
                Events.GENRE_FILTER_CHANGED,
                on_genres=on_genres,
                off_genres=off_genres,
            )

    def _clear_drawer_buttons(self) -> None:
        """Clear drawer buttons reference (called when drawer container is destroyed)."""
        self._drawer_buttons = []

    def _on_tracks_added(self) -> None:
        """Re-invalidate filter when tracks change."""
        if self.proxy:
            self.proxy.invalidateFilter()

    def activate(self, mode: str) -> None:
        """Activate plugin for the given mode.

        Restores genre button states from ``_genre_states`` (for toolbar buttons)
        and re-applies the current filter to the proxy model. In cue_maker mode,
        drawer buttons are created by the cue_maker plugin calling
        ``get_drawer_genre_buttons_container()`` — this method only handles the
        toolbar button set.
        """
        # Create buttons if needed
        if not self.toolbar_container and self.context:
            self._create_toolbar_buttons()

        # Restore saved genre button states on toolbar buttons
        for btn in self.genre_buttons:
            if btn.code in self._genre_states:
                btn.state = self._genre_states[btn.code]
                btn._apply_style()

        # Re-apply current filter
        self._on_filter_changed()
        logging.info("[Search & Filter] Activated for %s mode", mode)

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for the given mode.

        Resets the proxy filter so all tracks remain visible during the mode
        transition. Genre button states are preserved in ``_genre_states`` and
        will be restored when the plugin is re-activated.
        """
        # Clear filter so all tracks are visible during transition
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
