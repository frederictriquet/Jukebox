"""Tests for search and filter plugin."""

from unittest.mock import Mock, patch

from PySide6.QtCore import QModelIndex

from plugins.search_and_filter import (
    GenreFilterButton,
    SearchAndFilterPlugin,
    GenreFilterProxyModel,
    GenreFilterState,
)


class TestGenreFilterState:
    """Test GenreFilterState enum."""

    def test_state_values(self) -> None:
        """Test that state values are correct."""
        assert GenreFilterState.INDIFFERENT == 0
        assert GenreFilterState.ON == 1
        assert GenreFilterState.OFF == 2


class TestGenreFilterButton:
    """Test GenreFilterButton widget."""

    def test_initialization(self, qapp) -> None:  # type: ignore
        """Test button initializes correctly."""
        button = GenreFilterButton("H", "House")

        assert button.code == "H"
        assert button.genre_name == "House"
        assert button.state == GenreFilterState.INDIFFERENT
        assert button.text() == "H"
        assert button.toolTip() == "House"

    def test_button_size(self, qapp) -> None:  # type: ignore
        """Test button has fixed size."""
        button = GenreFilterButton("D", "Deep")

        assert button.width() == 32
        assert button.height() == 26

    def test_cycle_states(self, qapp) -> None:  # type: ignore
        """Test button cycles through states: indifferent → on → off → indifferent."""
        button = GenreFilterButton("T", "Trance")

        # Initial state
        assert button.state == GenreFilterState.INDIFFERENT

        # First click: indifferent → on
        button.click()
        assert button.state == GenreFilterState.ON

        # Second click: on → off
        button.click()
        assert button.state == GenreFilterState.OFF

        # Third click: off → indifferent
        button.click()
        assert button.state == GenreFilterState.INDIFFERENT

    def test_button_style_changes(self, qapp) -> None:  # type: ignore
        """Test button style changes with state."""
        button = GenreFilterButton("P", "Power")

        # INDIFFERENT: gray
        initial_style = button.styleSheet()
        assert "#555" in initial_style  # Gray background

        # ON: green
        button.click()
        on_style = button.styleSheet()
        assert "#2d7a2d" in on_style  # Green background

        # OFF: red
        button.click()
        off_style = button.styleSheet()
        assert "#7a2d2d" in off_style  # Red background


class TestGenreFilterProxyModelLogic:
    """Test GenreFilterProxyModel filtering logic (without Qt integration)."""

    def test_initialization(self, qapp) -> None:  # type: ignore
        """Test proxy model initializes correctly."""
        proxy = GenreFilterProxyModel()

        assert proxy._on_genres == set()
        assert proxy._off_genres == set()

    def test_set_filter_empty(self, qapp) -> None:  # type: ignore
        """Test setting empty filter."""
        proxy = GenreFilterProxyModel()

        proxy.set_genre_filter(set(), set())

        assert proxy._on_genres == set()
        assert proxy._off_genres == set()

    def test_set_filter_with_genres(self, qapp) -> None:  # type: ignore
        """Test setting filter with genres."""
        proxy = GenreFilterProxyModel()

        proxy.set_genre_filter({"H", "T"}, {"W"})

        assert proxy._on_genres == {"H", "T"}
        assert proxy._off_genres == {"W"}

    def test_filter_logic_no_filter(self, qapp) -> None:  # type: ignore
        """Test that no filter accepts all."""
        proxy = GenreFilterProxyModel()
        proxy._on_genres = set()
        proxy._off_genres = set()

        # Create a mock model with tracks
        with patch.object(proxy, "sourceModel") as mock_source:
            mock_source.return_value.tracks = [
                {"genre": "H-W"},
                {"genre": "T"},
            ]
            # Direct logic test: both should pass
            assert proxy.filterAcceptsRow(0, QModelIndex()) is True
            assert proxy.filterAcceptsRow(1, QModelIndex()) is True

    def test_filter_logic_on_genre(self, qapp) -> None:  # type: ignore
        """Test ON genre filter logic."""
        proxy = GenreFilterProxyModel()
        proxy._on_genres = {"H"}
        proxy._off_genres = set()

        tracks = [
            {"genre": "H-W"},  # Has H - pass
            {"genre": "T"},  # No H - fail
            {"genre": "H-P-*3"},  # Has H - pass
        ]

        with patch.object(proxy, "sourceModel") as mock_source:
            mock_source.return_value.tracks = tracks

            assert proxy.filterAcceptsRow(0, QModelIndex()) is True  # H-W
            assert proxy.filterAcceptsRow(1, QModelIndex()) is False  # T
            assert proxy.filterAcceptsRow(2, QModelIndex()) is True  # H-P-*3

    def test_filter_logic_off_genre(self, qapp) -> None:  # type: ignore
        """Test OFF genre filter logic."""
        proxy = GenreFilterProxyModel()
        proxy._on_genres = set()
        proxy._off_genres = {"W"}

        tracks = [
            {"genre": "H-W"},  # Has W - fail
            {"genre": "T"},  # No W - pass
            {"genre": "D-P"},  # No W - pass
        ]

        with patch.object(proxy, "sourceModel") as mock_source:
            mock_source.return_value.tracks = tracks

            assert proxy.filterAcceptsRow(0, QModelIndex()) is False  # H-W
            assert proxy.filterAcceptsRow(1, QModelIndex()) is True  # T
            assert proxy.filterAcceptsRow(2, QModelIndex()) is True  # D-P

    def test_filter_logic_multiple_on(self, qapp) -> None:  # type: ignore
        """Test ON multiple genres (AND logic)."""
        proxy = GenreFilterProxyModel()
        proxy._on_genres = {"H", "W"}
        proxy._off_genres = set()

        tracks = [
            {"genre": "H-W"},  # Has both - pass
            {"genre": "H"},  # Has H only - fail
            {"genre": "W"},  # Has W only - fail
            {"genre": "H-W-T"},  # Has both + T - pass
        ]

        with patch.object(proxy, "sourceModel") as mock_source:
            mock_source.return_value.tracks = tracks

            assert proxy.filterAcceptsRow(0, QModelIndex()) is True  # H-W
            assert proxy.filterAcceptsRow(1, QModelIndex()) is False  # H only
            assert proxy.filterAcceptsRow(2, QModelIndex()) is False  # W only
            assert proxy.filterAcceptsRow(3, QModelIndex()) is True  # H-W-T

    def test_filter_logic_combined(self, qapp) -> None:  # type: ignore
        """Test combined ON and OFF genres."""
        proxy = GenreFilterProxyModel()
        proxy._on_genres = {"H"}
        proxy._off_genres = {"W"}

        tracks = [
            {"genre": "H-T"},  # Has H, no W - pass
            {"genre": "H-W"},  # Has H and W - fail
            {"genre": "T"},  # No H - fail
            {"genre": "H-D"},  # Has H, no W - pass
        ]

        with patch.object(proxy, "sourceModel") as mock_source:
            mock_source.return_value.tracks = tracks

            assert proxy.filterAcceptsRow(0, QModelIndex()) is True  # H-T
            assert proxy.filterAcceptsRow(1, QModelIndex()) is False  # H-W
            assert proxy.filterAcceptsRow(2, QModelIndex()) is False  # T
            assert proxy.filterAcceptsRow(3, QModelIndex()) is True  # H-D

    def test_filter_logic_rating_stars_ignored(self, qapp) -> None:  # type: ignore
        """Test that rating stars (*N) are ignored."""
        proxy = GenreFilterProxyModel()
        proxy._on_genres = {"H"}
        proxy._off_genres = set()

        tracks = [
            {"genre": "H-*3"},  # H with rating - pass
            {"genre": "*5"},  # Only rating - fail
            {"genre": "H-W-*4"},  # H-W with rating - pass
        ]

        with patch.object(proxy, "sourceModel") as mock_source:
            mock_source.return_value.tracks = tracks

            assert proxy.filterAcceptsRow(0, QModelIndex()) is True  # H-*3
            assert proxy.filterAcceptsRow(1, QModelIndex()) is False  # *5
            assert proxy.filterAcceptsRow(2, QModelIndex()) is True  # H-W-*4

    def test_filter_logic_empty_genre(self, qapp) -> None:  # type: ignore
        """Test handling of empty/None genre."""
        proxy = GenreFilterProxyModel()
        proxy._on_genres = {"H"}
        proxy._off_genres = set()

        tracks = [
            {"genre": None},
            {"genre": ""},
            {},  # Missing genre
        ]

        with patch.object(proxy, "sourceModel") as mock_source:
            mock_source.return_value.tracks = tracks

            # All should fail (no H)
            assert proxy.filterAcceptsRow(0, QModelIndex()) is False
            assert proxy.filterAcceptsRow(1, QModelIndex()) is False
            assert proxy.filterAcceptsRow(2, QModelIndex()) is False

    def test_filter_accepts_out_of_bounds(self, qapp) -> None:  # type: ignore
        """Test out of bounds row returns True (accept)."""
        proxy = GenreFilterProxyModel()

        with patch.object(proxy, "sourceModel") as mock_source:
            mock_source.return_value.tracks = [{"genre": "H"}]

            # Out of bounds
            assert proxy.filterAcceptsRow(999, QModelIndex()) is True


class TestSearchAndFilterPlugin:
    """Test SearchAndFilterPlugin."""

    def test_plugin_attributes(self) -> None:
        """Test plugin has required attributes."""
        plugin = SearchAndFilterPlugin()

        assert plugin.name == "search_and_filter"
        assert plugin.version == "1.0.0"
        assert plugin.description == "Centralized search and genre filter management"
        assert plugin.modes == ["jukebox", "cue_maker"]

    def test_initialization(self) -> None:
        """Test plugin initializes correctly."""
        plugin = SearchAndFilterPlugin()

        assert plugin.context is None
        assert plugin.proxy is None
        assert plugin.genre_buttons == []
        assert plugin.toolbar_container is None

    def test_initialize_subscribes_to_events(self) -> None:
        """Test initialize subscribes to TRACKS_ADDED event."""
        plugin = SearchAndFilterPlugin()
        mock_context = Mock()

        plugin.initialize(mock_context)

        assert plugin.context == mock_context
        mock_context.subscribe.assert_called_once()
        call_args = mock_context.subscribe.call_args
        assert call_args[0][0] == "tracks_added"

    def test_register_ui_creates_buttons(self, qapp) -> None:  # type: ignore
        """Test register_ui creates filter buttons."""
        plugin = SearchAndFilterPlugin()

        # Create objects with string attributes (Qt methods like setToolTip need str)
        class CodeConfig:
            def __init__(self, code: str, name: str):
                self.code = code
                self.name = name

        mock_config = Mock()
        mock_config.genre_editor.codes = [
            CodeConfig("H", "House"),
            CodeConfig("T", "Trance"),
            CodeConfig("D", "Deep"),
        ]
        mock_context = Mock()
        mock_context.config = mock_config
        plugin.context = mock_context

        mock_ui_builder = Mock()
        mock_track_list = Mock()
        mock_ui_builder.main_window.track_list = mock_track_list

        plugin.register_ui(mock_ui_builder)

        # Verify buttons created and sorted
        assert len(plugin.genre_buttons) == 3
        assert plugin.genre_buttons[0].code == "D"  # Alphabetically sorted
        assert plugin.genre_buttons[1].code == "H"
        assert plugin.genre_buttons[2].code == "T"

        # Verify container added
        mock_ui_builder.add_toolbar_widget.assert_called_once()
        assert plugin.toolbar_container is not None

        # Verify proxy created
        assert plugin.proxy is not None
        mock_track_list.set_proxy_model.assert_called_once_with(plugin.proxy)

    def test_on_filter_changed_updates_proxy(self, qapp) -> None:  # type: ignore
        """Test _on_filter_changed collects states and updates proxy."""
        plugin = SearchAndFilterPlugin()
        plugin.proxy = GenreFilterProxyModel()
        mock_context = Mock()
        plugin.context = mock_context

        btn1 = GenreFilterButton("H", "House")
        btn1.state = GenreFilterState.ON
        btn2 = GenreFilterButton("W", "Weed")
        btn2.state = GenreFilterState.OFF
        btn3 = GenreFilterButton("T", "Trance")
        btn3.state = GenreFilterState.INDIFFERENT

        plugin.genre_buttons = [btn1, btn2, btn3]

        plugin._on_filter_changed()

        # Verify proxy updated
        assert plugin.proxy._on_genres == {"H"}
        assert plugin.proxy._off_genres == {"W"}

        # Verify event emitted
        mock_context.emit.assert_called_once()
        call_args = mock_context.emit.call_args
        assert call_args[0][0] == "genre_filter_changed"
        assert call_args[1]["on_genres"] == {"H"}
        assert call_args[1]["off_genres"] == {"W"}

    def test_on_tracks_added_invalidates_filter(self, qapp) -> None:  # type: ignore
        """Test _on_tracks_added invalidates filter."""
        plugin = SearchAndFilterPlugin()
        mock_proxy = Mock()
        plugin.proxy = mock_proxy

        plugin._on_tracks_added()

        mock_proxy.invalidateFilter.assert_called_once()

    def test_activate_re_applies_filter(self, qapp) -> None:  # type: ignore
        """Test activate() re-applies the filter."""
        plugin = SearchAndFilterPlugin()
        plugin.proxy = GenreFilterProxyModel()
        mock_context = Mock()
        plugin.context = mock_context

        btn = GenreFilterButton("H", "House")
        btn.state = GenreFilterState.ON
        plugin.genre_buttons = [btn]
        plugin.toolbar_container = Mock()  # Set container so _create_container isn't called

        plugin.activate("jukebox")

        # Verify filter was re-applied via event emission
        mock_context.emit.assert_called()

    def test_deactivate_clears_filter(self, qapp) -> None:  # type: ignore
        """Test deactivate() clears the filter."""
        plugin = SearchAndFilterPlugin()
        plugin.proxy = GenreFilterProxyModel()
        plugin.proxy.set_genre_filter({"H"}, {"W"})

        plugin.deactivate("curating")

        # Filter should be cleared
        assert plugin.proxy._on_genres == set()
        assert plugin.proxy._off_genres == set()

    def test_shutdown_removes_proxy(self) -> None:
        """Test shutdown() removes proxy model."""
        plugin = SearchAndFilterPlugin()
        mock_track_list = Mock()
        plugin._track_list = mock_track_list
        plugin.proxy = Mock()
        plugin.genre_buttons = [Mock(), Mock()]

        plugin.shutdown()

        mock_track_list.remove_proxy_model.assert_called_once()
        assert plugin._track_list is None
        assert plugin.proxy is None
        assert plugin.genre_buttons == []

    def test_buttons_emit_signal_on_click(self, qapp) -> None:  # type: ignore
        """Test clicking buttons triggers filter update."""
        plugin = SearchAndFilterPlugin()
        plugin.proxy = GenreFilterProxyModel()
        mock_context = Mock()
        plugin.context = mock_context

        button = GenreFilterButton("H", "House")
        plugin.genre_buttons = [button]

        button.clicked.connect(plugin._on_filter_changed)
        button.click()

        # Verify filter updated
        assert plugin.proxy._on_genres == {"H"}
        assert plugin.proxy._off_genres == set()
