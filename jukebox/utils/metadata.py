"""Audio metadata extraction using mutagen."""

import logging
from pathlib import Path
from typing import Any

import mutagen


class MetadataExtractor:
    """Extract metadata from audio files."""

    @staticmethod
    def extract(filepath: Path) -> dict[str, Any]:
        """Extract metadata from audio file.

        Args:
            filepath: Path to audio file

        Returns:
            Dictionary with metadata

        Raises:
            ValueError: If audio file is empty or invalid
        """
        try:
            audio = mutagen.File(filepath)
            if audio is None:
                logging.warning(f"Mutagen returned None for {filepath}")
                raise ValueError(f"Invalid audio file: {filepath}")

            metadata: dict[str, Any] = {
                "filepath": str(filepath),
                "filename": filepath.name,
                "file_size": filepath.stat().st_size,
                "date_modified": filepath.stat().st_mtime,
            }

            # Duration - validate that file has content
            if hasattr(audio.info, "length"):
                duration = audio.info.length
                if duration <= 0:
                    raise ValueError(f"Empty audio file (duration: {duration}): {filepath}")
                metadata["duration_seconds"] = duration
            else:
                # If we can't determine duration, file is likely invalid
                raise ValueError(f"Cannot determine duration for: {filepath}")

            # Bitrate
            if hasattr(audio.info, "bitrate"):
                metadata["bitrate"] = audio.info.bitrate

            # Sample rate
            if hasattr(audio.info, "sample_rate"):
                metadata["sample_rate"] = audio.info.sample_rate

            # Tags
            tags = MetadataExtractor._extract_tags(audio)
            metadata.update(tags)

            return metadata

        except ValueError:
            # Re-raise ValueError (empty/invalid file)
            raise
        except Exception as e:
            logging.error(f"Error extracting metadata from {filepath}: {e}", exc_info=True)
            raise ValueError(f"Failed to extract metadata from {filepath}: {e}") from e

    @staticmethod
    def _extract_tags(audio: Any) -> dict[str, Any]:
        """Extract tag information."""
        tags: dict[str, Any] = {}

        # Title
        tags["title"] = MetadataExtractor._get_tag(audio, ["TIT2", "title", "\xa9nam"])

        # Artist
        tags["artist"] = MetadataExtractor._get_tag(audio, ["TPE1", "artist", "\xa9ART"])

        # Album
        tags["album"] = MetadataExtractor._get_tag(audio, ["TALB", "album", "\xa9alb"])

        # Album Artist
        tags["album_artist"] = MetadataExtractor._get_tag(audio, ["TPE2", "albumartist", "aART"])

        # Genre
        tags["genre"] = MetadataExtractor._get_tag(audio, ["TCON", "genre", "\xa9gen"])

        # Year
        year_str = MetadataExtractor._get_tag(audio, ["TDRC", "date", "\xa9day"])
        if year_str:
            try:
                tags["year"] = int(str(year_str)[:4])
            except (ValueError, TypeError):
                pass  # noqa: SIM105

        # Track number
        track_str = MetadataExtractor._get_tag(audio, ["TRCK", "tracknumber", "trkn"])
        if track_str:
            try:
                track_num = str(track_str).split("/")[0]
                tags["track_number"] = int(track_num)
            except (ValueError, TypeError):
                pass  # noqa: SIM105

        return tags

    @staticmethod
    def _get_tag(audio: Any, keys: list[str]) -> str | None:
        """Get tag value from audio file.

        Args:
            audio: Mutagen audio file
            keys: List of possible tag keys

        Returns:
            Tag value or None
        """
        for key in keys:
            try:
                if key in audio:
                    value = audio[key]
                    if isinstance(value, list) and value:
                        return str(value[0])
                    return str(value)
            except (KeyError, ValueError):
                # Mutagen FLAC raises ValueError in __contains__ for invalid keys
                continue

        return None

    @staticmethod
    def _basic_info(filepath: Path) -> dict[str, Any]:
        """Return basic file info without metadata.

        Args:
            filepath: Path to file

        Returns:
            Basic file information
        """
        return {
            "filepath": str(filepath),
            "filename": filepath.name,
            "file_size": filepath.stat().st_size,
            "date_modified": filepath.stat().st_mtime,
        }
