"""Directory Navigator Plugin - Tree-based directory browsing for track navigation.

This plugin adds a directory tree view in the left sidebar (jukebox mode only) that
displays the hierarchical structure of directories containing tracks, along with
playlists. Clicking on a directory, playlist, or "All Tracks" filters the main
track list to show only matching tracks.

Usage:
    Enable the plugin in config/config.yaml under plugins.enabled:
        plugins:
          enabled:
            - directory_navigator

    The plugin activates automatically when switching to jukebox mode.
    Click on any tree node to filter the track list.

Architecture:
    - DirectoryTreeWidget: Qt tree view widget showing directory structure
    - DirectoryNavigatorPlugin: Plugin entry point and lifecycle manager

Tree Structure:
    The tree displays three top-level sections:
    - "All Tracks (N)": Shows all tracks when clicked
    - "Directories": Hierarchical view of directories with track counts
    - "Playlists (N)": List of playlists with track counts (if any exist)

Events:
    - Subscribes to: TRACKS_ADDED, TRACK_DELETED, TRACK_METADATA_UPDATED
    - Emits: LOAD_TRACK_LIST (with filepaths to display)

Filtering:
    The plugin works transparently with other filters (genre filter, search).
    It emits LOAD_TRACK_LIST events which replace the current track list,
    and other filters then apply on top of that base list.
"""

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QTreeView, QVBoxLayout, QWidget

from jukebox.core.event_bus import Events
from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol

logger = logging.getLogger(__name__)

# Data roles for tree items
ROLE_PATH = Qt.ItemDataRole.UserRole  # Full path string or "playlist:{id}"
ROLE_NODE_TYPE = Qt.ItemDataRole.UserRole + 1  # "all_tracks", "directory", "playlist"


class DirectoryTreeWidget(QWidget):
    """Tree view widget showing directory structure from database."""

    def __init__(self) -> None:
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.tree_view.setExpandsOnDoubleClick(True)

        self.model = QStandardItemModel()
        self.tree_view.setModel(self.model)

        layout.addWidget(self.tree_view)
        self.setLayout(layout)

    def build_tree(self, filepaths: list[str], playlists: list[dict[str, Any]]) -> None:
        """Build the directory tree from database filepaths and playlists.

        Args:
            filepaths: List of all track filepaths from database
            playlists: List of playlist dicts with 'id', 'name', 'track_count'
        """
        self.model.clear()
        root = self.model.invisibleRootItem()

        # "All Tracks" node
        all_item = QStandardItem(f"All Tracks ({len(filepaths)})")
        all_item.setData("all_tracks", ROLE_NODE_TYPE)
        all_item.setData("", ROLE_PATH)
        root.appendRow(all_item)

        # Build directory tree
        dir_node = QStandardItem("Directories")
        dir_node.setData("root", ROLE_NODE_TYPE)
        dir_node.setData("", ROLE_PATH)
        root.appendRow(dir_node)

        # Parse filepaths into directory structure
        dir_counts: dict[str, int] = {}
        for fp in filepaths:
            parent = str(Path(fp).parent)
            dir_counts[parent] = dir_counts.get(parent, 0) + 1

        # Build tree structure from directory paths
        self._build_directory_nodes(dir_node, dir_counts)

        # Playlists node
        if playlists:
            pl_node = QStandardItem(f"Playlists ({len(playlists)})")
            pl_node.setData("root", ROLE_NODE_TYPE)
            pl_node.setData("", ROLE_PATH)
            root.appendRow(pl_node)

            for pl in playlists:
                pl_item = QStandardItem(f"{pl['name']} ({pl['track_count']})")
                pl_item.setData("playlist", ROLE_NODE_TYPE)
                pl_item.setData(f"playlist:{pl['id']}", ROLE_PATH)
                pl_node.appendRow(pl_item)

        # Expand "Directories" by default
        dir_index = self.model.indexFromItem(dir_node)
        self.tree_view.expand(dir_index)

    def _build_directory_nodes(
        self, parent_item: QStandardItem, dir_counts: dict[str, int]
    ) -> None:
        """Build hierarchical directory nodes from flat directory paths.

        Finds the common prefix among all directories and builds a tree
        from the remaining path components.

        Args:
            parent_item: Parent tree item to attach nodes to
            dir_counts: Map of directory path -> track count
        """
        if not dir_counts:
            return

        dirs = sorted(dir_counts.keys())

        # Find common prefix (parent of all directories)
        common = Path(dirs[0])
        for d in dirs[1:]:
            # Walk up until we find a common ancestor
            while not str(d).startswith(str(common)):
                common = common.parent
                if common == common.parent:
                    break

        # Build tree from relative paths
        tree: dict[str, QStandardItem] = {}

        for dir_path in dirs:
            try:
                rel = Path(dir_path).relative_to(common)
            except ValueError:
                rel = Path(dir_path)

            parts = rel.parts
            if not parts:
                # This directory IS the common prefix
                count = dir_counts[dir_path]
                item = QStandardItem(f"{Path(dir_path).name} ({count})")
                item.setData("directory", ROLE_NODE_TYPE)
                item.setData(dir_path, ROLE_PATH)
                parent_item.appendRow(item)
                tree[dir_path] = item
                continue

            # Walk the path, creating intermediate nodes as needed
            current_parent = parent_item
            for i, part in enumerate(parts):
                key = str(common / Path(*parts[: i + 1]))
                if key not in tree:
                    # Count for this node: direct count + sum of descendants
                    node_count = dir_counts.get(key, 0)
                    # Also count all descendant directories
                    for d, c in dir_counts.items():
                        if d != key and d.startswith(key + "/"):
                            node_count += c

                    label = f"{part} ({node_count})" if node_count > 0 else part
                    item = QStandardItem(label)
                    item.setData("directory", ROLE_NODE_TYPE)
                    item.setData(key, ROLE_PATH)
                    current_parent.appendRow(item)
                    tree[key] = item
                current_parent = tree[key]


class DirectoryNavigatorPlugin:
    """Plugin providing directory-based track navigation via tree view."""

    name = "directory_navigator"
    version = "1.0.0"
    description = "Directory tree navigation for track browsing"
    modes = ["jukebox", "cue_maker"]

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin and subscribe to events."""
        self.context = context
        self.widget: DirectoryTreeWidget | None = None
        self.dock: QWidget | None = None

        context.subscribe(Events.TRACKS_ADDED, self._rebuild_tree)
        context.subscribe(Events.TRACK_DELETED, self._on_track_changed)
        context.subscribe(Events.TRACK_METADATA_UPDATED, self._on_track_changed)

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register left sidebar widget.

        The dock is created hidden by default since register_ui is called
        after deactivate in the startup sequence. activate() will show it
        when jukebox mode is entered.
        """
        self.widget = DirectoryTreeWidget()
        ui_builder.add_left_sidebar_widget(self.widget, "Directories")

        # Hide dock initially - activate() will show it for jukebox mode
        dock = self.widget.parent()
        if dock and hasattr(dock, "setVisible"):
            dock.setVisible(False)

        # Connect tree click
        self.widget.tree_view.clicked.connect(self._on_item_clicked)

        # Initial tree build
        self._rebuild_tree()

    def activate(self, mode: str) -> None:
        """Show directory tree when entering jukebox mode.

        Also rebuilds the tree to reflect changes made in curating mode.
        """
        if self.widget:
            dock = self.widget.parent()
            if dock and hasattr(dock, "setVisible"):
                dock.setVisible(True)
            self._rebuild_tree()
        logger.debug("[Directory Navigator] Activated for %s mode", mode)

    def deactivate(self, mode: str) -> None:
        """Hide directory tree when leaving jukebox mode."""
        if self.widget:
            dock = self.widget.parent()
            if dock and hasattr(dock, "setVisible"):
                dock.setVisible(False)
        logger.debug("[Directory Navigator] Deactivated for %s mode", mode)

    def _on_track_changed(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        """Handle track deletion or metadata update - rebuild tree."""
        self._rebuild_tree()

    def _rebuild_tree(self) -> None:
        """Rebuild the directory tree from database."""
        if self.widget is None:
            return

        db = self.context.database

        # Get all filepaths
        rows = db.conn.execute("SELECT filepath FROM tracks").fetchall()  # type: ignore[attr-defined]
        filepaths = [row["filepath"] for row in rows]

        # Get playlists with track counts
        playlist_rows = db.conn.execute(  # type: ignore[attr-defined]
            """
            SELECT p.id, p.name, COUNT(pt.track_id) as track_count
            FROM playlists p
            LEFT JOIN playlist_tracks pt ON p.id = pt.playlist_id
            GROUP BY p.id
            ORDER BY p.name
            """
        ).fetchall()
        playlists = [
            {"id": row["id"], "name": row["name"], "track_count": row["track_count"]}
            for row in playlist_rows
        ]

        self.widget.build_tree(filepaths, playlists)
        logger.info(
            "[Directory Navigator] Tree built: %d tracks, %d playlists",
            len(filepaths),
            len(playlists),
        )

    def _on_item_clicked(self, index) -> None:  # type: ignore[no-untyped-def]
        """Handle tree item click - filter tracklist by selected directory or playlist."""
        item = self.widget.model.itemFromIndex(index)  # type: ignore[union-attr]
        if item is None:
            return

        node_type = item.data(ROLE_NODE_TYPE)
        path_data = item.data(ROLE_PATH)

        if node_type == "root":
            # Root nodes ("Directories", "Playlists") are not clickable filters
            return

        db = self.context.database

        if node_type == "all_tracks":
            # Show all tracks - emit with all filepaths
            rows = db.conn.execute("SELECT filepath FROM tracks").fetchall()  # type: ignore[attr-defined]
            filepaths = [Path(row["filepath"]) for row in rows]

        elif node_type == "directory":
            # Filter by directory (recursive: LIKE 'path%')
            rows = db.conn.execute(  # type: ignore[attr-defined]
                "SELECT filepath FROM tracks WHERE filepath LIKE ?",
                (path_data + "/%",),
            ).fetchall()
            filepaths = [Path(row["filepath"]) for row in rows]

        elif node_type == "playlist":
            # Load playlist tracks
            playlist_id = int(path_data.split(":")[1])
            rows = db.conn.execute(  # type: ignore[attr-defined]
                """
                SELECT t.filepath
                FROM tracks t
                JOIN playlist_tracks pt ON t.id = pt.track_id
                WHERE pt.playlist_id = ?
                ORDER BY pt.position
                """,
                (playlist_id,),
            ).fetchall()
            filepaths = [Path(row["filepath"]) for row in rows]

        else:
            return

        self.context.emit(Events.LOAD_TRACK_LIST, filepaths=filepaths)
        logger.debug(
            "[Directory Navigator] Loaded %d tracks for %s: %s",
            len(filepaths),
            node_type,
            path_data,
        )

    def shutdown(self) -> None:
        """Cleanup references."""
        self.widget = None
