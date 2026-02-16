"""Tests for cue maker exporter module."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from plugins.cue_maker.exporter import CueExporter
from plugins.cue_maker.model import CueEntry, CueSheet, EntryStatus


class TestCueExporter:
    """Test CueExporter class."""

    def test_ms_to_cue_time_zero(self) -> None:
        """Test conversion of zero milliseconds."""
        result = CueExporter.ms_to_cue_time(0)
        assert result == "00:00:00"

    def test_ms_to_cue_time_seconds_only(self) -> None:
        """Test conversion of seconds without minutes."""
        result = CueExporter.ms_to_cue_time(45000)  # 45 seconds
        assert result == "00:45:00"

    def test_ms_to_cue_time_with_minutes(self) -> None:
        """Test conversion with minutes and seconds."""
        result = CueExporter.ms_to_cue_time(185000)  # 3:05
        assert result == "03:05:00"

    def test_ms_to_cue_time_with_frames(self) -> None:
        """Test conversion with fractional seconds (frames)."""
        result = CueExporter.ms_to_cue_time(185500)  # 3:05.5 = 3:05:37 (37.5 frames)
        assert result == "03:05:37"

    def test_ms_to_cue_time_full_frame(self) -> None:
        """Test conversion with almost full second (74 frames)."""
        result = CueExporter.ms_to_cue_time(185986)  # 3:05.986 ≈ 3:05:74
        assert result == "03:05:73"

    def test_ms_to_display_time_zero(self) -> None:
        """Test display time for zero."""
        result = CueExporter.ms_to_display_time(0)
        assert result == "00:00"

    def test_ms_to_display_time_seconds(self) -> None:
        """Test display time for seconds."""
        result = CueExporter.ms_to_display_time(45000)
        assert result == "00:45"

    def test_ms_to_display_time_minutes(self) -> None:
        """Test display time with minutes."""
        result = CueExporter.ms_to_display_time(185000)
        assert result == "03:05"

    def test_ms_to_display_time_truncates_milliseconds(self) -> None:
        """Test display time truncates milliseconds."""
        result = CueExporter.ms_to_display_time(185999)
        assert result == "03:05"

    def test_display_time_to_ms_valid_zero(self) -> None:
        """Test parsing zero time."""
        result = CueExporter.display_time_to_ms("00:00")
        assert result == 0

    def test_display_time_to_ms_valid_seconds(self) -> None:
        """Test parsing seconds only."""
        result = CueExporter.display_time_to_ms("00:45")
        assert result == 45000

    def test_display_time_to_ms_valid_minutes(self) -> None:
        """Test parsing minutes and seconds."""
        result = CueExporter.display_time_to_ms("03:05")
        assert result == 185000

    def test_display_time_to_ms_valid_large_minutes(self) -> None:
        """Test parsing large minute values."""
        result = CueExporter.display_time_to_ms("120:30")
        assert result == 7230000

    def test_display_time_to_ms_invalid_format_no_colon(self) -> None:
        """Test parsing invalid format without colon."""
        result = CueExporter.display_time_to_ms("0145")
        assert result is None

    def test_display_time_to_ms_invalid_format_too_many_colons(self) -> None:
        """Test parsing invalid format with too many colons."""
        result = CueExporter.display_time_to_ms("01:45:30")
        assert result is None

    def test_display_time_to_ms_invalid_seconds_too_large(self) -> None:
        """Test parsing invalid seconds (>59)."""
        result = CueExporter.display_time_to_ms("01:60")
        assert result is None

    def test_display_time_to_ms_invalid_seconds_negative(self) -> None:
        """Test parsing negative seconds."""
        result = CueExporter.display_time_to_ms("01:-10")
        assert result is None

    def test_display_time_to_ms_invalid_non_numeric(self) -> None:
        """Test parsing non-numeric values."""
        result = CueExporter.display_time_to_ms("aa:bb")
        assert result is None

    def test_escape_quotes_no_quotes(self) -> None:
        """Test escaping text without quotes."""
        result = CueExporter._escape_quotes("Normal text")
        assert result == "Normal text"

    def test_escape_quotes_with_quotes(self) -> None:
        """Test escaping text with quotes."""
        result = CueExporter._escape_quotes('Text with "quotes"')
        assert result == 'Text with \\"quotes\\"'

    def test_escape_quotes_multiple_quotes(self) -> None:
        """Test escaping multiple quotes."""
        result = CueExporter._escape_quotes('"Start" and "End"')
        assert result == '\\"Start\\" and \\"End\\"'

    def test_export_raises_on_no_confirmed_entries(self) -> None:
        """Test export raises ValueError when no confirmed entries."""
        sheet = CueSheet(
            mix_filepath="/path/to/mix.mp3",
            mix_title="Test Mix",
            mix_artist="DJ Test",
        )

        entry = CueEntry(60000, "Artist", "Title", 0.9, 180000)
        entry.status = EntryStatus.PENDING
        sheet.add_entry(entry)

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.cue"

            with pytest.raises(ValueError, match="No confirmed entries"):
                CueExporter.export(sheet, output_path)

    def test_export_creates_valid_cue_file(self) -> None:
        """Test export creates a valid CUE file with correct format."""
        sheet = CueSheet(
            mix_filepath="/path/to/test_mix.mp3",
            mix_title="Test Mix",
            mix_artist="DJ Test",
        )

        entry1 = CueEntry(0, "Artist 1", "Title 1", 0.95, 180000)
        entry1.status = EntryStatus.CONFIRMED

        entry2 = CueEntry(185000, "Artist 2", "Title 2", 1.0, 200000)
        entry2.status = EntryStatus.MANUAL

        sheet.add_entry(entry1)
        sheet.add_entry(entry2)

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.cue"
            CueExporter.export(sheet, output_path)

            assert output_path.exists()

            content = output_path.read_text(encoding="utf-8")

            # Check header
            assert 'PERFORMER "DJ Test"' in content
            assert 'TITLE "Test Mix"' in content
            assert 'FILE "test_mix.mp3" MP3' in content

            # Check tracks
            assert "  TRACK 01 AUDIO" in content
            assert '    PERFORMER "Artist 1"' in content
            assert '    TITLE "Title 1"' in content
            assert "    INDEX 01 00:00:00" in content

            assert "  TRACK 02 AUDIO" in content
            assert '    PERFORMER "Artist 2"' in content
            assert '    TITLE "Title 2"' in content
            assert "    INDEX 01 03:05:00" in content

    def test_export_skips_rejected_entries(self) -> None:
        """Test export only includes confirmed and manual entries."""
        sheet = CueSheet(
            mix_filepath="/path/to/mix.mp3",
            mix_title="Mix",
            mix_artist="DJ",
        )

        entry1 = CueEntry(0, "Artist 1", "Title 1", 0.95, 180000)
        entry1.status = EntryStatus.CONFIRMED

        entry2 = CueEntry(60000, "Artist 2", "Title 2", 0.80, 150000)
        entry2.status = EntryStatus.REJECTED

        entry3 = CueEntry(120000, "Artist 3", "Title 3", 1.0, 200000)
        entry3.status = EntryStatus.MANUAL

        sheet.add_entry(entry1)
        sheet.add_entry(entry2)
        sheet.add_entry(entry3)

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.cue"
            CueExporter.export(sheet, output_path)

            content = output_path.read_text(encoding="utf-8")

            # Should have 2 tracks (not 3)
            assert "  TRACK 01 AUDIO" in content
            assert "  TRACK 02 AUDIO" in content
            assert "  TRACK 03 AUDIO" not in content

            # Should include Artist 1 and 3, not 2
            assert "Artist 1" in content
            assert "Artist 2" not in content
            assert "Artist 3" in content

    def test_export_handles_different_audio_formats(self) -> None:
        """Test export detects audio format from extension."""
        formats = [
            ("test.mp3", "MP3"),
            ("test.flac", "FLAC"),
            ("test.wav", "WAV"),
            ("test.aiff", "AIFF"),
            ("test.aif", "AIF"),
            ("test.ogg", "MP3"),  # Unsupported falls back to MP3
        ]

        for filename, expected_format in formats:
            sheet = CueSheet(
                mix_filepath=f"/path/to/{filename}",
                mix_title="Mix",
                mix_artist="DJ",
            )

            entry = CueEntry(0, "Artist", "Title", 1.0, 180000)
            entry.status = EntryStatus.CONFIRMED
            sheet.add_entry(entry)

            with TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "test.cue"
                CueExporter.export(sheet, output_path)

                content = output_path.read_text(encoding="utf-8")
                assert f'FILE "{filename}" {expected_format}' in content

    def test_export_escapes_quotes_in_metadata(self) -> None:
        """Test export escapes quotes in artist and title."""
        sheet = CueSheet(
            mix_filepath="/path/to/mix.mp3",
            mix_title='Mix "Special Edition"',
            mix_artist='DJ "The Pro"',
        )

        entry = CueEntry(0, 'Artist "Quoted"', 'Title "Special"', 1.0, 180000)
        entry.status = EntryStatus.CONFIRMED
        sheet.add_entry(entry)

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.cue"
            CueExporter.export(sheet, output_path)

            content = output_path.read_text(encoding="utf-8")

            assert 'PERFORMER "DJ \\"The Pro\\""' in content
            assert 'TITLE "Mix \\"Special Edition\\""' in content
            assert 'PERFORMER "Artist \\"Quoted\\""' in content
            assert 'TITLE "Title \\"Special\\""' in content

    def test_export_handles_empty_artist_or_title(self) -> None:
        """Test export handles empty artist or title gracefully."""
        sheet = CueSheet(
            mix_filepath="/path/to/mix.mp3",
            mix_title="",
            mix_artist="",
        )

        entry = CueEntry(0, "", "", 1.0, 180000)
        entry.status = EntryStatus.CONFIRMED
        sheet.add_entry(entry)

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.cue"
            CueExporter.export(sheet, output_path)

            content = output_path.read_text(encoding="utf-8")

            # Should not have PERFORMER/TITLE lines for empty values
            assert 'PERFORMER ""' not in content
            assert 'TITLE ""' not in content

            # But should still have FILE and TRACK
            assert "FILE" in content
            assert "TRACK 01 AUDIO" in content

    def test_export_uses_only_filename_not_full_path(self) -> None:
        """Test export uses only filename in FILE line, not full path."""
        sheet = CueSheet(
            mix_filepath="/very/long/path/to/my/mix.mp3",
            mix_title="Mix",
            mix_artist="DJ",
        )

        entry = CueEntry(0, "Artist", "Title", 1.0, 180000)
        entry.status = EntryStatus.CONFIRMED
        sheet.add_entry(entry)

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.cue"
            CueExporter.export(sheet, output_path)

            content = output_path.read_text(encoding="utf-8")

            # Should use only filename
            assert 'FILE "mix.mp3" MP3' in content
            # Should not include full path
            assert "/very/long/path" not in content

    def test_export_tracks_are_numbered_sequentially(self) -> None:
        """Test exported tracks are numbered 01, 02, 03, etc."""
        sheet = CueSheet(
            mix_filepath="/path/to/mix.mp3",
            mix_title="Mix",
            mix_artist="DJ",
        )

        for i in range(5):
            entry = CueEntry(i * 60000, f"Artist {i}", f"Title {i}", 1.0, 60000)
            entry.status = EntryStatus.CONFIRMED
            sheet.add_entry(entry)

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.cue"
            CueExporter.export(sheet, output_path)

            content = output_path.read_text(encoding="utf-8")

            assert "  TRACK 01 AUDIO" in content
            assert "  TRACK 02 AUDIO" in content
            assert "  TRACK 03 AUDIO" in content
            assert "  TRACK 04 AUDIO" in content
            assert "  TRACK 05 AUDIO" in content
