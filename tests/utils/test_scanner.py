"""Tests for file scanner."""

from pathlib import Path

import pytest

from jukebox.core.database import Database
from jukebox.utils.scanner import FileScanner


class TestFileScanner:
    """Test suite for FileScanner."""

    def test_find_audio_files(self, tmp_path: Path) -> None:
        """Test finding audio files."""
        # Create test files
        (tmp_path / "song1.mp3").touch()
        (tmp_path / "song2.flac").touch()
        (tmp_path / "other.txt").touch()

        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        scanner = FileScanner(db, ["mp3", "flac"])
        files = scanner._find_audio_files(tmp_path, recursive=False)

        assert len(files) == 2
        assert any(f.name == "song1.mp3" for f in files)
        assert any(f.name == "song2.flac" for f in files)

    def test_scan_directory(self, tmp_path: Path) -> None:
        """Test scanning directory."""
        # Create test files
        (tmp_path / "song1.mp3").touch()
        (tmp_path / "song2.mp3").touch()

        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        scanner = FileScanner(db, ["mp3"])
        added = scanner.scan_directory(tmp_path, recursive=False)

        assert added == 2
        assert len(db.get_all_tracks()) == 2

    def test_scan_nonexistent_directory(self, tmp_path: Path) -> None:
        """Test scanning non-existent directory raises error."""
        db = Database(tmp_path / "test.db")
        db.connect()

        scanner = FileScanner(db, ["mp3"])

        with pytest.raises(ValueError):
            scanner.scan_directory(tmp_path / "nonexistent")
