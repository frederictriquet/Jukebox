"""Tests for audio tag writing utilities."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jukebox.utils.tag_writer import save_audio_tags


# The tag_writer imports mutagen.File, mutagen.easyid3.EasyID3, and mutagen.id3.ID3NoHeaderError
# lazily inside the function body, so we patch them at their source locations.
_PATCH_FILE = "mutagen.File"
_PATCH_EASYID3 = "mutagen.easyid3.EasyID3"
_PATCH_ID3_NO_HEADER = "mutagen.id3.ID3NoHeaderError"


class TestSaveAudioTagsMP3:
    """Tests for save_audio_tags with MP3 files."""

    def test_mp3_easy_id3_saves_tags_returns_true(self, tmp_path: Path) -> None:
        """EasyID3 loads successfully, tags are set and saved, returns True."""
        mp3_path = tmp_path / "song.mp3"
        mp3_path.write_bytes(b"fake mp3")

        mock_audio = MagicMock()
        mock_audio.__contains__ = MagicMock(return_value=False)

        with patch(_PATCH_EASYID3, return_value=mock_audio):
            result = save_audio_tags(str(mp3_path), {"artist": "Test Artist", "title": "Test Title"})

        assert result is True
        mock_audio.__setitem__.assert_any_call("artist", ["Test Artist"])
        mock_audio.__setitem__.assert_any_call("title", ["Test Title"])
        mock_audio.save.assert_called_once()

    def test_mp3_id3_no_header_falls_back_to_file(self, tmp_path: Path) -> None:
        """ID3NoHeaderError causes fallback to File(easy=True) and add_tags()."""
        mp3_path = tmp_path / "no_header.mp3"
        mp3_path.write_bytes(b"fake mp3 no header")

        mock_audio = MagicMock()
        mock_audio.__contains__ = MagicMock(return_value=False)

        from mutagen.id3 import ID3NoHeaderError

        with (
            patch(_PATCH_EASYID3, side_effect=ID3NoHeaderError("no header")),
            patch(_PATCH_FILE, return_value=mock_audio) as mock_file,
        ):
            result = save_audio_tags(str(mp3_path), {"genre": "Jazz"})

        assert result is True
        mock_file.assert_called_once_with(str(mp3_path), easy=True)
        mock_audio.add_tags.assert_called_once()
        mock_audio.save.assert_called_once()

    def test_mp3_id3_no_header_file_returns_none_returns_false(self, tmp_path: Path) -> None:
        """When File(easy=True) returns None after ID3NoHeaderError, returns False."""
        mp3_path = tmp_path / "bad.mp3"
        mp3_path.write_bytes(b"fake")

        from mutagen.id3 import ID3NoHeaderError

        with (
            patch(_PATCH_EASYID3, side_effect=ID3NoHeaderError("no header")),
            patch(_PATCH_FILE, return_value=None),
        ):
            result = save_audio_tags(str(mp3_path), {"artist": "Nobody"})

        assert result is False

    def test_mp3_empty_tag_value_deletes_existing_tag(self, tmp_path: Path) -> None:
        """Empty string value deletes the tag if it exists in the audio object."""
        mp3_path = tmp_path / "delete_tag.mp3"
        mp3_path.write_bytes(b"fake mp3")

        mock_audio = MagicMock()
        # Simulate 'artist' present in audio, 'title' absent
        mock_audio.__contains__ = MagicMock(side_effect=lambda k: k == "artist")

        with patch(_PATCH_EASYID3, return_value=mock_audio):
            result = save_audio_tags(str(mp3_path), {"artist": "", "title": ""})

        assert result is True
        # artist should be deleted (it was present, value is empty)
        mock_audio.__delitem__.assert_called_once_with("artist")
        # setitem should not be called for either empty-value tag
        set_calls = [c.args[0] for c in mock_audio.__setitem__.call_args_list]
        assert "artist" not in set_calls
        assert "title" not in set_calls

    def test_mp3_exception_during_save_returns_false(self, tmp_path: Path) -> None:
        """Exception raised during save() returns False."""
        mp3_path = tmp_path / "fail.mp3"
        mp3_path.write_bytes(b"fake mp3")

        mock_audio = MagicMock()
        mock_audio.__contains__ = MagicMock(return_value=False)
        mock_audio.save.side_effect = OSError("disk full")

        with patch(_PATCH_EASYID3, return_value=mock_audio):
            result = save_audio_tags(str(mp3_path), {"artist": "Someone"})

        assert result is False


class TestSaveAudioTagsNonMP3:
    """Tests for save_audio_tags with non-MP3 files (FLAC, WAV, etc.)."""

    def test_flac_saves_tags_returns_true(self, tmp_path: Path) -> None:
        """File() loads a FLAC successfully, tags are set and saved, returns True."""
        flac_path = tmp_path / "track.flac"
        flac_path.write_bytes(b"fake flac")

        mock_audio = MagicMock()
        mock_audio.__contains__ = MagicMock(return_value=False)

        with patch(_PATCH_FILE, return_value=mock_audio) as mock_file:
            result = save_audio_tags(str(flac_path), {"artist": "Band", "genre": "Rock"})

        assert result is True
        mock_file.assert_called_once_with(str(flac_path))
        mock_audio.__setitem__.assert_any_call("artist", ["Band"])
        mock_audio.__setitem__.assert_any_call("genre", ["Rock"])
        mock_audio.save.assert_called_once()

    def test_non_mp3_file_returns_none_returns_false(self, tmp_path: Path) -> None:
        """File() returning None for unsupported format returns False."""
        wav_path = tmp_path / "audio.wav"
        wav_path.write_bytes(b"fake wav")

        with patch(_PATCH_FILE, return_value=None):
            result = save_audio_tags(str(wav_path), {"artist": "X"})

        assert result is False

    def test_non_mp3_empty_tag_value_deletes_existing_tag(self, tmp_path: Path) -> None:
        """Empty string value deletes the tag if it exists (non-MP3)."""
        flac_path = tmp_path / "delete.flac"
        flac_path.write_bytes(b"fake flac")

        mock_audio = MagicMock()
        mock_audio.__contains__ = MagicMock(side_effect=lambda k: k == "artist")

        with patch(_PATCH_FILE, return_value=mock_audio):
            result = save_audio_tags(str(flac_path), {"artist": "", "title": ""})

        assert result is True
        mock_audio.__delitem__.assert_called_once_with("artist")
        set_calls = [c.args[0] for c in mock_audio.__setitem__.call_args_list]
        assert "artist" not in set_calls
        assert "title" not in set_calls

    def test_non_mp3_lowercase_tags_by_default(self, tmp_path: Path) -> None:
        """Tag names are lowercased for non-MP3 by default."""
        flac_path = tmp_path / "track.flac"
        flac_path.write_bytes(b"fake flac")

        mock_audio = MagicMock()
        mock_audio.__contains__ = MagicMock(return_value=False)

        with patch(_PATCH_FILE, return_value=mock_audio):
            result = save_audio_tags(str(flac_path), {"ARTIST": "Band", "GENRE": "Techno"})

        assert result is True
        mock_audio.__setitem__.assert_any_call("artist", ["Band"])
        mock_audio.__setitem__.assert_any_call("genre", ["Techno"])

    def test_non_mp3_lowercase_false_preserves_case(self, tmp_path: Path) -> None:
        """lowercase_tags_for_non_mp3=False preserves original tag name case."""
        flac_path = tmp_path / "track.flac"
        flac_path.write_bytes(b"fake flac")

        mock_audio = MagicMock()
        mock_audio.__contains__ = MagicMock(return_value=False)

        with patch(_PATCH_FILE, return_value=mock_audio):
            result = save_audio_tags(
                str(flac_path),
                {"ARTIST": "Band", "GENRE": "Techno"},
                lowercase_tags_for_non_mp3=False,
            )

        assert result is True
        mock_audio.__setitem__.assert_any_call("ARTIST", ["Band"])
        mock_audio.__setitem__.assert_any_call("GENRE", ["Techno"])
        # Lowercase versions should NOT have been set
        set_calls = [c.args[0] for c in mock_audio.__setitem__.call_args_list]
        assert "artist" not in set_calls
        assert "genre" not in set_calls

    def test_non_mp3_exception_during_save_returns_false(self, tmp_path: Path) -> None:
        """Exception during save() for a non-MP3 file returns False."""
        flac_path = tmp_path / "fail.flac"
        flac_path.write_bytes(b"fake flac")

        mock_audio = MagicMock()
        mock_audio.__contains__ = MagicMock(return_value=False)
        mock_audio.save.side_effect = RuntimeError("unexpected")

        with patch(_PATCH_FILE, return_value=mock_audio):
            result = save_audio_tags(str(flac_path), {"title": "Track"})

        assert result is False

    def test_accepts_path_object(self, tmp_path: Path) -> None:
        """save_audio_tags accepts a pathlib.Path (not just str)."""
        flac_path = tmp_path / "path_obj.flac"
        flac_path.write_bytes(b"fake flac")

        mock_audio = MagicMock()
        mock_audio.__contains__ = MagicMock(return_value=False)

        with patch(_PATCH_FILE, return_value=mock_audio):
            result = save_audio_tags(flac_path, {"title": "My Track"})

        assert result is True
