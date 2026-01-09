"""Tests for track list widget."""

from pathlib import Path

import pytest

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
