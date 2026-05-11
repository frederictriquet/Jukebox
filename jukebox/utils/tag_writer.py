"""Utility module for writing audio file tags using mutagen."""

import logging
from pathlib import Path
from typing import Any

# Mapping nom de tag → frame ID3 pour formats ID3-based (AIFF, WAV)
# Les classes Frame sont importées de façon lazy dans save_audio_tags
_TAG_TO_ID3_FRAME_ID: dict[str, str] = {
    "genre":        "TCON",
    "title":        "TIT2",
    "artist":       "TPE1",
    "album":        "TALB",
    "year":         "TDRC",
    "date":         "TDRC",
    "album_artist": "TPE2",
    "albumartist":  "TPE2",
}


def _register_easyid3_comment() -> None:
    """Register 'comment' key in EasyID3 so it maps to COMM frames."""
    from mutagen.easyid3 import EasyID3  # type: ignore[import-untyped]
    from mutagen.id3 import COMM  # type: ignore[import-untyped]

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


# Enregistrement à l'import du module
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
    from mutagen import File  # type: ignore[import-untyped]
    from mutagen.easyid3 import EasyID3  # type: ignore[import-untyped]
    from mutagen.id3 import COMM, ID3, TALB, TDRC, TCON, TIT2, TPE1, TPE2  # type: ignore[import-untyped]
    from mutagen.id3 import ID3NoHeaderError  # type: ignore[import-untyped]

    # Mapping nom de tag → classe Frame ID3 (utilisé pour AIFF/WAV)
    _tag_to_id3_class: dict[str, type] = {
        "TCON": TCON,
        "TIT2": TIT2,
        "TPE1": TPE1,
        "TALB": TALB,
        "TDRC": TDRC,
        "TPE2": TPE2,
    }

    filepath_str = str(filepath)

    try:
        if filepath_str.lower().endswith(".mp3"):
            # Utilisation d'EasyID3 pour les fichiers MP3
            try:
                audio: Any = EasyID3(filepath_str)
            except ID3NoHeaderError:
                # Aucun tag ID3 existant, en créer un
                audio = File(filepath_str, easy=True)
                if audio is None:
                    logging.warning(f"Failed to open MP3 file: {filepath_str}")
                    return False
                audio.add_tags()

            # Mise à jour des tags
            for tag_name, value in tags.items():
                if value:
                    # EasyID3 attend des listes
                    audio[tag_name] = [value]
                elif tag_name in audio:
                    # Suppression du tag si la valeur est vide
                    del audio[tag_name]

            audio.save()

        else:
            # Utilisation de l'interface générique mutagen pour FLAC, AIFF, WAV, etc.
            audio = File(filepath_str)
            if audio is None:
                logging.warning(f"Unsupported file format: {filepath_str}")
                return False

            # Détecter si les tags sont ID3-based (AIFF, WAV utilisent ID3 au lieu de Vorbis comments)
            is_id3_based = isinstance(getattr(audio, "tags", None), ID3)

            for tag_name, value in tags.items():
                # Normalisation du nom de tag pour les formats non-MP3
                normalized_tag = tag_name.lower() if lowercase_tags_for_non_mp3 else tag_name

                if is_id3_based:
                    if normalized_tag == "comment":
                        # COMM requiert des paramètres spéciaux
                        comm_key = "COMM::eng"
                        if value:
                            audio.tags[comm_key] = COMM(encoding=3, lang="eng", desc="", text=value)
                        elif comm_key in audio.tags:
                            del audio.tags[comm_key]
                    elif normalized_tag in _TAG_TO_ID3_FRAME_ID:
                        frame_id = _TAG_TO_ID3_FRAME_ID[normalized_tag]
                        frame_class = _tag_to_id3_class[frame_id]
                        if value:
                            audio.tags[frame_id] = frame_class(encoding=3, text=[value])
                        elif frame_id in audio.tags:
                            del audio.tags[frame_id]
                else:
                    # Formats Vorbis comments (FLAC, OGG, etc.)
                    if value:
                        audio[normalized_tag] = [value]
                    elif normalized_tag in audio:
                        del audio[normalized_tag]

            audio.save()

        logging.debug(f"Successfully saved tags to: {filepath_str}")
        return True

    except Exception as e:
        logging.error(f"Failed to save tags to {filepath_str}: {e}")
        return False
