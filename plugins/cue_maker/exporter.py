"""CUE file exporter."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from plugins.cue_maker.model import CueSheet

if TYPE_CHECKING:
    from plugins.cue_maker.model import CueEntry

logger = logging.getLogger(__name__)


class CueExporter:
    """Export cue sheets to standard CUE format.

    Exports only confirmed and manual entries to ensure quality.
    Format follows the standard CUE sheet specification compatible
    with CDJs, Rekordbox, VirtualDJ, etc.
    """

    @staticmethod
    def export(cue_sheet: CueSheet, output_path: str | Path) -> None:
        """Export cue sheet to .cue file.

        Args:
            cue_sheet: Cue sheet to export
            output_path: Path where to write the .cue file

        Raises:
            IOError: If file cannot be written
            ValueError: If cue sheet has no confirmed entries
        """
        entries = cue_sheet.get_confirmed_entries()
        if not entries:
            raise ValueError("No confirmed entries to export")

        output_path = Path(output_path)
        mix_path = Path(cue_sheet.mix_filepath)

        # Determine audio file format
        audio_format = mix_path.suffix[1:].upper()  # Remove dot and uppercase
        if audio_format not in ("MP3", "FLAC", "WAV", "AIFF", "AIF"):
            audio_format = "MP3"  # Default fallback

        lines = []

        # Header
        if cue_sheet.mix_artist:
            lines.append(f'PERFORMER "{CueExporter._escape_quotes(cue_sheet.mix_artist)}"')
        if cue_sheet.mix_title:
            lines.append(f'TITLE "{CueExporter._escape_quotes(cue_sheet.mix_title)}"')

        # File reference (just the filename, not full path)
        lines.append(f'FILE "{mix_path.name}" {audio_format}')

        # Tracks
        for track_num, entry in enumerate(entries, start=1):
            lines.append(f"  TRACK {track_num:02d} AUDIO")

            if entry.artist:
                lines.append(f'    PERFORMER "{CueExporter._escape_quotes(entry.artist)}"')
            if entry.title:
                lines.append(f'    TITLE "{CueExporter._escape_quotes(entry.title)}"')

            # INDEX 01 marks the start of the track
            cue_time = CueExporter.ms_to_cue_time(entry.start_time_ms)
            lines.append(f"    INDEX 01 {cue_time}")

        # Write file
        content = "\n".join(lines) + "\n"
        output_path.write_text(content, encoding="utf-8")

        logger.info("[Cue Exporter] Exported %d tracks to %s", len(entries), output_path)

    @staticmethod
    def ms_to_cue_time(ms: int) -> str:
        """Convert milliseconds to CUE time format MM:SS:FF.

        In CUE format, frames (FF) represent 1/75th of a second.

        Args:
            ms: Time in milliseconds

        Returns:
            Time string in MM:SS:FF format

        Example:
            >>> CueExporter.ms_to_cue_time(185000)
            '03:05:00'
        """
        total_seconds = ms / 1000.0
        minutes = int(total_seconds // 60)
        seconds = int(total_seconds % 60)
        # Frames: 1 frame = 1/75 second
        frames = int((total_seconds - int(total_seconds)) * 75)
        return f"{minutes:02d}:{seconds:02d}:{frames:02d}"

    @staticmethod
    def ms_to_display_time(ms: int) -> str:
        """Convert milliseconds to MM:SS for display.

        Args:
            ms: Time in milliseconds

        Returns:
            Time string in MM:SS format

        Example:
            >>> CueExporter.ms_to_display_time(185000)
            '03:05'
        """
        total_seconds = ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def display_time_to_ms(time_str: str) -> int | None:
        """Convert MM:SS string to milliseconds.

        Args:
            time_str: Time string in MM:SS format

        Returns:
            Time in milliseconds, or None if invalid format

        Example:
            >>> CueExporter.display_time_to_ms("03:05")
            185000
        """
        import re

        match = re.match(r"^(\d{1,3}):([0-5]\d)$", time_str)
        if not match:
            return None

        minutes = int(match.group(1))
        seconds = int(match.group(2))
        return (minutes * 60 + seconds) * 1000

    @staticmethod
    def _escape_quotes(text: str) -> str:
        """Escape double quotes in text for CUE format.

        Args:
            text: Text to escape

        Returns:
            Escaped text
        """
        return text.replace('"', '\\"')

    @staticmethod
    def cue_time_to_ms(cue_time: str) -> int:
        """Convert CUE time format MM:SS:FF to milliseconds.

        Args:
            cue_time: Time string in MM:SS:FF format (FF = 1/75th second frames)

        Returns:
            Time in milliseconds
        """
        parts = cue_time.split(":")
        if len(parts) != 3:
            return 0
        minutes = int(parts[0])
        seconds = int(parts[1])
        frames = int(parts[2])
        return int((minutes * 60 + seconds + frames / 75.0) * 1000)

    @staticmethod
    def parse(filepath: str | Path) -> list[CueEntry]:
        """Parse a .cue file and return a list of CueEntry objects.

        Args:
            filepath: Path to the .cue file

        Returns:
            List of CueEntry objects parsed from the file

        Raises:
            OSError: If file cannot be read
            ValueError: If file contains no valid tracks
        """
        import re

        from plugins.cue_maker.model import CueEntry, EntryStatus

        filepath = Path(filepath)
        content = filepath.read_text(encoding="utf-8")

        entries: list[CueEntry] = []
        current_artist = ""
        current_title = ""
        current_index_ms = 0

        for line in content.splitlines():
            line = line.strip()

            # Track-level PERFORMER
            match = re.match(r'PERFORMER\s+"(.*)"', line)
            if match:
                current_artist = match.group(1).replace('\\"', '"')
                continue

            # Track-level TITLE
            match = re.match(r'TITLE\s+"(.*)"', line)
            if match:
                current_title = match.group(1).replace('\\"', '"')
                continue

            # INDEX 01 marks track start
            match = re.match(r"INDEX\s+01\s+(\d+:\d+:\d+)", line)
            if match:
                current_index_ms = CueExporter.cue_time_to_ms(match.group(1))
                entries.append(
                    CueEntry(
                        start_time_ms=current_index_ms,
                        artist=current_artist,
                        title=current_title,
                        confidence=1.0,
                        duration_ms=0,
                        status=EntryStatus.CONFIRMED,
                    )
                )
                # Reset per-track fields
                current_artist = ""
                current_title = ""

        if not entries:
            raise ValueError("No valid tracks found in CUE file")

        # Compute durations from gaps between consecutive entries
        for i in range(len(entries) - 1):
            entries[i].duration_ms = entries[i + 1].start_time_ms - entries[i].start_time_ms

        logger.info("[Cue Exporter] Parsed %d entries from %s", len(entries), filepath)
        return entries
