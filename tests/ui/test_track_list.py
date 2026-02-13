"""Tests for track list widget."""

from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel

from jukebox.ui.components.track_list import TrackList


class TestTrackList:
    """Test TrackList widget."""

    def test_initialization(self, qapp):  # type: ignore
        """Test track list initializes correctly."""
        track_list = TrackList()
        assert track_list is not None
        assert track_list.count() == 0

    def test_add_track_without_metadata(self, qapp):  # type: ignore
        """Test adding track without metadata."""
        track_list = TrackList()
        path = Path("/tmp/test.mp3")

        track_list.add_track(path)

        assert track_list.count() == 1
        assert track_list.item(0).text() == "test.mp3"

    def test_add_track_with_metadata(self, qapp):  # type: ignore
        """Test adding track with metadata."""
        track_list = TrackList()
        path = Path("/tmp/test.mp3")

        track_list.add_track(path, "My Song", "My Artist")

        assert track_list.count() == 1
        assert track_list.item(0).text() == "My Artist - My Song"

    def test_add_multiple_tracks(self, qapp):  # type: ignore
        """Test adding multiple tracks."""
        track_list = TrackList()
        paths = [Path(f"/tmp/track{i}.mp3") for i in range(5)]

        track_list.add_tracks(paths)

        assert track_list.count() == 5

    def test_clear_tracks(self, qapp):  # type: ignore
        """Test clearing tracks."""
        track_list = TrackList()
        track_list.add_track(Path("/tmp/test.mp3"))

        track_list.clear_tracks()

        assert track_list.count() == 0

    def test_get_selected_track(self, qapp):  # type: ignore
        """Test getting selected track."""
        track_list = TrackList()
        path = Path("/tmp/test.mp3")
        track_list.add_track(path)

        # Select first item
        track_list.setCurrentRow(0)

        selected = track_list.get_selected_track()
        assert selected == path

    def test_track_model_property(self, qapp):  # type: ignore
        """Test track_model property returns source model."""
        track_list = TrackList()

        # track_model should return TrackListModel directly
        assert track_list.track_model is not None
        assert track_list.track_model == track_list._track_model

    def test_set_proxy_model(self, qapp):  # type: ignore
        """Test set_proxy_model installs proxy between source and view."""
        track_list = TrackList()
        path = Path("/tmp/test.mp3")
        track_list.add_track(path)

        # Create a proxy
        proxy = QSortFilterProxyModel()

        # Install proxy
        track_list.set_proxy_model(proxy)

        # Verify proxy is now the view's model
        assert track_list.model() == proxy
        # Verify proxy's source is the track model
        assert proxy.sourceModel() == track_list.track_model
        # Verify track is still accessible
        assert track_list.count() == 1

    def test_remove_proxy_model(self, qapp):  # type: ignore
        """Test remove_proxy_model restores direct source model."""
        track_list = TrackList()
        path = Path("/tmp/test.mp3")
        track_list.add_track(path)

        # Install then remove proxy
        proxy = QSortFilterProxyModel()
        track_list.set_proxy_model(proxy)
        track_list.remove_proxy_model()

        # Verify source model is now view's model
        assert track_list.model() == track_list.track_model
        assert track_list.count() == 1

    def test_select_track_by_filepath_without_proxy(self, qapp):  # type: ignore
        """Test select_track_by_filepath works without proxy."""
        track_list = TrackList()
        path1 = Path("/tmp/track1.mp3")
        path2 = Path("/tmp/track2.mp3")
        track_list.add_track(path1)
        track_list.add_track(path2)

        # Select second track by filepath
        track_list.select_track_by_filepath(path2)

        # Verify selection
        selected = track_list.get_selected_track()
        assert selected == path2

    def test_select_track_by_filepath_with_proxy(self, qapp):  # type: ignore
        """Test select_track_by_filepath works with proxy model."""
        track_list = TrackList()
        path1 = Path("/tmp/track1.mp3")
        path2 = Path("/tmp/track2.mp3")
        track_list.add_track(path1, genre="H")
        track_list.add_track(path2, genre="W")

        # Install a proxy that filters
        proxy = QSortFilterProxyModel()
        proxy.setFilterKeyColumn(2)  # Genre column
        proxy.setFilterFixedString("H")
        track_list.set_proxy_model(proxy)

        # Select first track (which passes filter)
        track_list.select_track_by_filepath(path1)

        # Verify selection works through proxy
        selected = track_list.get_selected_track()
        assert selected == path1

    def test_select_track_by_filepath_not_found(self, qapp):  # type: ignore
        """Test select_track_by_filepath handles missing filepath gracefully."""
        track_list = TrackList()
        path1 = Path("/tmp/track1.mp3")
        track_list.add_track(path1)

        # Try to select non-existent track (should not crash)
        track_list.select_track_by_filepath(Path("/tmp/nonexistent.mp3"))

        # No selection should be made
        # (original selection remains, or no selection if none was set)

    def test_count_with_proxy(self, qapp):  # type: ignore
        """Test count() returns filtered count with proxy."""
        track_list = TrackList()
        track_list.add_track(Path("/tmp/track1.mp3"), genre="H")
        track_list.add_track(Path("/tmp/track2.mp3"), genre="W")
        track_list.add_track(Path("/tmp/track3.mp3"), genre="H")

        # Without proxy: 3 tracks
        assert track_list.count() == 3

        # With proxy filtering for "H": 2 tracks
        proxy = QSortFilterProxyModel()
        proxy.setFilterKeyColumn(2)  # Genre column
        proxy.setFilterFixedString("H")
        track_list.set_proxy_model(proxy)

        assert track_list.count() == 2
