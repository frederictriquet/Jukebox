"""Tests for database module."""

from pathlib import Path

from jukebox.core.database import Database


class TestDatabase:
    """Test suite for Database."""

    def test_initialization(self, tmp_path: Path) -> None:
        """Test database initialization."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        assert db.conn is not None

        # Verify tables exist
        cursor = db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        assert "tracks" in tables
        assert "tracks_fts" in tables
        assert "playlists" in tables
        assert "play_history" in tables

    def test_add_track(self, tmp_path: Path) -> None:
        """Test adding a track."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        track_data = {
            "filepath": "/tmp/test.mp3",
            "filename": "test.mp3",
            "title": "Test Song",
            "artist": "Test Artist",
            "album": "Test Album",
        }

        track_id = db.add_track(track_data)
        assert track_id > 0

        # Verify retrieval
        track = db.get_track_by_id(track_id)
        assert track is not None
        assert track["title"] == "Test Song"
        assert track["artist"] == "Test Artist"

    def test_search_tracks(self, tmp_path: Path) -> None:
        """Test FTS5 search."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        # Add tracks
        db.add_track(
            {
                "filepath": "/tmp/song1.mp3",
                "filename": "song1.mp3",
                "title": "Rock Song",
                "artist": "Rock Band",
            }
        )
        db.add_track(
            {
                "filepath": "/tmp/song2.mp3",
                "filename": "song2.mp3",
                "title": "Jazz Song",
                "artist": "Jazz Band",
            }
        )

        # Search
        results = db.search_tracks("Rock")
        assert len(results) == 1
        assert results[0]["title"] == "Rock Song"

    def test_record_play(self, tmp_path: Path) -> None:
        """Test recording play history."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        track_id = db.add_track({"filepath": "/tmp/test.mp3", "filename": "test.mp3"})

        # Record play
        db.record_play(track_id, 180.5, True)

        # Verify play count
        track = db.get_track_by_id(track_id)
        assert track is not None
        assert track["play_count"] == 1
