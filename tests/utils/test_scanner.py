"""Tests for file scanner."""

from pathlib import Path
from unittest.mock import patch

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

        # Mock MetadataExtractor to return valid metadata
        def mock_extract(filepath: Path) -> dict:
            return {
                "filepath": str(filepath),
                "filename": filepath.name,
                "file_size": filepath.stat().st_size,
                "date_modified": filepath.stat().st_mtime,
                "duration_seconds": 180.0,
            }

        scanner = FileScanner(db, ["mp3"])
        with patch("jukebox.utils.scanner.MetadataExtractor.extract", side_effect=mock_extract):
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

    def test_scan_skips_empty_audio_files(self, tmp_path: Path) -> None:
        """Test that scanner skips empty/invalid audio files."""
        # Create test files
        (tmp_path / "valid.mp3").touch()
        (tmp_path / "empty.mp3").touch()

        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()

        scanner = FileScanner(db, ["mp3"])

        # Mock MetadataExtractor to raise ValueError for empty.mp3
        def mock_extract(filepath: Path) -> dict:
            if filepath.name == "empty.mp3":
                raise ValueError("Empty audio file")
            return {
                "filepath": str(filepath),
                "filename": filepath.name,
                "file_size": filepath.stat().st_size,
                "date_modified": filepath.stat().st_mtime,
                "duration_seconds": 180.0,
            }

        with patch("jukebox.utils.scanner.MetadataExtractor.extract", side_effect=mock_extract):
            added = scanner.scan_directory(tmp_path, recursive=False)

        # Only 1 file should be added (empty.mp3 should be skipped)
        assert added == 1
        tracks = db.get_all_tracks()
        assert len(tracks) == 1
        assert tracks[0]["filename"] == "valid.mp3"
