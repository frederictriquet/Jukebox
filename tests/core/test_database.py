"""Tests for database module."""

import pytest
from pathlib import Path

from jukebox.core.database import Database
from jukebox.core.repositories import (
    AnalysisRepository,
    PluginSettingsRepository,
    TrackRepository,
    WaveformRepository,
)


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
        tables = [row["name"] for row in cursor.fetchall()]

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


class TestDatabaseAdditional:
    """Additional tests covering repository properties, transaction manager, and delegate methods."""

    # ------------------------------------------------------------------
    # Repository properties
    # ------------------------------------------------------------------

    def test_tracks_property_returns_track_repository(self, tmp_path: Path) -> None:
        """Test that db.tracks returns a TrackRepository instance."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        assert isinstance(db.tracks, TrackRepository)

    def test_tracks_property_is_lazily_cached(self, tmp_path: Path) -> None:
        """Test that db.tracks returns the same instance on repeated access."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        first = db.tracks
        second = db.tracks
        assert first is second

    def test_waveforms_property_returns_waveform_repository(self, tmp_path: Path) -> None:
        """Test that db.waveforms returns a WaveformRepository instance."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        assert isinstance(db.waveforms, WaveformRepository)

    def test_analysis_property_returns_analysis_repository(self, tmp_path: Path) -> None:
        """Test that db.analysis returns an AnalysisRepository instance."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        assert isinstance(db.analysis, AnalysisRepository)

    def test_settings_property_returns_plugin_settings_repository(self, tmp_path: Path) -> None:
        """Test that db.settings returns a PluginSettingsRepository instance."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        assert isinstance(db.settings, PluginSettingsRepository)

    # ------------------------------------------------------------------
    # Transaction context manager
    # ------------------------------------------------------------------

    def test_transaction_commits_on_success(self, tmp_path: Path) -> None:
        """Test that changes inside a transaction() block are committed on success."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        with db.transaction():
            db.tracks.add({"filepath": "/tmp/tx.mp3", "filename": "tx.mp3", "title": "TX Song"})

        # Re-open the same database file to confirm the data was persisted
        db2 = Database(tmp_path / "test.db")
        db2.connect()
        tracks = db2.tracks.get_all()
        assert any(t["filepath"] == "/tmp/tx.mp3" for t in tracks)

    def test_transaction_rolls_back_on_exception(self, tmp_path: Path) -> None:
        """Test that changes are rolled back when an exception is raised inside transaction()."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        with pytest.raises(RuntimeError, match="intentional rollback"):
            with db.transaction():
                db.tracks.add(
                    {"filepath": "/tmp/rollback.mp3", "filename": "rollback.mp3"}
                )
                raise RuntimeError("intentional rollback")

        # The track must not be present
        tracks = db.tracks.get_all()
        assert not any(t["filepath"] == "/tmp/rollback.mp3" for t in tracks)

    def test_transaction_resets_in_transaction_flag(self, tmp_path: Path) -> None:
        """Test that _in_transaction flag is False after transaction completes."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        with db.transaction():
            assert db._in_transaction is True

        assert db._in_transaction is False

    def test_transaction_resets_flag_after_exception(self, tmp_path: Path) -> None:
        """Test that _in_transaction flag is reset to False even when an exception is raised."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        with pytest.raises(ValueError):
            with db.transaction():
                raise ValueError("boom")

        assert db._in_transaction is False

    def test_transaction_raises_when_not_connected(self, tmp_path: Path) -> None:
        """Test that transaction() raises RuntimeError when database is not connected."""
        db = Database(tmp_path / "test.db")

        with pytest.raises(RuntimeError, match="not connected"):
            with db.transaction():
                pass

    # ------------------------------------------------------------------
    # Delegate methods
    # ------------------------------------------------------------------

    def test_update_track_metadata_delegate(self, tmp_path: Path) -> None:
        """Test that update_track_metadata delegates to tracks.update_metadata."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        track_id = db.add_track(
            {"filepath": "/tmp/meta.mp3", "filename": "meta.mp3", "title": "Original"}
        )

        result = db.update_track_metadata(track_id, {"title": "Updated"})

        assert result is True
        track = db.get_track_by_id(track_id)
        assert track is not None
        assert track["title"] == "Updated"

    def test_update_track_metadata_nonexistent_returns_false(self, tmp_path: Path) -> None:
        """Test that update_track_metadata returns False for a nonexistent track."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        result = db.update_track_metadata(99999, {"title": "Ghost"})
        assert result is False

    def test_delete_track_delegate(self, tmp_path: Path) -> None:
        """Test that delete_track delegates to tracks.delete and removes the track."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        track_id = db.add_track({"filepath": "/tmp/del.mp3", "filename": "del.mp3"})

        result = db.delete_track(track_id)

        assert result is True
        assert db.get_track_by_id(track_id) is None

    def test_delete_track_nonexistent_returns_false(self, tmp_path: Path) -> None:
        """Test that delete_track returns False for a nonexistent track."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        result = db.delete_track(99999)
        assert result is False

    def test_save_waveform_and_get_waveform_delegates(self, tmp_path: Path) -> None:
        """Test save_waveform_cache / get_waveform_cache round-trip via repository delegates."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        track_id = db.add_track({"filepath": "/tmp/wave.mp3", "filename": "wave.mp3"})
        waveform_bytes = b"\x00\x01\x02\x03\xff"

        # Save via repository (waveforms.save) and retrieve via legacy delegate
        db.waveforms.save(track_id, waveform_bytes)
        retrieved = db.get_waveform_cache(track_id)

        assert retrieved == waveform_bytes

    def test_get_waveform_cache_returns_none_when_missing(self, tmp_path: Path) -> None:
        """Test that get_waveform_cache returns None when no waveform is cached."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        track_id = db.add_track({"filepath": "/tmp/nowave.mp3", "filename": "nowave.mp3"})
        assert db.get_waveform_cache(track_id) is None

    def test_has_audio_analysis_false_before_save(self, tmp_path: Path) -> None:
        """Test that has_audio_analysis returns False when no analysis has been saved."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        track_id = db.add_track({"filepath": "/tmp/noanalysis.mp3", "filename": "noanalysis.mp3"})
        assert db.has_audio_analysis(track_id) is False

    def test_has_audio_analysis_true_after_save(self, tmp_path: Path) -> None:
        """Test that has_audio_analysis returns True after saving analysis data."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        track_id = db.add_track(
            {"filepath": "/tmp/analysis.mp3", "filename": "analysis.mp3"}
        )
        db.save_audio_analysis(track_id, {"tempo": 120.0, "energy": 0.8})

        assert db.has_audio_analysis(track_id) is True

    def test_save_and_get_audio_analysis_delegate(self, tmp_path: Path) -> None:
        """Test that save_audio_analysis and get_audio_analysis round-trip correctly."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        track_id = db.add_track(
            {"filepath": "/tmp/analysisfull.mp3", "filename": "analysisfull.mp3"}
        )
        db.save_audio_analysis(track_id, {"tempo": 128.0, "energy": 0.9})

        result = db.get_audio_analysis(track_id)
        assert result is not None
        assert result["tempo"] == 128.0
        assert result["energy"] == 0.9
