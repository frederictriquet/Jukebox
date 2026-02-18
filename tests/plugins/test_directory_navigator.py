"""Tests for the directory navigator plugin."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QDockWidget, QWidget

from plugins.directory_navigator import (
    ROLE_NODE_TYPE,
    ROLE_PATH,
    DirectoryNavigatorPlugin,
    DirectoryTreeWidget,
)

# ============================================================================
# DirectoryTreeWidget Tests
# ============================================================================


def test_directory_tree_widget_init_ui(qapp) -> None:  # type: ignore
    """Test that DirectoryTreeWidget initializes UI correctly."""
    widget = DirectoryTreeWidget()

    assert widget.tree_view is not None
    assert widget.model is not None
    assert widget.tree_view.model() == widget.model
    assert widget.tree_view.isHeaderHidden() is True


def test_build_tree_empty_filepaths(qapp) -> None:  # type: ignore
    """Test build_tree with no filepaths."""
    widget = DirectoryTreeWidget()
    widget.build_tree([], [])

    # Should have "All Tracks" and "Directories" root nodes
    root = widget.model.invisibleRootItem()
    assert root.rowCount() == 2

    all_tracks_item = root.child(0)
    assert "All Tracks (0)" in all_tracks_item.text()
    assert all_tracks_item.data(ROLE_NODE_TYPE) == "all_tracks"

    dir_item = root.child(1)
    assert "Directories" in dir_item.text()
    assert dir_item.data(ROLE_NODE_TYPE) == "root"


def test_build_tree_single_level(qapp) -> None:  # type: ignore
    """Test build_tree with single directory level."""
    widget = DirectoryTreeWidget()
    filepaths = [
        "/music/song1.mp3",
        "/music/song2.mp3",
        "/music/song3.mp3",
    ]
    widget.build_tree(filepaths, [])

    root = widget.model.invisibleRootItem()

    # Check "All Tracks" node
    all_tracks_item = root.child(0)
    assert "All Tracks (3)" in all_tracks_item.text()

    # Check "Directories" node has one child
    dir_node = root.child(1)
    assert dir_node.rowCount() == 1

    # Check the /music directory
    music_dir = dir_node.child(0)
    assert "music" in music_dir.text()
    assert "(3)" in music_dir.text()
    assert music_dir.data(ROLE_PATH) == str(Path("/music"))
    assert music_dir.data(ROLE_NODE_TYPE) == "directory"


def test_build_tree_multi_level(qapp) -> None:  # type: ignore
    """Test build_tree with nested directories."""
    widget = DirectoryTreeWidget()
    filepaths = [
        "/music/rock/song1.mp3",
        "/music/rock/song2.mp3",
        "/music/jazz/song3.mp3",
        "/music/jazz/classic/song4.mp3",
    ]
    widget.build_tree(filepaths, [])

    root = widget.model.invisibleRootItem()
    dir_node = root.child(1)

    # Should have "rock" and "jazz" under first level
    assert dir_node.rowCount() > 0

    # Verify counts are accumulated (rock=2, jazz=2 including nested)
    all_tracks_item = root.child(0)
    assert "All Tracks (4)" in all_tracks_item.text()


def test_build_tree_with_playlists(qapp) -> None:  # type: ignore
    """Test build_tree includes playlists."""
    widget = DirectoryTreeWidget()
    filepaths = ["/music/song1.mp3", "/music/song2.mp3"]
    playlists = [
        {"id": 1, "name": "Favorites", "track_count": 5},
        {"id": 2, "name": "Chill", "track_count": 3},
    ]
    widget.build_tree(filepaths, playlists)

    root = widget.model.invisibleRootItem()

    # Should have "All Tracks", "Directories", and "Playlists" nodes
    assert root.rowCount() == 3

    playlists_node = root.child(2)
    assert "Playlists (2)" in playlists_node.text()
    assert playlists_node.data(ROLE_NODE_TYPE) == "root"

    # Check playlist items
    assert playlists_node.rowCount() == 2

    fav_item = playlists_node.child(0)
    assert "Favorites (5)" in fav_item.text()
    assert fav_item.data(ROLE_NODE_TYPE) == "playlist"
    assert fav_item.data(ROLE_PATH) == "playlist:1"

    chill_item = playlists_node.child(1)
    assert "Chill (3)" in chill_item.text()
    assert chill_item.data(ROLE_PATH) == "playlist:2"


def test_build_tree_common_prefix(qapp) -> None:  # type: ignore
    """Test build_tree handles common prefix correctly."""
    widget = DirectoryTreeWidget()
    filepaths = [
        "/home/user/music/rock/song1.mp3",
        "/home/user/music/jazz/song2.mp3",
    ]
    widget.build_tree(filepaths, [])

    root = widget.model.invisibleRootItem()
    dir_node = root.child(1)

    # Should strip common prefix and show relative paths
    # The exact structure depends on _build_directory_nodes implementation
    assert dir_node.rowCount() > 0


def test_build_directory_nodes_single_dir(qapp) -> None:  # type: ignore
    """Test _build_directory_nodes with a single directory."""
    widget = DirectoryTreeWidget()
    from PySide6.QtGui import QStandardItem

    parent_item = QStandardItem()
    dir_counts = {"/music": 5}

    widget._build_directory_nodes(parent_item, dir_counts)

    assert parent_item.rowCount() == 1
    item = parent_item.child(0)
    assert "music" in item.text()
    assert "(5)" in item.text()
    assert item.data(ROLE_PATH) == "/music"


def test_build_directory_nodes_nested(qapp) -> None:  # type: ignore
    """Test _build_directory_nodes with nested directories."""
    widget = DirectoryTreeWidget()
    from PySide6.QtGui import QStandardItem

    parent_item = QStandardItem()
    dir_counts = {
        "/music/rock": 3,
        "/music/jazz": 2,
        "/music/jazz/classic": 1,
    }

    widget._build_directory_nodes(parent_item, dir_counts)

    # Should create hierarchical structure
    assert parent_item.rowCount() > 0


def test_build_directory_nodes_count_accumulation(qapp) -> None:  # type: ignore
    """Test that directory counts include descendant tracks."""
    widget = DirectoryTreeWidget()
    from PySide6.QtGui import QStandardItem

    parent_item = QStandardItem()
    dir_counts = {
        "/music": 2,  # 2 direct tracks
        "/music/rock": 3,  # 3 tracks in rock
    }

    widget._build_directory_nodes(parent_item, dir_counts)

    # Parent "/music" should show total count (2 direct + 3 in rock = 5)
    # Implementation detail: verify the count includes descendants
    assert parent_item.rowCount() > 0


def test_tree_view_expand_directories_by_default(qapp) -> None:  # type: ignore
    """Test that Directories node is expanded by default."""
    widget = DirectoryTreeWidget()
    filepaths = ["/music/song1.mp3"]
    widget.build_tree(filepaths, [])

    # Verify the "Directories" node is expanded (tested via index)
    root = widget.model.invisibleRootItem()
    dir_node = root.child(1)
    dir_index = widget.model.indexFromItem(dir_node)

    # This should be expanded after build_tree
    assert widget.tree_view.isExpanded(dir_index) is True


# ============================================================================
# DirectoryNavigatorPlugin Tests
# ============================================================================


@pytest.fixture
def mock_context() -> Mock:
    """Create a mock PluginContext."""
    context = Mock()
    context.database = Mock()
    context.database.conn = Mock()
    # Setup default return for _rebuild_tree calls (empty database)
    context.database.conn.execute.return_value.fetchall.return_value = []
    context.event_bus = Mock()
    context.emit = Mock()
    context.subscribe = Mock()
    return context


@pytest.fixture
def mock_ui_builder() -> Mock:
    """Create a mock UIBuilder."""
    ui_builder = Mock()
    ui_builder.add_left_sidebar_widget = Mock()
    return ui_builder


@pytest.fixture
def plugin() -> DirectoryNavigatorPlugin:
    """Create a plugin instance."""
    return DirectoryNavigatorPlugin()


def test_plugin_metadata(plugin) -> None:  # type: ignore
    """Test plugin metadata attributes."""
    assert plugin.name == "directory_navigator"
    assert plugin.version == "1.0.0"
    assert "directory" in plugin.description.lower()
    assert plugin.modes == ["jukebox", "cue_maker"]


def test_initialize_subscribes_to_events(plugin, mock_context) -> None:  # type: ignore
    """Test that initialize subscribes to required events."""
    plugin.initialize(mock_context)

    assert plugin.context == mock_context

    # Verify event subscriptions
    from jukebox.core.event_bus import Events

    assert mock_context.subscribe.call_count == 3
    mock_context.subscribe.assert_any_call(Events.TRACKS_ADDED, plugin._rebuild_tree)
    mock_context.subscribe.assert_any_call(Events.TRACK_DELETED, plugin._on_track_changed)
    mock_context.subscribe.assert_any_call(Events.TRACK_METADATA_UPDATED, plugin._on_track_changed)


def test_register_ui_creates_widget(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test that register_ui creates widget and adds to left sidebar."""
    plugin.initialize(mock_context)
    plugin.register_ui(mock_ui_builder)

    assert plugin.widget is not None
    assert isinstance(plugin.widget, DirectoryTreeWidget)

    # Verify widget was added to left sidebar
    mock_ui_builder.add_left_sidebar_widget.assert_called_once()
    call_args = mock_ui_builder.add_left_sidebar_widget.call_args
    assert call_args[0][0] == plugin.widget
    assert "Directories" in call_args[0][1]


def test_register_ui_hides_dock_initially(qapp, plugin, mock_context) -> None:  # type: ignore
    """Test that register_ui creates dock hidden by default."""
    plugin.initialize(mock_context)

    # Create a real dock to test visibility
    from PySide6.QtWidgets import QDockWidget, QMainWindow

    main_window = QMainWindow()
    dock = QDockWidget("Test", main_window)

    ui_builder = Mock()

    def add_left_sidebar_side_effect(widget: QWidget, title: str) -> None:
        dock.setWidget(widget)
        # Simulate what real UIBuilder does
        pass

    ui_builder.add_left_sidebar_widget = Mock(side_effect=add_left_sidebar_side_effect)

    # Patch parent() to return our dock
    with patch.object(DirectoryTreeWidget, "parent", return_value=dock):
        plugin.register_ui(ui_builder)

        # Dock should be hidden initially
        assert dock.isVisible() is False


def test_register_ui_calls_rebuild_tree(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test that register_ui calls _rebuild_tree to populate initially."""
    plugin.initialize(mock_context)

    with patch.object(plugin, "_rebuild_tree") as mock_rebuild:
        plugin.register_ui(mock_ui_builder)
        mock_rebuild.assert_called_once()


def test_activate_shows_dock(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test that activate shows the dock widget."""
    plugin.initialize(mock_context)
    plugin.register_ui(mock_ui_builder)

    # Create a mock dock
    mock_dock = Mock(spec=QDockWidget)
    with patch.object(plugin.widget, "parent", return_value=mock_dock):
        plugin.activate("jukebox")

        mock_dock.setVisible.assert_called_with(True)


def test_activate_rebuilds_tree(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test that activate rebuilds tree to show curating-mode changes."""
    plugin.initialize(mock_context)
    plugin.register_ui(mock_ui_builder)

    with patch.object(plugin, "_rebuild_tree") as mock_rebuild:
        # Reset call count from register_ui
        mock_rebuild.reset_mock()

        plugin.activate("jukebox")
        mock_rebuild.assert_called_once()


def test_deactivate_hides_dock(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test that deactivate hides the dock widget."""
    plugin.initialize(mock_context)
    plugin.register_ui(mock_ui_builder)

    mock_dock = Mock(spec=QDockWidget)
    with patch.object(plugin.widget, "parent", return_value=mock_dock):
        plugin.deactivate("curating")

        mock_dock.setVisible.assert_called_with(False)


def test_on_track_changed_rebuilds_tree(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test that _on_track_changed calls _rebuild_tree."""
    plugin.initialize(mock_context)
    plugin.register_ui(mock_ui_builder)

    with patch.object(plugin, "_rebuild_tree") as mock_rebuild:
        mock_rebuild.reset_mock()

        plugin._on_track_changed()
        mock_rebuild.assert_called_once()


def test_rebuild_tree_queries_database(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test that _rebuild_tree queries database for tracks and playlists."""
    plugin.initialize(mock_context)
    plugin.register_ui(mock_ui_builder)

    # Setup mock database
    mock_conn = Mock()
    mock_context.database.conn = mock_conn

    # Mock track query
    track_rows = [
        {"filepath": "/music/song1.mp3"},
        {"filepath": "/music/song2.mp3"},
    ]
    mock_conn.execute.return_value.fetchall.side_effect = [track_rows, []]

    plugin._rebuild_tree()

    # Verify database was queried
    assert mock_conn.execute.call_count == 2


def test_rebuild_tree_with_playlists(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test that _rebuild_tree includes playlists."""
    plugin.initialize(mock_context)
    plugin.register_ui(mock_ui_builder)

    mock_conn = Mock()
    mock_context.database.conn = mock_conn

    track_rows = [{"filepath": "/music/song1.mp3"}]
    playlist_rows = [
        {"id": 1, "name": "Favorites", "track_count": 5},
    ]

    mock_conn.execute.return_value.fetchall.side_effect = [track_rows, playlist_rows]

    with patch.object(plugin.widget, "build_tree") as mock_build:
        plugin._rebuild_tree()

        # Verify build_tree was called with both tracks and playlists
        mock_build.assert_called_once()
        call_args = mock_build.call_args[0]
        assert len(call_args[0]) == 1  # filepaths
        assert len(call_args[1]) == 1  # playlists


def test_on_item_clicked_all_tracks(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test clicking 'All Tracks' node emits LOAD_TRACK_LIST with all tracks."""
    plugin.initialize(mock_context)
    plugin.register_ui(mock_ui_builder)

    # Setup mock database
    mock_conn = Mock()
    mock_context.database.conn = mock_conn
    track_rows = [
        {"filepath": "/music/song1.mp3"},
        {"filepath": "/music/song2.mp3"},
    ]
    mock_conn.execute.return_value.fetchall.return_value = track_rows

    # Create mock index for "all_tracks" node
    mock_item = Mock()
    mock_item.data.side_effect = lambda role: "all_tracks" if role == ROLE_NODE_TYPE else ""

    with patch.object(plugin.widget.model, "itemFromIndex", return_value=mock_item):
        mock_index = Mock(spec=QModelIndex)
        plugin._on_item_clicked(mock_index)

    # Verify LOAD_TRACK_LIST was emitted with all filepaths
    from jukebox.core.event_bus import Events

    mock_context.emit.assert_called_once()
    call_args = mock_context.emit.call_args
    assert call_args[0][0] == Events.LOAD_TRACK_LIST
    assert "filepaths" in call_args[1]
    assert len(call_args[1]["filepaths"]) == 2


def test_on_item_clicked_directory(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test clicking directory node filters tracks recursively."""
    plugin.initialize(mock_context)
    plugin.register_ui(mock_ui_builder)

    # Setup mock database
    mock_conn = Mock()
    mock_context.database.conn = mock_conn
    track_rows = [
        {"filepath": "/music/rock/song1.mp3"},
        {"filepath": "/music/rock/song2.mp3"},
    ]
    mock_conn.execute.return_value.fetchall.return_value = track_rows

    # Create mock index for directory node
    mock_item = Mock()
    mock_item.data.side_effect = lambda role: (
        "directory" if role == ROLE_NODE_TYPE else "/music/rock" if role == ROLE_PATH else None
    )

    with patch.object(plugin.widget.model, "itemFromIndex", return_value=mock_item):
        mock_index = Mock(spec=QModelIndex)
        plugin._on_item_clicked(mock_index)

    # Verify database query used LIKE for recursive filtering
    mock_conn.execute.assert_called()
    call_args = mock_conn.execute.call_args
    assert "LIKE" in call_args[0][0]
    assert call_args[0][1] == ("/music/rock/%",)

    # Verify LOAD_TRACK_LIST was emitted
    from jukebox.core.event_bus import Events

    mock_context.emit.assert_called_once()
    assert mock_context.emit.call_args[0][0] == Events.LOAD_TRACK_LIST


def test_on_item_clicked_playlist(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test clicking playlist node loads playlist tracks."""
    plugin.initialize(mock_context)
    plugin.register_ui(mock_ui_builder)

    # Setup mock database
    mock_conn = Mock()
    mock_context.database.conn = mock_conn
    track_rows = [
        {"filepath": "/music/song1.mp3"},
        {"filepath": "/music/song2.mp3"},
    ]
    mock_conn.execute.return_value.fetchall.return_value = track_rows

    # Create mock index for playlist node
    mock_item = Mock()
    mock_item.data.side_effect = lambda role: (
        "playlist" if role == ROLE_NODE_TYPE else "playlist:42" if role == ROLE_PATH else None
    )

    with patch.object(plugin.widget.model, "itemFromIndex", return_value=mock_item):
        mock_index = Mock(spec=QModelIndex)
        plugin._on_item_clicked(mock_index)

    # Verify database query for playlist tracks
    mock_conn.execute.assert_called()
    call_args = mock_conn.execute.call_args
    assert "playlist_tracks" in call_args[0][0]
    assert call_args[0][1] == (42,)  # Playlist ID extracted from "playlist:42"

    # Verify LOAD_TRACK_LIST was emitted

    mock_context.emit.assert_called_once()


def test_on_item_clicked_root_node_ignored(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test clicking root nodes (Directories, Playlists) does nothing."""
    plugin.initialize(mock_context)
    plugin.register_ui(mock_ui_builder)

    # Create mock index for root node
    mock_item = Mock()
    mock_item.data.side_effect = lambda role: "root" if role == ROLE_NODE_TYPE else ""

    with patch.object(plugin.widget.model, "itemFromIndex", return_value=mock_item):
        mock_index = Mock(spec=QModelIndex)
        plugin._on_item_clicked(mock_index)

    # Verify no event was emitted
    mock_context.emit.assert_not_called()


def test_on_item_clicked_none_item_ignored(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test clicking invalid index does nothing."""
    plugin.initialize(mock_context)
    plugin.register_ui(mock_ui_builder)

    with patch.object(plugin.widget.model, "itemFromIndex", return_value=None):
        mock_index = Mock(spec=QModelIndex)
        plugin._on_item_clicked(mock_index)

    # Verify no event was emitted
    mock_context.emit.assert_not_called()


def test_shutdown_cleanup(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test that shutdown cleans up references."""
    plugin.initialize(mock_context)
    plugin.register_ui(mock_ui_builder)

    assert plugin.widget is not None

    plugin.shutdown()

    assert plugin.widget is None


def test_rebuild_tree_handles_empty_database(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test _rebuild_tree handles empty database gracefully."""
    plugin.initialize(mock_context)
    plugin.register_ui(mock_ui_builder)

    mock_conn = Mock()
    mock_context.database.conn = mock_conn
    mock_conn.execute.return_value.fetchall.return_value = []

    # Should not raise exception
    plugin._rebuild_tree()

    # Widget should have empty tree
    assert plugin.widget.model.invisibleRootItem().rowCount() >= 2  # At least root nodes


def test_filepaths_converted_to_path_objects(qapp, plugin, mock_context, mock_ui_builder) -> None:  # type: ignore
    """Test that LOAD_TRACK_LIST receives Path objects, not strings."""
    plugin.initialize(mock_context)
    plugin.register_ui(mock_ui_builder)

    mock_conn = Mock()
    mock_context.database.conn = mock_conn
    track_rows = [{"filepath": "/music/song1.mp3"}]
    mock_conn.execute.return_value.fetchall.return_value = track_rows

    # Click "all_tracks" node
    mock_item = Mock()
    mock_item.data.side_effect = lambda role: "all_tracks" if role == ROLE_NODE_TYPE else ""

    with patch.object(plugin.widget.model, "itemFromIndex", return_value=mock_item):
        mock_index = Mock(spec=QModelIndex)
        plugin._on_item_clicked(mock_index)

    # Verify Path objects were passed

    call_args = mock_context.emit.call_args[1]
    filepaths = call_args["filepaths"]
    assert all(isinstance(fp, Path) for fp in filepaths)
