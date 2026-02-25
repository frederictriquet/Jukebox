"""Tests for track cell renderer stylers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from jukebox.ui.components.track_cell_renderer import (
    ArtistStyler,
    DuplicateStatusStyler,
    FilenameStyler,
    TitleStyler,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_track(**kwargs: Any) -> dict[str, Any]:
    """Return a minimal track dict with sensible defaults."""
    defaults: dict[str, Any] = {
        "filepath": Path("/music/artist - title.mp3"),
        "artist": "Test Artist",
        "title": "Test Title",
        "genre": "H-*3",
        "duration_seconds": 180,
        "file_missing": False,
        "duplicate_status": "green",
        "duplicate_match": None,
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# DuplicateStatusStyler
# ---------------------------------------------------------------------------


class TestDuplicateStatusStyler:
    """Tests for the duplicate column styler."""

    def test_display_always_returns_dot(self) -> None:
        styler = DuplicateStatusStyler()
        track = make_track()
        assert styler.display(None, track) == "●"

    def test_alignment_is_center(self, qapp: Any) -> None:
        styler = DuplicateStatusStyler()
        track = make_track()
        alignment = styler.alignment(None, track)
        assert alignment == Qt.AlignmentFlag.AlignCenter

    # --- Tooltip ---

    def test_tooltip_green(self) -> None:
        styler = DuplicateStatusStyler()
        track = make_track(duplicate_status="green")
        assert styler.tooltip(None, track) == "No duplicate detected"

    def test_tooltip_red_with_match(self) -> None:
        styler = DuplicateStatusStyler()
        track = make_track(duplicate_status="red", duplicate_match="Daft Punk - Get Lucky")
        assert styler.tooltip(None, track) == "Certain duplicate: Daft Punk - Get Lucky"

    def test_tooltip_red_without_match(self) -> None:
        styler = DuplicateStatusStyler()
        track = make_track(duplicate_status="red", duplicate_match=None)
        assert styler.tooltip(None, track) == "Certain duplicate in library"

    def test_tooltip_orange_with_match(self) -> None:
        styler = DuplicateStatusStyler()
        track = make_track(duplicate_status="orange", duplicate_match="Some Track")
        assert styler.tooltip(None, track) == "Possible duplicate: Some Track"

    def test_tooltip_orange_without_match(self) -> None:
        styler = DuplicateStatusStyler()
        track = make_track(duplicate_status="orange", duplicate_match=None)
        assert styler.tooltip(None, track) == "Possible duplicate in library"

    def test_tooltip_pending(self) -> None:
        styler = DuplicateStatusStyler()
        track = make_track(duplicate_status="pending")
        assert styler.tooltip(None, track) == "Checking for duplicates..."

    # --- Foreground color ---

    def test_foreground_green_is_green_color(self, qapp: Any) -> None:
        styler = DuplicateStatusStyler()
        track = make_track(duplicate_status="green")
        color = styler.foreground(None, track)
        assert isinstance(color, QColor)
        assert color == DuplicateStatusStyler._COLORS["green"]

    def test_foreground_orange_is_orange_color(self, qapp: Any) -> None:
        styler = DuplicateStatusStyler()
        track = make_track(duplicate_status="orange")
        color = styler.foreground(None, track)
        assert isinstance(color, QColor)
        assert color == DuplicateStatusStyler._COLORS["orange"]

    def test_foreground_red_is_red_color(self, qapp: Any) -> None:
        styler = DuplicateStatusStyler()
        track = make_track(duplicate_status="red")
        color = styler.foreground(None, track)
        assert isinstance(color, QColor)
        assert color == DuplicateStatusStyler._COLORS["red"]

    def test_foreground_pending_is_gray(self, qapp: Any) -> None:
        styler = DuplicateStatusStyler()
        track = make_track(duplicate_status="pending")
        color = styler.foreground(None, track)
        assert isinstance(color, QColor)
        assert color == DuplicateStatusStyler._COLORS["pending"]

    def test_foreground_unknown_status_defaults_to_green(self, qapp: Any) -> None:
        """An unrecognised status should fall back to green color without crashing."""
        styler = DuplicateStatusStyler()
        track = make_track(duplicate_status="unknown_value")
        color = styler.foreground(None, track)
        assert isinstance(color, QColor)
        assert color == DuplicateStatusStyler._COLORS["green"]

    def test_foreground_missing_status_defaults_to_green(self, qapp: Any) -> None:
        styler = DuplicateStatusStyler()
        track = make_track()
        del track["duplicate_status"]  # key absent from dict
        color = styler.foreground(None, track)
        assert color == DuplicateStatusStyler._COLORS["green"]


# ---------------------------------------------------------------------------
# FilenameStyler — file_missing behaviour
# ---------------------------------------------------------------------------


class TestFilenameStylerMissingFile:
    """Tests for red foreground / tooltip when a file is missing from disk."""

    def test_foreground_red_when_file_missing(self, qapp: Any) -> None:
        styler = FilenameStyler()
        track = make_track(file_missing=True)
        color = styler.foreground(None, track)
        assert isinstance(color, QColor)
        assert color == QColor(Qt.GlobalColor.red)

    def test_foreground_none_when_file_present(self) -> None:
        styler = FilenameStyler()
        track = make_track(file_missing=False)
        assert styler.foreground(None, track) is None

    def test_tooltip_shows_missing_file_message(self) -> None:
        styler = FilenameStyler()
        fp = Path("/music/lost_track.mp3")
        track = make_track(filepath=fp, file_missing=True)
        tooltip = styler.tooltip(None, track)
        assert "missing" in tooltip.lower()
        assert str(fp) in tooltip

    def test_tooltip_filename_in_jukebox_mode(self) -> None:
        from jukebox.core.mode_manager import AppMode

        styler = FilenameStyler(mode=AppMode.JUKEBOX.value)
        track = make_track(file_missing=False)
        tooltip = styler.tooltip(None, track)
        assert "artist - title.mp3" in tooltip.lower()

    def test_tooltip_full_path_in_curating_mode(self) -> None:
        styler = FilenameStyler(mode="curating")
        fp = Path("/music/artist - title.mp3")
        track = make_track(filepath=fp, file_missing=False)
        tooltip = styler.tooltip(None, track)
        assert str(fp) in tooltip


# ---------------------------------------------------------------------------
# ArtistStyler — file_missing colour
# ---------------------------------------------------------------------------


class TestArtistStylerMissingFile:
    """Tests for red foreground on ArtistStyler when file is missing."""

    def test_foreground_red_when_file_missing(self, qapp: Any) -> None:
        styler = ArtistStyler()
        track = make_track(file_missing=True)
        color = styler.foreground(None, track)
        assert isinstance(color, QColor)
        assert color == QColor(Qt.GlobalColor.red)

    def test_foreground_none_when_file_present(self) -> None:
        styler = ArtistStyler()
        track = make_track(file_missing=False)
        assert styler.foreground(None, track) is None


# ---------------------------------------------------------------------------
# TitleStyler — file_missing colour
# ---------------------------------------------------------------------------


class TestTitleStylerMissingFile:
    """Tests for red foreground on TitleStyler when file is missing."""

    def test_foreground_red_when_file_missing(self, qapp: Any) -> None:
        styler = TitleStyler()
        track = make_track(file_missing=True)
        color = styler.foreground(None, track)
        assert isinstance(color, QColor)
        assert color == QColor(Qt.GlobalColor.red)

    def test_foreground_none_when_file_present(self) -> None:
        styler = TitleStyler()
        track = make_track(file_missing=False)
        assert styler.foreground(None, track) is None
