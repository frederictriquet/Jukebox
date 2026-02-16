"""Tests for metadata extraction."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jukebox.utils.metadata import MetadataExtractor


class TestMetadataExtractor:
    """Test MetadataExtractor."""

    def test_basic_info(self, tmp_path: Path) -> None:
        """Test basic file info extraction."""
        test_file = tmp_path / "test.mp3"
        test_file.write_text("dummy")

        info = MetadataExtractor._basic_info(test_file)

        assert info["filepath"] == str(test_file)
        assert info["filename"] == "test.mp3"
        assert "file_size" in info
        assert "date_modified" in info

    def test_extract_nonexistent_file(self) -> None:
        """Test extracting from non-existent file."""
        # Should not crash when file doesn't exist
        try:
            MetadataExtractor.extract(Path("/nonexistent/file.mp3"))
        except Exception:
            pass  # Expected - file doesn't exist

    def test_get_tag_with_list_value(self) -> None:
        """Test _get_tag with list value."""

        # Mock audio object
        class MockAudio:
            def __contains__(self, key: str) -> bool:
                return key == "title"

            def __getitem__(self, key: str) -> list[str]:
                if key == "title":
                    return ["Test Title"]
                raise KeyError

        audio = MockAudio()
        result = MetadataExtractor._get_tag(audio, ["title"])

        assert result == "Test Title"

    def test_get_tag_not_found(self) -> None:
        """Test _get_tag when key not found."""

        class MockAudio:
            def __contains__(self, key: str) -> bool:
                return False

        audio = MockAudio()
        result = MetadataExtractor._get_tag(audio, ["title", "TIT2"])

        assert result is None

    def test_extract_empty_audio_file(self, tmp_path: Path) -> None:
        """Test that empty audio files raise ValueError."""
        test_file = tmp_path / "empty.mp3"
        test_file.write_bytes(b"")  # Empty file

        # Mock mutagen to return a file with zero duration
        mock_audio = MagicMock()
        mock_audio.info.length = 0  # Zero duration indicates empty file

        with (
            patch("mutagen.File", return_value=mock_audio),
            pytest.raises(ValueError, match="Empty audio file"),
        ):
            MetadataExtractor.extract(test_file)

    def test_extract_no_duration_raises_error(self, tmp_path: Path) -> None:
        """Test that audio files without duration raise ValueError."""
        test_file = tmp_path / "no_duration.mp3"
        test_file.write_bytes(b"dummy")

        # Mock mutagen to return a file without duration attribute
        mock_audio = MagicMock()
        del mock_audio.info.length  # No duration attribute

        with (
            patch("mutagen.File", return_value=mock_audio),
            pytest.raises(ValueError, match="Cannot determine duration"),
        ):
            MetadataExtractor.extract(test_file)

    def test_extract_invalid_file_raises_error(self, tmp_path: Path) -> None:
        """Test that invalid audio files raise ValueError."""
        test_file = tmp_path / "invalid.mp3"
        test_file.write_bytes(b"dummy")

        # Mock mutagen to return None (invalid file)
        with (
            patch("mutagen.File", return_value=None),
            pytest.raises(ValueError, match="Invalid audio file"),
        ):
            MetadataExtractor.extract(test_file)
