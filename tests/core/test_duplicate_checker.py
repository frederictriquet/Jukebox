"""Tests for DuplicateChecker — automatic duplicate detection logic."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from jukebox.core.duplicate_checker import DuplicateChecker, DuplicateStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_db(tmp_path: Path, jukebox_tracks: list[dict[str, Any]]) -> Path:
    """Create a minimal SQLite database populated with jukebox tracks.

    Only the columns read by DuplicateChecker are required:
    filepath, artist, title, mode.
    """
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath TEXT,
            artist TEXT,
            title TEXT,
            mode TEXT DEFAULT 'jukebox'
        )
        """
    )
    for t in jukebox_tracks:
        conn.execute(
            "INSERT INTO tracks (filepath, artist, title, mode) VALUES (?, ?, ?, ?)",
            (
                t.get("filepath", "/music/unknown.mp3"),
                t.get("artist", ""),
                t.get("title", ""),
                t.get("mode", "jukebox"),
            ),
        )
    conn.commit()
    conn.close()
    return db_path


def make_checker(tmp_path: Path, jukebox_tracks: list[dict[str, Any]]) -> DuplicateChecker:
    """Convenience: create DB + checker in one call."""
    db_path = make_db(tmp_path, jukebox_tracks)
    return DuplicateChecker(db_path)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


class TestNormalize:
    """Tests for DuplicateChecker._normalize (static)."""

    def test_lowercases_text(self) -> None:
        assert DuplicateChecker._normalize("Rock Band") == "rock band"

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert DuplicateChecker._normalize("  hello  ") == "hello"

    def test_removes_punctuation(self) -> None:
        assert DuplicateChecker._normalize("Rock's Best!") == "rocks best"

    def test_preserves_digits(self) -> None:
        assert DuplicateChecker._normalize("Track 99") == "track 99"

    def test_empty_string(self) -> None:
        assert DuplicateChecker._normalize("") == ""


class TestNormalizeFilename:
    """Tests for DuplicateChecker._normalize_filename (static)."""

    def test_removes_extension(self) -> None:
        assert DuplicateChecker._normalize_filename("song.mp3") == "song"

    def test_lowercases(self) -> None:
        assert DuplicateChecker._normalize_filename("MyTrack.mp3") == "mytrack"

    def test_replaces_dashes_with_spaces(self) -> None:
        result = DuplicateChecker._normalize_filename("artist-title.mp3")
        assert "artist" in result
        assert "title" in result

    def test_replaces_underscores_with_spaces(self) -> None:
        result = DuplicateChecker._normalize_filename("artist_title.mp3")
        assert "artist" in result
        assert "title" in result

    def test_replaces_dots_in_stem(self) -> None:
        result = DuplicateChecker._normalize_filename("some.song.mp3")
        # Only last extension removed; internal dots become spaces
        assert "some" in result
        assert "song" in result

    def test_empty_filename(self) -> None:
        assert DuplicateChecker._normalize_filename("") == ""


class TestParseFilename:
    """Tests for DuplicateChecker._parse_filename (static)."""

    def test_parses_artist_dash_title(self) -> None:
        artist, title = DuplicateChecker._parse_filename("Daft Punk - Get Lucky.mp3")
        assert artist == "Daft Punk"
        assert title == "Get Lucky"

    def test_no_separator_returns_empty_artist(self) -> None:
        artist, title = DuplicateChecker._parse_filename("GetLucky.mp3")
        assert artist == ""
        assert title == "GetLucky"

    def test_multiple_separators_splits_on_first(self) -> None:
        artist, title = DuplicateChecker._parse_filename("A - B - C.mp3")
        assert artist == "A"
        assert title == "B - C"

    def test_strips_whitespace_from_parts(self) -> None:
        artist, title = DuplicateChecker._parse_filename("  Artist  -  Title  .mp3")
        assert artist == "Artist"
        assert title == "Title"


class TestMakeDisplay:
    """Tests for DuplicateChecker._make_display (static)."""

    def test_artist_and_title(self) -> None:
        assert (
            DuplicateChecker._make_display("Daft Punk", "Get Lucky", "x.mp3")
            == "Daft Punk - Get Lucky"
        )

    def test_title_only(self) -> None:
        assert DuplicateChecker._make_display("", "Get Lucky", "x.mp3") == "Get Lucky"

    def test_filename_fallback(self) -> None:
        assert DuplicateChecker._make_display("", "", "fallback.mp3") == "fallback.mp3"


class TestTokenize:
    """Tests for DuplicateChecker._tokenize."""

    def test_returns_words_of_min_length(self) -> None:
        checker = DuplicateChecker.__new__(DuplicateChecker)
        result = checker._tokenize("get lucky daft")
        assert result == {"get", "lucky", "daft"}

    def test_filters_short_words(self) -> None:
        checker = DuplicateChecker.__new__(DuplicateChecker)
        result = checker._tokenize("a bb ccc dddd")
        # MIN_TOKEN_LENGTH = 3 → "a" and "bb" filtered out
        assert "a" not in result
        assert "bb" not in result
        assert "ccc" in result
        assert "dddd" in result

    def test_empty_string(self) -> None:
        checker = DuplicateChecker.__new__(DuplicateChecker)
        assert checker._tokenize("") == set()


# ---------------------------------------------------------------------------
# Pass 1 — Exact (artist, title) match
# ---------------------------------------------------------------------------


class TestPass1ExactMatch:
    """Tests for the exact artist+title matching pass."""

    def test_exact_match_returns_red(self, tmp_path: Path) -> None:
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        result = checker.check({"artist": "Daft Punk", "title": "Get Lucky", "filename": ""})
        assert result.status == DuplicateStatus.RED
        assert result.match_info == "Daft Punk - Get Lucky"

    def test_exact_match_is_case_insensitive(self, tmp_path: Path) -> None:
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        result = checker.check({"artist": "daft punk", "title": "get lucky", "filename": ""})
        assert result.status == DuplicateStatus.RED

    def test_exact_match_ignores_punctuation(self, tmp_path: Path) -> None:
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "AC/DC", "title": "Back in Black"}],
        )
        result = checker.check({"artist": "ACDC", "title": "Back in Black", "filename": ""})
        assert result.status == DuplicateStatus.RED

    def test_no_exact_match_continues_to_next_pass(self, tmp_path: Path) -> None:
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        result = checker.check(
            {"artist": "Another Artist", "title": "Another Song", "filename": ""}
        )
        # Should not return RED (no exact match)
        assert result.status != DuplicateStatus.RED

    def test_missing_artist_skips_pass1(self, tmp_path: Path) -> None:
        """When artist is empty, pass 1 should be skipped entirely."""
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        # artist is empty → pass 1 skipped → result can't be RED from this pass
        result = checker.check({"artist": "", "title": "Get Lucky", "filename": ""})
        # Should not be RED (pass 1 skipped due to missing artist)
        assert result.status != DuplicateStatus.RED

    def test_missing_title_skips_pass1(self, tmp_path: Path) -> None:
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        result = checker.check({"artist": "Daft Punk", "title": "", "filename": ""})
        assert result.status != DuplicateStatus.RED

    def test_curating_tracks_excluded_from_index(self, tmp_path: Path) -> None:
        """Tracks with mode='curating' should NOT be in the jukebox index."""
        checker = make_checker(
            tmp_path,
            [
                {
                    "filepath": "/music/jb.mp3",
                    "artist": "Jukebox Artist",
                    "title": "Jukebox Song",
                    "mode": "jukebox",
                },
                {
                    "filepath": "/cur/cur.mp3",
                    "artist": "Curating Artist",
                    "title": "Curating Song",
                    "mode": "curating",
                },
            ],
        )
        # Curating track: should return GREEN
        result = checker.check(
            {"artist": "Curating Artist", "title": "Curating Song", "filename": ""}
        )
        assert result.status == DuplicateStatus.GREEN


# ---------------------------------------------------------------------------
# Pass 2 — Filename parse match
# ---------------------------------------------------------------------------


class TestPass2FilenameParseMatch:
    """Tests for the filename-parse matching pass."""

    def test_filename_artist_title_exact_match_red(self, tmp_path: Path) -> None:
        """Filename 'Artist - Title.mp3' parsed → exact match → RED."""
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        result = checker.check({"artist": "", "title": "", "filename": "Daft Punk - Get Lucky.mp3"})
        assert result.status == DuplicateStatus.RED
        assert result.match_info == "Daft Punk - Get Lucky"

    def test_filename_title_only_match_orange(self, tmp_path: Path) -> None:
        """Filename without ' - ' → title-only lookup → ORANGE."""
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "GetLucky"}],
        )
        # Filename has no ' - ' → parsed as ("", "GetLucky")
        result = checker.check({"artist": "", "title": "", "filename": "GetLucky.mp3"})
        assert result.status == DuplicateStatus.ORANGE

    def test_filename_parse_no_match(self, tmp_path: Path) -> None:
        """Filename doesn't parse to any known track → None (pass continues)."""
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        result = checker.check(
            {"artist": "", "title": "", "filename": "Completely Unknown Track.mp3"}
        )
        # No match in pass 2 → may continue to fuzzy or return GREEN
        assert result.status != DuplicateStatus.RED

    def test_filename_parse_case_insensitive(self, tmp_path: Path) -> None:
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "daft punk", "title": "get lucky"}],
        )
        result = checker.check({"artist": "", "title": "", "filename": "DAFT PUNK - GET LUCKY.mp3"})
        assert result.status == DuplicateStatus.RED


# ---------------------------------------------------------------------------
# Pass 3 — Fuzzy filename match
# ---------------------------------------------------------------------------


class TestPass3FuzzyMatch:
    """Tests for the token-accelerated fuzzy filename matching pass."""

    def test_high_similarity_returns_orange(self, tmp_path: Path) -> None:
        """Very similar filenames (>= 0.8 ratio) should match as ORANGE."""
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/daft-punk-get-lucky.mp3", "artist": "", "title": ""}],
        )
        # Slightly different but very similar filename
        result = checker.check({"artist": "", "title": "", "filename": "daft punk get lucky.mp3"})
        assert result.status == DuplicateStatus.ORANGE

    def test_low_similarity_returns_green(self, tmp_path: Path) -> None:
        """Unrelated filenames should not match."""
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/beethoven-symphony.mp3", "artist": "", "title": ""}],
        )
        result = checker.check(
            {"artist": "", "title": "", "filename": "totally_different_song.mp3"}
        )
        assert result.status == DuplicateStatus.GREEN

    def test_exact_filename_match_is_orange(self, tmp_path: Path) -> None:
        """Same filename (without artist/title) triggers fuzzy pass → ORANGE."""
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/my_great_track.mp3", "artist": "", "title": ""}],
        )
        result = checker.check({"artist": "", "title": "", "filename": "my_great_track.mp3"})
        # No artist/title in index → exact/parse passes fail → fuzzy catches it
        assert result.status == DuplicateStatus.ORANGE


# ---------------------------------------------------------------------------
# No duplicate
# ---------------------------------------------------------------------------


class TestGreenResult:
    """Tests for tracks with no duplicate."""

    def test_empty_database_returns_green(self, tmp_path: Path) -> None:
        checker = make_checker(tmp_path, [])
        result = checker.check({"artist": "Unknown", "title": "Song", "filename": "song.mp3"})
        assert result.status == DuplicateStatus.GREEN
        assert result.match_info is None

    def test_no_matching_tracks_returns_green(self, tmp_path: Path) -> None:
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        result = checker.check(
            {"artist": "Mozart", "title": "Symphony 40", "filename": "mozart.mp3"}
        )
        assert result.status == DuplicateStatus.GREEN

    def test_empty_track_dict_returns_green(self, tmp_path: Path) -> None:
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        result = checker.check({"artist": "", "title": "", "filename": ""})
        assert result.status == DuplicateStatus.GREEN


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------


class TestIndexManagement:
    """Tests for lazy index building, invalidation, and rebuild."""

    def test_index_built_lazily_on_first_check(self, tmp_path: Path) -> None:
        db_path = make_db(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        checker = DuplicateChecker(db_path)
        assert not checker._index_built
        checker.check({"artist": "Daft Punk", "title": "Get Lucky", "filename": ""})
        assert checker._index_built

    def test_invalidate_index_marks_stale(self, tmp_path: Path) -> None:
        db_path = make_db(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        checker = DuplicateChecker(db_path)
        checker.rebuild_index()
        assert checker._index_built
        checker.invalidate_index()
        assert not checker._index_built

    def test_invalidate_triggers_rebuild_on_next_check(self, tmp_path: Path) -> None:
        db_path = make_db(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        checker = DuplicateChecker(db_path)
        checker.rebuild_index()
        checker.invalidate_index()

        # Add another jukebox track directly to DB
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO tracks (filepath, artist, title, mode) VALUES (?, ?, ?, ?)",
            ("/music/new.mp3", "New Artist", "New Song", "jukebox"),
        )
        conn.commit()
        conn.close()

        # After invalidation, next check should rebuild and find new track
        result = checker.check({"artist": "New Artist", "title": "New Song", "filename": ""})
        assert result.status == DuplicateStatus.RED

    def test_rebuild_index_explicit(self, tmp_path: Path) -> None:
        db_path = make_db(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        checker = DuplicateChecker(db_path)
        checker.rebuild_index()
        assert checker._index_built
        assert len(checker._exact_index) == 1

    def test_db_error_gracefully_returns_green(self, tmp_path: Path) -> None:
        """If the DB file is missing, checker should return GREEN without crashing."""
        db_path = tmp_path / "nonexistent.db"
        checker = DuplicateChecker(db_path)
        result = checker.check({"artist": "Daft Punk", "title": "Get Lucky", "filename": ""})
        assert result.status == DuplicateStatus.GREEN


# ---------------------------------------------------------------------------
# recheck_tracks
# ---------------------------------------------------------------------------


class TestRecheckTracks:
    """Tests for the recheck_tracks() batch update method."""

    def test_recheck_updates_status_in_place(self, tmp_path: Path) -> None:
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        tracks = [
            {
                "artist": "Daft Punk",
                "title": "Get Lucky",
                "filename": "",
                "duplicate_status": "pending",
            },
        ]
        checker.recheck_tracks(tracks)
        assert tracks[0]["duplicate_status"] == "red"
        assert tracks[0]["duplicate_match"] == "Daft Punk - Get Lucky"

    def test_recheck_returns_true_when_status_changed(self, tmp_path: Path) -> None:
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        tracks = [
            {
                "artist": "Daft Punk",
                "title": "Get Lucky",
                "filename": "",
                "duplicate_status": "pending",
            }
        ]
        changed = checker.recheck_tracks(tracks)
        assert changed is True

    def test_recheck_returns_false_when_nothing_changed(self, tmp_path: Path) -> None:
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        tracks = [
            {
                "artist": "Daft Punk",
                "title": "Get Lucky",
                "filename": "",
                "duplicate_status": "red",
                "duplicate_match": "Daft Punk - Get Lucky",
            }
        ]
        changed = checker.recheck_tracks(tracks)
        assert changed is False

    def test_recheck_handles_empty_list(self, tmp_path: Path) -> None:
        checker = make_checker(tmp_path, [])
        changed = checker.recheck_tracks([])
        assert changed is False

    def test_recheck_mixed_tracks(self, tmp_path: Path) -> None:
        """Some tracks match, some don't."""
        checker = make_checker(
            tmp_path,
            [{"filepath": "/music/track.mp3", "artist": "Daft Punk", "title": "Get Lucky"}],
        )
        tracks = [
            {
                "artist": "Daft Punk",
                "title": "Get Lucky",
                "filename": "",
                "duplicate_status": "pending",
            },
            {
                "artist": "Mozart",
                "title": "Symphony",
                "filename": "",
                "duplicate_status": "pending",
            },
        ]
        checker.recheck_tracks(tracks)
        assert tracks[0]["duplicate_status"] == "red"
        assert tracks[1]["duplicate_status"] == "green"
