"""Tests for repository classes."""

from pathlib import Path
from typing import Any

import pytest

from jukebox.core.database import Database
from jukebox.core.repositories import (
    AnalysisRepository,
    BaseRepository,
    PluginSettingsRepository,
    TrackRepository,
    WaveformRepository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_db(tmp_path: Path) -> Database:
    """Create a connected, schema-initialised Database in *tmp_path*."""
    db = Database(tmp_path / "test.db")
    db.connect()
    db.initialize_schema()
    return db


def sample_track(
    filepath: str = "/tmp/test.mp3",
    filename: str = "test.mp3",
    title: str = "Test Song",
    artist: str = "Test Artist",
    **extra: Any,
) -> dict[str, Any]:
    """Return a minimal track-data dict."""
    data: dict[str, Any] = {
        "filepath": filepath,
        "filename": filename,
        "title": title,
        "artist": artist,
    }
    data.update(extra)
    return data


# ---------------------------------------------------------------------------
# BaseRepository
# ---------------------------------------------------------------------------


class TestBaseRepository:
    """Tests for BaseRepository._conn and _commit helpers."""

    def test_conn_raises_when_not_connected(self, tmp_path: Path) -> None:
        """_conn should raise RuntimeError if the database has no connection."""
        db = Database(tmp_path / "no_connect.db")
        repo = TrackRepository(db)  # any subclass works
        with pytest.raises(RuntimeError, match="not connected"):
            _ = repo._conn

    def test_conn_returns_connection_when_connected(self, tmp_path: Path) -> None:
        """_conn should return the sqlite3 connection after connect()."""
        db = make_db(tmp_path)
        repo = TrackRepository(db)
        import sqlite3

        assert isinstance(repo._conn, sqlite3.Connection)

    def test_commit_inside_transaction_does_not_commit(self, tmp_path: Path) -> None:
        """_commit should be a no-op when _in_transaction is True."""
        db = make_db(tmp_path)
        repo = TrackRepository(db)
        db._in_transaction = True
        # Should not raise and should not actually commit
        repo._commit()
        db._in_transaction = False

    def test_commit_outside_transaction_commits(self, tmp_path: Path) -> None:
        """_commit should call conn.commit() when not inside a transaction."""
        db = make_db(tmp_path)
        repo = TrackRepository(db)
        # Insert a row manually without committing, then call _commit
        db.conn.execute(
            "INSERT INTO tracks (filepath, filename) VALUES (?, ?)",
            ("/tmp/commit_test.mp3", "commit_test.mp3"),
        )
        repo._commit()
        row = db.conn.execute(
            "SELECT id FROM tracks WHERE filepath = ?", ("/tmp/commit_test.mp3",)
        ).fetchone()
        assert row is not None


# ---------------------------------------------------------------------------
# TrackRepository
# ---------------------------------------------------------------------------


class TestTrackRepositoryAdd:
    """Tests for TrackRepository.add."""

    def test_add_returns_positive_id(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        assert track_id > 0

    def test_add_persists_all_provided_fields(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        data = sample_track(
            filepath="/tmp/full.mp3",
            filename="full.mp3",
            title="Full Song",
            artist="Full Artist",
            album="Full Album",
            album_artist="Album Artist",
            genre="Pop",
            year=2020,
            track_number=3,
            duration_seconds=210.5,
            bitrate=320,
            sample_rate=44100,
            file_size=8000000,
        )
        track_id = db.tracks.add(data)
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["title"] == "Full Song"
        assert row["artist"] == "Full Artist"
        assert row["album"] == "Full Album"
        assert row["album_artist"] == "Album Artist"
        assert row["genre"] == "Pop"
        assert row["year"] == 2020
        assert row["track_number"] == 3
        assert row["duration_seconds"] == pytest.approx(210.5)
        assert row["bitrate"] == 320
        assert row["sample_rate"] == 44100
        assert row["file_size"] == 8000000

    def test_add_defaults_to_jukebox_mode(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["mode"] == "jukebox"

    def test_add_respects_explicit_mode(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track(filepath="/tmp/cur.mp3", filename="cur.mp3"), mode="curating")
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["mode"] == "curating"

    def test_add_replace_on_duplicate_filepath(self, tmp_path: Path) -> None:
        """INSERT OR REPLACE should overwrite an existing track with the same filepath."""
        db = make_db(tmp_path)
        db.tracks.add(sample_track(title="Original"))
        db.tracks.add(sample_track(title="Replaced"))
        all_tracks = db.tracks.get_all()
        assert len(all_tracks) == 1
        assert all_tracks[0]["title"] == "Replaced"

    def test_add_optional_fields_default_to_none(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add({"filepath": "/tmp/bare.mp3", "filename": "bare.mp3"})
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["title"] is None
        assert row["artist"] is None
        assert row["album"] is None


class TestTrackRepositoryGetAll:
    """Tests for TrackRepository.get_all."""

    def test_get_all_empty_database(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        assert db.tracks.get_all() == []

    def test_get_all_returns_all_tracks(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        for i in range(3):
            db.tracks.add(sample_track(filepath=f"/tmp/t{i}.mp3", filename=f"t{i}.mp3"))
        assert len(db.tracks.get_all()) == 3

    def test_get_all_mode_filter_jukebox(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.tracks.add(sample_track(filepath="/tmp/j.mp3", filename="j.mp3"), mode="jukebox")
        db.tracks.add(sample_track(filepath="/tmp/c.mp3", filename="c.mp3"), mode="curating")
        results = db.tracks.get_all(mode="jukebox")
        assert len(results) == 1
        assert results[0]["mode"] == "jukebox"

    def test_get_all_mode_filter_curating(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.tracks.add(sample_track(filepath="/tmp/j.mp3", filename="j.mp3"), mode="jukebox")
        db.tracks.add(sample_track(filepath="/tmp/c.mp3", filename="c.mp3"), mode="curating")
        results = db.tracks.get_all(mode="curating")
        assert len(results) == 1
        assert results[0]["mode"] == "curating"

    def test_get_all_no_mode_filter_returns_both_modes(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.tracks.add(sample_track(filepath="/tmp/j.mp3", filename="j.mp3"), mode="jukebox")
        db.tracks.add(sample_track(filepath="/tmp/c.mp3", filename="c.mp3"), mode="curating")
        assert len(db.tracks.get_all()) == 2

    def test_get_all_limit(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        for i in range(5):
            db.tracks.add(sample_track(filepath=f"/tmp/t{i}.mp3", filename=f"t{i}.mp3"))
        assert len(db.tracks.get_all(limit=2)) == 2

    def test_get_all_limit_with_mode(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        for i in range(4):
            db.tracks.add(sample_track(filepath=f"/tmp/j{i}.mp3", filename=f"j{i}.mp3"), mode="jukebox")
        results = db.tracks.get_all(limit=2, mode="jukebox")
        assert len(results) == 2


class TestTrackRepositoryGetById:
    """Tests for TrackRepository.get_by_id."""

    def test_get_by_id_found(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track(title="By ID"))
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["title"] == "By ID"
        assert row["id"] == track_id

    def test_get_by_id_not_found(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        assert db.tracks.get_by_id(999999) is None


class TestTrackRepositoryGetByFilepath:
    """Tests for TrackRepository.get_by_filepath."""

    def test_get_by_filepath_string(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.tracks.add(sample_track(filepath="/tmp/fp.mp3", filename="fp.mp3"))
        row = db.tracks.get_by_filepath("/tmp/fp.mp3")
        assert row is not None
        assert row["filename"] == "fp.mp3"

    def test_get_by_filepath_path_object(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.tracks.add(sample_track(filepath="/tmp/fp2.mp3", filename="fp2.mp3"))
        row = db.tracks.get_by_filepath(Path("/tmp/fp2.mp3"))
        assert row is not None
        assert row["filename"] == "fp2.mp3"

    def test_get_by_filepath_not_found(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        assert db.tracks.get_by_filepath("/does/not/exist.mp3") is None


class TestTrackRepositoryDelete:
    """Tests for TrackRepository.delete and delete_by_filepath."""

    def test_delete_existing_track(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        assert db.tracks.delete(track_id) is True
        assert db.tracks.get_by_id(track_id) is None

    def test_delete_nonexistent_track(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        assert db.tracks.delete(999999) is False

    def test_delete_by_filepath_existing(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.tracks.add(sample_track(filepath="/tmp/del.mp3", filename="del.mp3"))
        assert db.tracks.delete_by_filepath("/tmp/del.mp3") is True
        assert db.tracks.get_by_filepath("/tmp/del.mp3") is None

    def test_delete_by_filepath_path_object(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.tracks.add(sample_track(filepath="/tmp/del2.mp3", filename="del2.mp3"))
        assert db.tracks.delete_by_filepath(Path("/tmp/del2.mp3")) is True

    def test_delete_by_filepath_not_found(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        assert db.tracks.delete_by_filepath("/no/such/file.mp3") is False


class TestTrackRepositoryUpdateMetadata:
    """Tests for TrackRepository.update_metadata."""

    def test_update_allowed_single_field(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track(title="Old Title"))
        assert db.tracks.update_metadata(track_id, {"title": "New Title"}) is True
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["title"] == "New Title"

    def test_update_multiple_allowed_fields(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        updates = {"title": "Updated", "artist": "New Artist", "album": "New Album", "year": 2024}
        assert db.tracks.update_metadata(track_id, updates) is True
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["title"] == "Updated"
        assert row["artist"] == "New Artist"
        assert row["album"] == "New Album"
        assert row["year"] == 2024

    def test_update_all_allowed_fields(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        all_allowed = {
            "title": "T",
            "artist": "A",
            "album": "B",
            "album_artist": "AA",
            "genre": "G",
            "year": 2000,
            "track_number": 1,
            "duration_seconds": 99.9,
            "bitrate": 128,
            "sample_rate": 44100,
            "file_size": 1000,
            "date_modified": "2024-01-01",
        }
        assert db.tracks.update_metadata(track_id, all_allowed) is True

    def test_update_disallowed_field_is_ignored(self, tmp_path: Path) -> None:
        """Fields not in the allowed set must be silently filtered out."""
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track(filepath="/tmp/orig.mp3", filename="orig.mp3"))
        # 'filepath', 'id', and 'mode' are not in allowed_fields
        result = db.tracks.update_metadata(track_id, {"filepath": "/tmp/evil.mp3", "id": 42, "mode": "curating"})
        # All provided keys are disallowed → returns False (no update performed)
        assert result is False
        # Filepath must remain unchanged
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["filepath"] == "/tmp/orig.mp3"

    def test_update_mixed_allowed_and_disallowed(self, tmp_path: Path) -> None:
        """Disallowed keys are stripped; allowed keys still get applied."""
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track(title="Original"))
        result = db.tracks.update_metadata(track_id, {"title": "Changed", "id": 99, "mode": "curating"})
        assert result is True
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["title"] == "Changed"
        # Disallowed 'mode' should not have been applied
        assert row["mode"] == "jukebox"

    def test_update_metadata_nonexistent_track(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        assert db.tracks.update_metadata(999999, {"title": "Ghost"}) is False

    def test_update_metadata_empty_dict(self, tmp_path: Path) -> None:
        """Empty metadata dict has no allowed fields → False returned immediately."""
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        assert db.tracks.update_metadata(track_id, {}) is False


class TestTrackRepositoryUpdateFilepath:
    """Tests for TrackRepository.update_filepath."""

    def test_update_filepath_string(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track(filepath="/tmp/old.mp3", filename="old.mp3"))
        assert db.tracks.update_filepath(track_id, "/tmp/new.mp3") is True
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["filepath"] == "/tmp/new.mp3"
        assert row["filename"] == "new.mp3"

    def test_update_filepath_path_object(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track(filepath="/tmp/old2.mp3", filename="old2.mp3"))
        assert db.tracks.update_filepath(track_id, Path("/tmp/new2.mp3")) is True
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["filepath"] == "/tmp/new2.mp3"

    def test_update_filepath_explicit_filename(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track(filepath="/tmp/old3.mp3", filename="old3.mp3"))
        assert db.tracks.update_filepath(track_id, "/tmp/dir/new3.mp3", new_filename="custom.mp3") is True
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["filename"] == "custom.mp3"

    def test_update_filepath_nonexistent_track(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        assert db.tracks.update_filepath(999999, "/tmp/x.mp3") is False


class TestTrackRepositoryUpdateMode:
    """Tests for TrackRepository.update_mode."""

    def test_update_mode_jukebox_to_curating(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track(), mode="jukebox")
        assert db.tracks.update_mode(track_id, "curating") is True
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["mode"] == "curating"

    def test_update_mode_curating_to_jukebox(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track(), mode="curating")
        assert db.tracks.update_mode(track_id, "jukebox") is True
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["mode"] == "jukebox"

    def test_update_mode_nonexistent_track(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        assert db.tracks.update_mode(999999, "jukebox") is False


class TestTrackRepositoryRecordPlay:
    """Tests for TrackRepository.record_play."""

    def test_record_play_increments_play_count(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        db.tracks.record_play(track_id, 180.0, completed=True)
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["play_count"] == 1

    def test_record_play_multiple_times(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        db.tracks.record_play(track_id, 60.0, completed=False)
        db.tracks.record_play(track_id, 180.0, completed=True)
        db.tracks.record_play(track_id, 180.0, completed=True)
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["play_count"] == 3

    def test_record_play_sets_last_played(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        assert db.tracks.get_by_id(track_id)["last_played"] is None  # type: ignore[index]
        db.tracks.record_play(track_id, 120.0, completed=True)
        row = db.tracks.get_by_id(track_id)
        assert row is not None
        assert row["last_played"] is not None

    def test_record_play_writes_history_row(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        assert db.conn is not None
        track_id = db.tracks.add(sample_track())
        db.tracks.record_play(track_id, 95.5, completed=False)
        row = db.conn.execute(
            "SELECT * FROM play_history WHERE track_id = ?", (track_id,)
        ).fetchone()
        assert row is not None
        assert row["play_duration_seconds"] == pytest.approx(95.5)
        assert row["completed"] == 0  # False stored as 0

    def test_record_play_completed_flag(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        assert db.conn is not None
        track_id = db.tracks.add(sample_track())
        db.tracks.record_play(track_id, 200.0, completed=True)
        row = db.conn.execute(
            "SELECT completed FROM play_history WHERE track_id = ?", (track_id,)
        ).fetchone()
        assert row is not None
        assert row["completed"] == 1  # True stored as 1


class TestTrackRepositorySearch:
    """Tests for TrackRepository.search (FTS5)."""

    def _add_fixture_tracks(self, db: Database) -> None:
        db.tracks.add(
            sample_track(filepath="/tmp/rock.mp3", filename="rock.mp3", title="Rock Song", artist="Rock Band"),
            mode="jukebox",
        )
        db.tracks.add(
            sample_track(filepath="/tmp/jazz.mp3", filename="jazz.mp3", title="Jazz Tune", artist="Jazz Quartet"),
            mode="curating",
        )
        db.tracks.add(
            sample_track(filepath="/tmp/pop.mp3", filename="pop.mp3", title="Pop Hit", artist="Pop Star"),
            mode="jukebox",
        )

    def test_search_single_term_matches_title(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        self._add_fixture_tracks(db)
        results = db.tracks.search("Rock")
        assert len(results) == 1
        assert results[0]["title"] == "Rock Song"

    def test_search_single_term_matches_artist(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        self._add_fixture_tracks(db)
        results = db.tracks.search("Quartet")
        assert len(results) == 1
        assert results[0]["title"] == "Jazz Tune"

    def test_search_multi_term_narrows_results(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        self._add_fixture_tracks(db)
        results = db.tracks.search("Rock Song")
        assert len(results) == 1
        assert results[0]["title"] == "Rock Song"

    def test_search_no_match_returns_empty(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        self._add_fixture_tracks(db)
        assert db.tracks.search("Nonexistent") == []

    def test_search_with_mode_filter_jukebox(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        # Both modes have a track whose title contains "Song"
        db.tracks.add(
            sample_track(filepath="/tmp/j.mp3", filename="j.mp3", title="Happy Song"),
            mode="jukebox",
        )
        db.tracks.add(
            sample_track(filepath="/tmp/c.mp3", filename="c.mp3", title="Sad Song"),
            mode="curating",
        )
        results = db.tracks.search("Song", mode="jukebox")
        assert len(results) == 1
        assert results[0]["mode"] == "jukebox"

    def test_search_with_mode_filter_curating(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.tracks.add(
            sample_track(filepath="/tmp/j.mp3", filename="j.mp3", title="Happy Song"),
            mode="jukebox",
        )
        db.tracks.add(
            sample_track(filepath="/tmp/c.mp3", filename="c.mp3", title="Sad Song"),
            mode="curating",
        )
        results = db.tracks.search("Song", mode="curating")
        assert len(results) == 1
        assert results[0]["mode"] == "curating"

    def test_search_without_mode_returns_all_modes(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.tracks.add(
            sample_track(filepath="/tmp/j.mp3", filename="j.mp3", title="Happy Song"),
            mode="jukebox",
        )
        db.tracks.add(
            sample_track(filepath="/tmp/c.mp3", filename="c.mp3", title="Sad Song"),
            mode="curating",
        )
        results = db.tracks.search("Song")
        assert len(results) == 2

    def test_search_limit(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        for i in range(10):
            db.tracks.add(
                sample_track(filepath=f"/tmp/t{i}.mp3", filename=f"t{i}.mp3", title=f"Track {i}")
            )
        results = db.tracks.search("Track", limit=3)
        assert len(results) <= 3

    def test_search_fts5_special_chars_do_not_crash(self, tmp_path: Path) -> None:
        """Queries containing FTS5 special characters should not raise an exception."""
        db = make_db(tmp_path)
        db.tracks.add(sample_track(title="Hello World"))
        # These characters are normally FTS5 operators; the repository must escape them
        results = db.tracks.search('Hello "World"')
        assert isinstance(results, list)

    def test_search_case_insensitive(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.tracks.add(sample_track(title="Blues Brother"))
        results = db.tracks.search("blues")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# WaveformRepository
# ---------------------------------------------------------------------------


class TestWaveformRepository:
    """Tests for WaveformRepository."""

    def test_get_returns_none_when_no_cache(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        assert db.waveforms.get(track_id) is None

    def test_save_and_get_roundtrip(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        data = b"\x00\x01\x02\xff"
        db.waveforms.save(track_id, data)
        assert db.waveforms.get(track_id) == data

    def test_save_replaces_existing(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        db.waveforms.save(track_id, b"old data")
        db.waveforms.save(track_id, b"new data")
        assert db.waveforms.get(track_id) == b"new data"

    def test_delete_removes_cache(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        db.waveforms.save(track_id, b"some data")
        db.waveforms.delete(track_id)
        assert db.waveforms.get(track_id) is None

    def test_delete_nonexistent_does_not_raise(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        # No track, no waveform — should not raise
        db.waveforms.delete(999999)

    def test_get_tracks_without_waveform_all_missing(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        for i in range(3):
            db.tracks.add(sample_track(filepath=f"/tmp/t{i}.mp3", filename=f"t{i}.mp3"))
        missing = db.waveforms.get_tracks_without_waveform()
        assert len(missing) == 3

    def test_get_tracks_without_waveform_excludes_cached(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        t1 = db.tracks.add(sample_track(filepath="/tmp/a.mp3", filename="a.mp3"))
        t2 = db.tracks.add(sample_track(filepath="/tmp/b.mp3", filename="b.mp3"))
        db.waveforms.save(t1, b"waveform")
        missing = db.waveforms.get_tracks_without_waveform()
        assert len(missing) == 1
        assert missing[0]["id"] == t2

    def test_get_tracks_without_waveform_empty_when_all_cached(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        db.waveforms.save(track_id, b"data")
        assert db.waveforms.get_tracks_without_waveform() == []

    def test_get_tracks_without_waveform_mode_filter_jukebox(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        j_id = db.tracks.add(sample_track(filepath="/tmp/j.mp3", filename="j.mp3"), mode="jukebox")
        c_id = db.tracks.add(sample_track(filepath="/tmp/c.mp3", filename="c.mp3"), mode="curating")
        # Cache the jukebox track; curating track has no cache
        db.waveforms.save(j_id, b"jukebox waveform")
        # Without mode filter both modes appear; only curating track is missing
        all_missing = db.waveforms.get_tracks_without_waveform()
        assert len(all_missing) == 1
        assert all_missing[0]["id"] == c_id
        # With jukebox mode filter: nothing missing (jukebox track is cached)
        jukebox_missing = db.waveforms.get_tracks_without_waveform(mode="jukebox")
        assert jukebox_missing == []

    def test_get_tracks_without_waveform_mode_filter_curating(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.tracks.add(sample_track(filepath="/tmp/j.mp3", filename="j.mp3"), mode="jukebox")
        c_id = db.tracks.add(sample_track(filepath="/tmp/c.mp3", filename="c.mp3"), mode="curating")
        curating_missing = db.waveforms.get_tracks_without_waveform(mode="curating")
        assert len(curating_missing) == 1
        assert curating_missing[0]["id"] == c_id

    def test_get_tracks_without_waveform_limit(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        for i in range(5):
            db.tracks.add(sample_track(filepath=f"/tmp/t{i}.mp3", filename=f"t{i}.mp3"))
        results = db.waveforms.get_tracks_without_waveform(limit=2)
        assert len(results) == 2

    def test_get_tracks_without_waveform_no_tracks(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        assert db.waveforms.get_tracks_without_waveform() == []


# ---------------------------------------------------------------------------
# AnalysisRepository
# ---------------------------------------------------------------------------


class TestAnalysisRepository:
    """Tests for AnalysisRepository."""

    def test_get_returns_none_when_no_analysis(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        assert db.analysis.get(track_id) is None

    def test_exists_false_before_save(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        assert db.analysis.exists(track_id) is False

    def test_save_insert_and_get_roundtrip(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        db.analysis.save(track_id, {"tempo": 120.0, "energy": 0.8})
        row = db.analysis.get(track_id)
        assert row is not None
        assert row["track_id"] == track_id
        assert row["tempo"] == pytest.approx(120.0)
        assert row["energy"] == pytest.approx(0.8)

    def test_exists_true_after_save(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        db.analysis.save(track_id, {"tempo": 100.0})
        assert db.analysis.exists(track_id) is True

    def test_save_update_path(self, tmp_path: Path) -> None:
        """Calling save twice for the same track should update, not insert."""
        db = make_db(tmp_path)
        assert db.conn is not None
        track_id = db.tracks.add(sample_track())
        db.analysis.save(track_id, {"tempo": 90.0, "energy": 0.5})
        db.analysis.save(track_id, {"tempo": 130.0, "energy": 0.9})
        row = db.analysis.get(track_id)
        assert row is not None
        assert row["tempo"] == pytest.approx(130.0)
        assert row["energy"] == pytest.approx(0.9)
        # Confirm only one row exists
        count = db.conn.execute(
            "SELECT COUNT(*) as cnt FROM audio_analysis WHERE track_id = ?", (track_id,)
        ).fetchone()
        assert count is not None
        assert count["cnt"] == 1

    def test_save_update_partial_fields(self, tmp_path: Path) -> None:
        """Update with only a subset of fields; other fields are left unchanged."""
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        db.analysis.save(track_id, {"tempo": 100.0, "energy": 0.5})
        db.analysis.save(track_id, {"tempo": 110.0})
        row = db.analysis.get(track_id)
        assert row is not None
        assert row["tempo"] == pytest.approx(110.0)
        # energy was not touched in the second save, so it should remain
        assert row["energy"] == pytest.approx(0.5)

    def test_delete_removes_analysis(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        db.analysis.save(track_id, {"tempo": 100.0})
        db.analysis.delete(track_id)
        assert db.analysis.get(track_id) is None
        assert db.analysis.exists(track_id) is False

    def test_delete_nonexistent_does_not_raise(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.analysis.delete(999999)

    def test_get_tracks_without_analysis_all_missing(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        for i in range(3):
            db.tracks.add(sample_track(filepath=f"/tmp/t{i}.mp3", filename=f"t{i}.mp3"))
        missing = db.analysis.get_tracks_without_analysis()
        assert len(missing) == 3

    def test_get_tracks_without_analysis_excludes_analyzed(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        t1 = db.tracks.add(sample_track(filepath="/tmp/a.mp3", filename="a.mp3"))
        t2 = db.tracks.add(sample_track(filepath="/tmp/b.mp3", filename="b.mp3"))
        db.analysis.save(t1, {"tempo": 120.0})
        missing = db.analysis.get_tracks_without_analysis()
        assert len(missing) == 1
        assert missing[0]["id"] == t2

    def test_get_tracks_without_analysis_empty_when_all_analyzed(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        db.analysis.save(track_id, {"tempo": 100.0})
        assert db.analysis.get_tracks_without_analysis() == []

    def test_get_tracks_without_analysis_mode_filter_jukebox(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        j_id = db.tracks.add(sample_track(filepath="/tmp/j.mp3", filename="j.mp3"), mode="jukebox")
        c_id = db.tracks.add(sample_track(filepath="/tmp/c.mp3", filename="c.mp3"), mode="curating")
        db.analysis.save(j_id, {"tempo": 120.0})
        # Jukebox track is analyzed, curating is not
        jukebox_missing = db.analysis.get_tracks_without_analysis(mode="jukebox")
        assert jukebox_missing == []
        curating_missing = db.analysis.get_tracks_without_analysis(mode="curating")
        assert len(curating_missing) == 1
        assert curating_missing[0]["id"] == c_id

    def test_get_tracks_without_analysis_mode_filter_curating(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.tracks.add(sample_track(filepath="/tmp/j.mp3", filename="j.mp3"), mode="jukebox")
        c_id = db.tracks.add(sample_track(filepath="/tmp/c.mp3", filename="c.mp3"), mode="curating")
        curating_missing = db.analysis.get_tracks_without_analysis(mode="curating")
        assert len(curating_missing) == 1
        assert curating_missing[0]["id"] == c_id

    def test_get_tracks_without_analysis_no_mode_returns_both(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.tracks.add(sample_track(filepath="/tmp/j.mp3", filename="j.mp3"), mode="jukebox")
        db.tracks.add(sample_track(filepath="/tmp/c.mp3", filename="c.mp3"), mode="curating")
        missing = db.analysis.get_tracks_without_analysis()
        assert len(missing) == 2

    def test_get_tracks_without_analysis_limit(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        for i in range(5):
            db.tracks.add(sample_track(filepath=f"/tmp/t{i}.mp3", filename=f"t{i}.mp3"))
        results = db.analysis.get_tracks_without_analysis(limit=2)
        assert len(results) == 2

    def test_get_tracks_without_analysis_no_tracks(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        assert db.analysis.get_tracks_without_analysis() == []

    def test_save_empty_analysis_dict_inserts_row(self, tmp_path: Path) -> None:
        """Saving an empty dict should insert a row with only the track_id."""
        db = make_db(tmp_path)
        track_id = db.tracks.add(sample_track())
        db.analysis.save(track_id, {})
        assert db.analysis.exists(track_id) is True

    def test_save_multiple_tracks_independently(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        t1 = db.tracks.add(sample_track(filepath="/tmp/a.mp3", filename="a.mp3"))
        t2 = db.tracks.add(sample_track(filepath="/tmp/b.mp3", filename="b.mp3"))
        db.analysis.save(t1, {"tempo": 100.0})
        db.analysis.save(t2, {"tempo": 140.0})
        assert db.analysis.get(t1)["tempo"] == pytest.approx(100.0)  # type: ignore[index]
        assert db.analysis.get(t2)["tempo"] == pytest.approx(140.0)  # type: ignore[index]


# ---------------------------------------------------------------------------
# PluginSettingsRepository
# ---------------------------------------------------------------------------


class TestPluginSettingsRepository:
    """Tests for PluginSettingsRepository."""

    def test_get_returns_none_when_not_set(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        assert db.settings.get("my_plugin", "volume") is None

    def test_save_and_get_roundtrip(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.settings.save("my_plugin", "volume", "75")
        assert db.settings.get("my_plugin", "volume") == "75"

    def test_save_overwrites_existing_value(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.settings.save("my_plugin", "theme", "dark")
        db.settings.save("my_plugin", "theme", "light")
        assert db.settings.get("my_plugin", "theme") == "light"

    def test_settings_are_scoped_by_plugin_name(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.settings.save("plugin_a", "key", "value_a")
        db.settings.save("plugin_b", "key", "value_b")
        assert db.settings.get("plugin_a", "key") == "value_a"
        assert db.settings.get("plugin_b", "key") == "value_b"

    def test_settings_are_scoped_by_key(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.settings.save("my_plugin", "key1", "v1")
        db.settings.save("my_plugin", "key2", "v2")
        assert db.settings.get("my_plugin", "key1") == "v1"
        assert db.settings.get("my_plugin", "key2") == "v2"

    def test_get_unknown_key_for_known_plugin(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.settings.save("my_plugin", "known_key", "value")
        assert db.settings.get("my_plugin", "unknown_key") is None

    def test_save_empty_string_value(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        db.settings.save("my_plugin", "empty", "")
        assert db.settings.get("my_plugin", "empty") == ""

    def test_save_long_value(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        long_value = "x" * 10000
        db.settings.save("my_plugin", "big_key", long_value)
        assert db.settings.get("my_plugin", "big_key") == long_value


# ---------------------------------------------------------------------------
# Transaction integration
# ---------------------------------------------------------------------------


class TestTransactionIntegration:
    """Verify that repository operations respect database.transaction()."""

    def test_transaction_commits_multiple_operations(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        with db.transaction():
            t1 = db.tracks.add(sample_track(filepath="/tmp/a.mp3", filename="a.mp3"))
            t2 = db.tracks.add(sample_track(filepath="/tmp/b.mp3", filename="b.mp3"))
            db.waveforms.save(t1, b"wave1")
        assert db.tracks.get_by_id(t1) is not None
        assert db.tracks.get_by_id(t2) is not None
        assert db.waveforms.get(t1) == b"wave1"

    def test_transaction_rollback_on_error(self, tmp_path: Path) -> None:
        db = make_db(tmp_path)
        with pytest.raises(RuntimeError):
            with db.transaction():
                db.tracks.add(sample_track(filepath="/tmp/r.mp3", filename="r.mp3"))
                raise RuntimeError("forced rollback")
        assert db.tracks.get_by_filepath("/tmp/r.mp3") is None
