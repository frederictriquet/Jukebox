"""Tests for reading/writing the quick-export .jsonl store."""

from __future__ import annotations

import json
from pathlib import Path

from plugins.video_exporter.quick_export_store import (
    QuickExportEntry,
    read_entries,
    write_entries,
)

_ENTRY = QuickExportEntry(
    track_id=1,
    filepath="/music/track.mp3",
    loop_start=10.0,
    loop_end=40.0,
    exported_at="2026-07-10T12:00:00+00:00",
)


def test_read_entries_missing_file_returns_empty_list(tmp_path: Path) -> None:
    """A .jsonl that doesn't exist yet reads as an empty list, not an error."""
    assert read_entries(tmp_path / "missing.jsonl") == []


def test_write_then_read_round_trips(tmp_path: Path) -> None:
    """Entries written are read back identically."""
    jsonl_path = tmp_path / "quick_exports.jsonl"

    write_entries(jsonl_path, [_ENTRY])

    assert read_entries(jsonl_path) == [_ENTRY]


def test_read_entries_defaults_missing_fields_for_backward_compat(tmp_path: Path) -> None:
    """Lines written by the original QuickExportWorker (no rendered_at/output_path) still load."""
    jsonl_path = tmp_path / "quick_exports.jsonl"
    old_style_record = {
        "track_id": 1,
        "filepath": "/music/track.mp3",
        "loop_start": 10.0,
        "loop_end": 40.0,
        "exported_at": "2026-07-10T12:00:00+00:00",
    }
    jsonl_path.write_text(json.dumps(old_style_record) + "\n", encoding="utf-8")

    entries = read_entries(jsonl_path)

    assert entries == [_ENTRY]
    assert entries[0].rendered_at is None
    assert entries[0].output_path is None


def test_read_entries_skips_malformed_lines(tmp_path: Path) -> None:
    """A corrupt line is logged and skipped; valid lines around it still load."""
    jsonl_path = tmp_path / "quick_exports.jsonl"
    jsonl_path.write_text(
        json.dumps(_ENTRY.to_dict())
        + "\n"
        + "not valid json\n"
        + json.dumps({"track_id": 2, "filepath": "x"})  # missing required fields
        + "\n",
        encoding="utf-8",
    )

    entries = read_entries(jsonl_path)

    assert entries == [_ENTRY]


def test_read_entries_skips_blank_lines(tmp_path: Path) -> None:
    """Blank lines (trailing newline, stray whitespace) are ignored, not treated as malformed."""
    jsonl_path = tmp_path / "quick_exports.jsonl"
    jsonl_path.write_text(json.dumps(_ENTRY.to_dict()) + "\n\n   \n", encoding="utf-8")

    assert read_entries(jsonl_path) == [_ENTRY]


def test_write_entries_creates_parent_directories(tmp_path: Path) -> None:
    """Missing parent directories are created before writing."""
    jsonl_path = tmp_path / "nested" / "dir" / "quick_exports.jsonl"

    write_entries(jsonl_path, [_ENTRY])

    assert jsonl_path.exists()


def test_write_entries_empty_list_clears_the_file(tmp_path: Path) -> None:
    """Writing an empty list (e.g. after deleting the last entry) empties the file."""
    jsonl_path = tmp_path / "quick_exports.jsonl"
    write_entries(jsonl_path, [_ENTRY])

    write_entries(jsonl_path, [])

    assert read_entries(jsonl_path) == []
    assert jsonl_path.exists()


def test_write_entries_overwrites_rather_than_appends(tmp_path: Path) -> None:
    """A second write_entries call replaces the file content, it doesn't append."""
    jsonl_path = tmp_path / "quick_exports.jsonl"
    write_entries(jsonl_path, [_ENTRY])

    other = QuickExportEntry(
        track_id=2,
        filepath="/music/other.mp3",
        loop_start=0.0,
        loop_end=30.0,
        exported_at="2026-07-10T13:00:00+00:00",
    )
    write_entries(jsonl_path, [other])

    assert read_entries(jsonl_path) == [other]


def test_write_entries_persists_rendered_state(tmp_path: Path) -> None:
    """rendered_at/output_path set on an entry survive a write/read round trip."""
    jsonl_path = tmp_path / "quick_exports.jsonl"
    rendered = QuickExportEntry(
        track_id=1,
        filepath="/music/track.mp3",
        loop_start=10.0,
        loop_end=40.0,
        exported_at="2026-07-10T12:00:00+00:00",
        rendered_at="2026-07-10T12:05:00+00:00",
        output_path="/videos/Artist - Title.mp4",
    )

    write_entries(jsonl_path, [rendered])

    assert read_entries(jsonl_path) == [rendered]
