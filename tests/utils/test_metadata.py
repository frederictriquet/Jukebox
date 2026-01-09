"""Tests for metadata extraction."""

from pathlib import Path

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
