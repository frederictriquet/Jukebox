"""Genre filter plugin - filter tracks by genre in jukebox mode.

This plugin adds a toolbar with toggle buttons (one per genre code) that allow
filtering the track list by genre in jukebox mode. Each button has three states:
- INDIFFERENT (gray): genre not considered in filtering
- ON (green): tracks must have this genre
- OFF (red): tracks must NOT have this genre

The filtering uses a QSortFilterProxyModel that intercepts between the source
TrackListModel and the view, making filtering transparent for navigation, random
selection, and track count operations.

Usage:
    Enable the plugin in config/config.yaml under plugins.enabled:
        plugins:
          enabled:
            - genre_filter

    The plugin activates automatically when switching to jukebox mode.
    Click genre buttons to cycle through states and filter the track list.

Architecture:
    - GenreFilterProxyModel: Qt proxy model that implements the filtering logic
    - GenreFilterButton: Custom button widget with 3-state cycling
    - GenreFilterPlugin: Plugin entry point and lifecycle manager

Events:
    - Subscribes to: TRACKS_ADDED (to re-apply filter on list changes)
    - Emits: GENRE_FILTER_CHANGED (when filter state changes)
"""

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
    """State of a genre filter button.

    Attributes:
        INDIFFERENT: Genre is not considered in filtering (gray button)
        ON: Tracks must have this genre (green button)
        OFF: Tracks must NOT have this genre (red button)
    """

    INDIFFERENT = 0
    ON = 1
    OFF = 2


class GenreFilterProxyModel(QSortFilterProxyModel):
    """Proxy model that filters tracks by genre.

    This proxy model sits between the TrackListModel and the QTableView,
    filtering rows based on genre codes. It implements Qt's filtering protocol
    via filterAcceptsRow() and automatically updates when set_filter() is called.

    The filtering logic:
    - ON genres (green buttons): Track must contain ALL of these genres (AND logic)
    - OFF genres (red buttons): Track must NOT contain ANY of these genres (exclusion)
    - INDIFFERENT genres (gray buttons): Not considered in filtering

    Genre parsing:
    - Parses genre strings like "H-W-*3" into genre codes {"H", "W"}
    - Ignores rating stars (parts starting with *)
    - Handles empty/None genres gracefully
    """

    def __init__(self, parent: Any = None) -> None:
        """Initialize the proxy model with empty filter sets.

        Args:
            parent: Optional Qt parent object
        """
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
        """Check if a row passes the genre filter.

        Qt calls this method for each row to determine visibility.

        Args:
            source_row: Row index in the source model
            source_parent: Parent index (unused for flat lists)

        Returns:
            True if the row should be visible, False to hide it

        Filter logic:
            - If no filters active: accept all
            - For ON genres: track must have ALL of them
            - For OFF genres: track must have NONE of them
            - Edge cases (empty genre, out of bounds): accept
        """
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
        """Override vertical header to show proxy row numbers.

        Displays "N/Total" in row headers to show filtered position.

        Args:
            section: Row or column index
            orientation: Horizontal (columns) or Vertical (rows)
            role: Qt data role (DisplayRole, etc.)

        Returns:
            Header data (e.g., "3/15" for 3rd visible row of 15 total)
        """
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Vertical:
            return f"{section + 1}/{self.rowCount()}"
        return super().headerData(section, orientation, role)


class GenreFilterButton(QPushButton):
    """Button that cycles between indifferent/on/off states.

    A compact toggle button that displays a genre code letter and cycles
    through three states on click:
        INDIFFERENT (gray) → ON (green) → OFF (red) → INDIFFERENT

    Visual design:
    - Size: 28x22 pixels (compact for toolbar)
    - Label: Single letter genre code (e.g., "H", "T", "W")
    - Tooltip: Full genre name (e.g., "House", "Trance", "Weed")
    - Colors: Gray (indifferent), Green (on), Red (off)
    """

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
        """Initialize a genre filter button.

        Args:
            code: Single-letter genre code (displayed on button)
            name: Full genre name (displayed in tooltip)
            parent: Optional Qt parent widget
        """
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


class GenreFilterPlugin:
    """Genre filter plugin for jukebox mode.

    This plugin provides interactive genre filtering via toolbar buttons.
    It's active only in jukebox mode and uses a QSortFilterProxyModel to
    filter the track list without modifying the underlying data.

    Plugin lifecycle:
    1. initialize(): Subscribe to TRACKS_ADDED events
    2. register_ui(): Create buttons and install proxy model
    3. activate(): Show buttons and re-apply filter (on mode switch)
    4. deactivate(): Hide buttons and clear filter (on mode switch)
    5. shutdown(): Remove proxy and cleanup resources

    Integration:
    - Works transparently with search, navigation, and random selection
    - Filter state persists during mode switches
    - Emits GENRE_FILTER_CHANGED event for other plugins

    Configuration:
        Reads genre codes from config.genre_editor.codes
        Must be enabled in config/config.yaml under plugins.enabled
    """

    name = "genre_filter"
    version = "1.0.0"
    description = "Filter tracks by genre with toggle buttons"
    modes = ["jukebox", "cue_maker"]

    def __init__(self) -> None:
        """Initialize plugin state (all None/empty until register_ui)."""
        self.context: PluginContextProtocol | None = None
        self.proxy: GenreFilterProxyModel | None = None
        self.buttons: list[GenreFilterButton] = []
        self.container: QWidget | None = None
        self._track_list: Any = None

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin with application context.

        Called once when the plugin is loaded by PluginManager.

        Args:
            context: Provides access to database, player, config, event_bus
        """
        self.context = context
        context.subscribe(Events.TRACKS_ADDED, self._on_tracks_added)

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register filter buttons in toolbar and install proxy model.

        Creates one button per genre code (from config), sorted alphabetically.
        Installs a GenreFilterProxyModel on the track list to enable filtering.

        Args:
            ui_builder: API for adding UI elements to main window
        """
        if not self.context:
            return

        # Create the container widget with buttons
        self._create_container()

        # Add container to toolbar
        ui_builder.add_toolbar_widget(self.container)

        # Create proxy model and install it on the track list
        self.proxy = GenreFilterProxyModel()
        self._track_list = ui_builder.main_window.track_list
        self._track_list.set_proxy_model(self.proxy)

        logging.info("[Genre Filter] Registered %d filter buttons", len(self.buttons))

    def _create_container(self) -> None:
        """Create the filter buttons container widget for the toolbar.

        Creates one button per genre code (from config), sorted alphabetically.
        """
        if not self.context or self.container:
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

    def _make_button_container(self, on_filter_changed_callback: Any) -> QWidget:
        """Create a button container widget that can be reused.

        This method creates a container with genre filter buttons that are
        connected to the provided callback. It can be used to create buttons
        for the toolbar or for other layouts (e.g., drawer).

        Args:
            on_filter_changed_callback: Callback to connect to button clicks

        Returns:
            QWidget container with genre filter buttons
        """
        if not self.context:
            return QWidget()

        config = self.context.config
        codes = config.genre_editor.codes

        # Sort codes alphabetically by code letter
        sorted_codes = sorted(codes, key=lambda c: c.code)

        # Create container widget
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Create one button per genre code
        for code_config in sorted_codes:
            btn = GenreFilterButton(code_config.code, code_config.name)
            btn.clicked.connect(on_filter_changed_callback)
            layout.addWidget(btn)

        return container

    def _make_button_container(self, on_filter_changed_callback: Any) -> QWidget:
        """Create a button container widget that can be reused.

        This method creates a container with genre filter buttons that are
        connected to the provided callback. It can be used to create buttons
        for the toolbar or for other layouts (e.g., drawer).

        Args:
            on_filter_changed_callback: Callback to connect to button clicks

        Returns:
            QWidget container with genre filter buttons
        """
        if not self.context:
            return QWidget()

        config = self.context.config
        codes = config.genre_editor.codes

        # Sort codes alphabetically by code letter
        sorted_codes = sorted(codes, key=lambda c: c.code)

        # Create container widget
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Create one button per genre code
        for code_config in sorted_codes:
            btn = GenreFilterButton(code_config.code, code_config.name)
            btn.clicked.connect(on_filter_changed_callback)
            layout.addWidget(btn)

        # Add stretch to keep buttons left-aligned in wider layouts
        layout.addStretch()

        return container

    def _on_filter_changed(self) -> None:
        """Collect button states and update the proxy filter.

        Called when any genre button is clicked. Scans all buttons,
        collects ON and OFF genres, updates the proxy model, and emits
        GENRE_FILTER_CHANGED event for other plugins.
        """
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
        """Re-invalidate the filter when tracks change.

        Event handler for TRACKS_ADDED. Forces the proxy model to
        re-evaluate all rows with the current filter criteria.
        """
        if self.proxy:
            self.proxy.invalidateFilter()

    def activate(self, mode: str) -> None:
        """Activate plugin when switching to jukebox or cue_maker mode.

        In cue_maker mode: removes buttons from toolbar (shown in drawer instead).
        In jukebox/curating mode: adds buttons back to toolbar.
        Re-applies the current filter state.

        Args:
            mode: Mode name ("jukebox" or "cue_maker")
        """
        # Create container if it doesn't exist yet
        if not self.container and self.context:
            self._create_container()

        if self.container and self.context:
            app = self.context.app
            toolbar = getattr(app.main_window, "_plugin_toolbar", None)

            if mode == "cue_maker":
                # Remove from toolbar (will be shown in drawer instead)
                if toolbar and self.container.parent() == toolbar:
                    self.container.setParent(None)
            else:
                # Add back to toolbar if not already there
                if toolbar and self.container.parent() != toolbar:
                    toolbar.addWidget(self.container)
                self.container.setVisible(True)

        # Re-apply current filter
        self._on_filter_changed()
        logging.debug("[Genre Filter] Activated for %s mode", mode)

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin when switching away from jukebox mode.

        Hides the filter buttons and clears the filter (shows all tracks).

        Args:
            mode: Mode name being switched away from
        """
        if self.container:
            self.container.setVisible(False)
        # Clear filter so all tracks are visible
        if self.proxy:
            self.proxy.set_filter(set(), set())
        logging.debug("[Genre Filter] Deactivated for %s mode", mode)

    def shutdown(self) -> None:
        """Cleanup resources when plugin is unloaded.

        Removes the proxy model from the track list and clears all
        references to prevent memory leaks.
        """
        if self._track_list:
            self._track_list.remove_proxy_model()
        self._track_list = None
        self.proxy = None
        self.buttons.clear()
