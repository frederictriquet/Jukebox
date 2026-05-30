"""Utility module for writing audio file tags using mutagen."""

import logging
from pathlib import Path
from typing import Any

# Mapping nom de tag → frame ID3 pour formats ID3-based (AIFF, WAV).
# La valeur est le nom de la classe Frame mutagen, résolue de façon lazy
# dans save_audio_tags (l'import de mutagen.id3 y est différé).
# Source de vérité unique : le frame ID est dérivé du nom de classe.
_TAG_TO_ID3_FRAME_CLASS_NAME: dict[str, str] = {
    "genre": "TCON",
    "title": "TIT2",
    "artist": "TPE1",
    "album": "TALB",
    "year": "TDRC",
    "date": "TDRC",
    "album_artist": "TPE2",
    "albumartist": "TPE2",
}


def _register_easyid3_comment() -> None:
    """Register 'comment' key in EasyID3 so it maps to COMM frames."""
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import COMM  # pyright: ignore[reportPrivateImportUsage]

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
    from mutagen import File  # pyright: ignore[reportPrivateImportUsage]
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3, ID3NoHeaderError  # pyright: ignore[reportPrivateImportUsage]
    from mutagen.id3._frames import (
        COMM,
        TALB,
        TCON,
        TDRC,
        TIT2,
        TPE1,
        TPE2,
    )

    # Résolution des classes Frame à partir du mapping de référence unique.
    # Évite la désynchronisation entre le nom de frame et la classe.
    _frame_classes: dict[str, type] = {
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
                        # Supprime toutes les frames COMM existantes quelle que soit
                        # leur langue/desc pour éviter les doublons (ex. COMM::fra).
                        for frame_key in [k for k in audio.tags if k.startswith("COMM")]:
                            del audio.tags[frame_key]
                        if value:
                            audio.tags["COMM::eng"] = COMM(
                                encoding=3, lang="eng", desc="", text=value
                            )
                    elif normalized_tag in _TAG_TO_ID3_FRAME_CLASS_NAME:
                        frame_id = _TAG_TO_ID3_FRAME_CLASS_NAME[normalized_tag]
                        frame_class = _frame_classes[frame_id]
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
