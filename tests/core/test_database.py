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

    def test_add_track_with_mode(self, tmp_path: Path) -> None:
        """Test adding a track with mode."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        # Add to jukebox mode
        jukebox_id = db.add_track(
            {"filepath": "/tmp/jukebox.mp3", "filename": "jukebox.mp3", "title": "Jukebox Song"},
            mode="jukebox",
        )

        # Add to curating mode
        curating_id = db.add_track(
            {"filepath": "/tmp/curating.mp3", "filename": "curating.mp3", "title": "Curating Song"},
            mode="curating",
        )

        # Verify both tracks exist
        jukebox_track = db.get_track_by_id(jukebox_id)
        curating_track = db.get_track_by_id(curating_id)

        assert jukebox_track is not None
        assert jukebox_track["mode"] == "jukebox"
        assert curating_track is not None
        assert curating_track["mode"] == "curating"

    def test_get_all_tracks_with_mode_filter(self, tmp_path: Path) -> None:
        """Test filtering tracks by mode."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        # Add tracks to both modes
        db.add_track({"filepath": "/tmp/jukebox1.mp3", "filename": "jukebox1.mp3"}, mode="jukebox")
        db.add_track({"filepath": "/tmp/jukebox2.mp3", "filename": "jukebox2.mp3"}, mode="jukebox")
        db.add_track(
            {"filepath": "/tmp/curating1.mp3", "filename": "curating1.mp3"}, mode="curating"
        )

        # Get all tracks (no filter)
        all_tracks = db.get_all_tracks()
        assert len(all_tracks) == 3

        # Filter by jukebox mode
        jukebox_tracks = db.get_all_tracks(mode="jukebox")
        assert len(jukebox_tracks) == 2
        for track in jukebox_tracks:
            assert track["mode"] == "jukebox"

        # Filter by curating mode
        curating_tracks = db.get_all_tracks(mode="curating")
        assert len(curating_tracks) == 1
        assert curating_tracks[0]["mode"] == "curating"

    def test_search_tracks_with_mode(self, tmp_path: Path) -> None:
        """Test FTS5 search with mode filter."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        # Add tracks to different modes
        db.add_track(
            {
                "filepath": "/tmp/rock_jukebox.mp3",
                "filename": "rock_jukebox.mp3",
                "title": "Rock Song",
                "artist": "Rock Band",
            },
            mode="jukebox",
        )
        db.add_track(
            {
                "filepath": "/tmp/rock_curating.mp3",
                "filename": "rock_curating.mp3",
                "title": "Rock Track",
                "artist": "Another Rock Band",
            },
            mode="curating",
        )

        # Search in jukebox mode
        jukebox_results = db.search_tracks("Rock", mode="jukebox")
        assert len(jukebox_results) == 1
        assert jukebox_results[0]["filename"] == "rock_jukebox.mp3"

        # Search in curating mode
        curating_results = db.search_tracks("Rock", mode="curating")
        assert len(curating_results) == 1
        assert curating_results[0]["filename"] == "rock_curating.mp3"

        # Search without mode filter
        all_results = db.search_tracks("Rock")
        assert len(all_results) == 2

    def test_update_track_mode(self, tmp_path: Path) -> None:
        """Test updating track mode."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        track_id = db.add_track(
            {"filepath": "/tmp/test.mp3", "filename": "test.mp3"}, mode="jukebox"
        )

        # Verify initial mode
        track = db.get_track_by_id(track_id)
        assert track is not None
        assert track["mode"] == "jukebox"

        # Update to curating mode
        result = db.update_track_mode(track_id, "curating")
        assert result is True

        # Verify update
        track = db.get_track_by_id(track_id)
        assert track is not None
        assert track["mode"] == "curating"

        # Update non-existent track
        result = db.update_track_mode(99999, "jukebox")
        assert result is False

    def test_migration_adds_mode_column(self, tmp_path: Path) -> None:
        """Test that migration adds mode column to existing tracks."""
        db = Database(tmp_path / "test.db")
        db.connect()

        # Create old schema without mode column
        db.conn.execute(
            """
            CREATE TABLE tracks (
                id INTEGER PRIMARY KEY,
                filepath TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                title TEXT,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        db.conn.execute(
            "INSERT INTO tracks (filepath, filename, title) VALUES (?, ?, ?)",
            ("/tmp/old.mp3", "old.mp3", "Old Song"),
        )
        db.conn.commit()

        # Run migration
        db._migrate_track_mode()

        # Verify mode column exists with default value 'curating'
        track = db.conn.execute("SELECT mode FROM tracks").fetchone()
        assert track is not None
        assert track["mode"] == "curating"
