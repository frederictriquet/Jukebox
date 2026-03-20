"""Utility module for writing audio file tags using mutagen."""

import logging
from pathlib import Path
from typing import Any


def _register_easyid3_comment() -> None:
    """Register 'comment' key in EasyID3 so it maps to COMM frames."""
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import COMM

    def getter(id3: Any, key: str) -> list[str]:
        for k in id3:
            if k.startswith("COMM"):
                return [str(id3[k])]
        return []

    def setter(id3: Any, key: str, value: list[str]) -> None:
        for k in list(id3):
            if k.startswith("COMM"):
                del id3[k]
        if value and value[0]:
            id3.add(COMM(encoding=3, lang="eng", desc="", text=value[0]))

    def deleter(id3: Any, key: str) -> None:
        for k in list(id3):
            if k.startswith("COMM"):
                del id3[k]

    if "comment" not in EasyID3.valid_keys:
        EasyID3.RegisterKey("comment", getter, setter, deleter)


# Register on module import
_register_easyid3_comment()


def save_audio_tags(
    filepath: str | Path,
    tags: dict[str, str],
    *,
    lowercase_tags_for_non_mp3: bool = True,
) -> bool:
    """Save tags to audio file using mutagen.

    This function handles both MP3 files (using EasyID3) and other formats
    (FLAC, AIFF, WAV, etc.) using generic mutagen File interface.

    Args:
        filepath: Path to audio file
        tags: Dict mapping tag names to values. Empty string deletes the tag.
              For MP3: uses standard tag names (artist, title, album, genre, date,
              comment, etc.)
              For non-MP3: tag names are lowercased by default unless disabled
        lowercase_tags_for_non_mp3: If True, use lowercase tag names for non-MP3 formats.
                                    Set to False to preserve tag name casing.

    Returns:
        True if tags were saved successfully, False otherwise

    Example:
        >>> save_audio_tags("/path/to/song.mp3", {"artist": "Artist Name", "genre": "Rock"})
        True
        >>> save_audio_tags("/path/to/song.flac", {"artist": "", "genre": "Jazz"})  # Delete artist
        True
    """
    from mutagen import File
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3NoHeaderError

    filepath_str = str(filepath)

    try:
        if filepath_str.lower().endswith(".mp3"):
            # Use EasyID3 for MP3 files
            try:
                audio: Any = EasyID3(filepath_str)
            except ID3NoHeaderError:
                # No ID3 tag exists, create one
                audio = File(filepath_str, easy=True)
                if audio is None:
                    logging.warning(f"Failed to open MP3 file: {filepath_str}")
                    return False
                audio.add_tags()

            # Update tags
            for tag_name, value in tags.items():
                if value:
                    # Set tag (EasyID3 expects lists)
                    audio[tag_name] = [value]
                elif tag_name in audio:
                    # Delete tag if value is empty
                    del audio[tag_name]

            audio.save()

        else:
            # Use generic mutagen for FLAC, AIFF, WAV, etc.
            audio = File(filepath_str)
            if audio is None:
                logging.warning(f"Unsupported file format: {filepath_str}")
                return False

            # Update tags
            for tag_name, value in tags.items():
                # Normalize tag name for non-MP3 formats
                normalized_tag = tag_name.lower() if lowercase_tags_for_non_mp3 else tag_name

                if value:
                    # Set tag (mutagen expects lists for most formats)
                    audio[normalized_tag] = [value]
                elif normalized_tag in audio:
                    # Delete tag if value is empty
                    del audio[normalized_tag]

            audio.save()

        logging.debug(f"Successfully saved tags to: {filepath_str}")
        return True

    except Exception as e:
        logging.error(f"Failed to save tags to {filepath_str}: {e}")
        return False
