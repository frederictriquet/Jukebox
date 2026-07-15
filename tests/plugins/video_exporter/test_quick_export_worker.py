"""Tests for QuickExportWorker: upserts loop info into a .jsonl file, off the UI thread."""

from __future__ import annotations

from pathlib import Path

from plugins.video_exporter.quick_export_store import QuickExportEntry, read_entries, write_entries
from plugins.video_exporter.quick_export_worker import QuickExportWorker

_ENTRY = QuickExportEntry(
    track_id=42,
    filepath="/music/track.mp3",
    loop_start=10.0,
    loop_end=40.0,
    exported_at="2026-07-10T12:00:00+00:00",
)


def test_worker_has_named_object_name(tmp_path: Path, qapp: object) -> None:
    """The QThread is named so it never shows up as '' in Qt teardown warnings."""
    worker = QuickExportWorker(tmp_path / "quick_exports.jsonl", _ENTRY)

    assert worker.objectName() == "VideoExporter-QuickExportWorker-42"


def test_run_appends_new_entry(tmp_path: Path, qapp: object) -> None:
    """A track_id not already present is appended as a new line."""
    jsonl_path = tmp_path / "quick_exports.jsonl"
    worker = QuickExportWorker(jsonl_path, _ENTRY)
    finished_calls: list[None] = []
    worker.finished.connect(lambda: finished_calls.append(None))

    worker.run()

    assert finished_calls == [None]
    assert read_entries(jsonl_path) == [_ENTRY]


def test_run_creates_parent_directories(tmp_path: Path, qapp: object) -> None:
    """Missing parent directories are created before writing."""
    jsonl_path = tmp_path / "nested" / "dir" / "quick_exports.jsonl"
    worker = QuickExportWorker(jsonl_path, _ENTRY)

    worker.run()

    assert jsonl_path.exists()


def test_run_appends_distinct_track_ids_as_separate_lines(tmp_path: Path, qapp: object) -> None:
    """Different track_ids each get their own line, in insertion order."""
    jsonl_path = tmp_path / "quick_exports.jsonl"
    other = QuickExportEntry(
        track_id=99, filepath="/music/other.mp3", loop_start=0.0, loop_end=20.0, exported_at="x"
    )

    QuickExportWorker(jsonl_path, _ENTRY).run()
    QuickExportWorker(jsonl_path, other).run()

    assert [e.track_id for e in read_entries(jsonl_path)] == [42, 99]


def test_run_replaces_existing_entry_with_same_track_id(tmp_path: Path, qapp: object) -> None:
    """Re-clicking Quick Export for the same track updates its entry instead of duplicating it."""
    jsonl_path = tmp_path / "quick_exports.jsonl"
    stale = QuickExportEntry(
        track_id=42,
        filepath="/music/track.mp3",
        loop_start=0.0,
        loop_end=15.0,
        exported_at="2026-07-01T00:00:00+00:00",
        rendered_at="2026-07-01T00:05:00+00:00",
        output_path="/videos/old.mp4",
    )
    write_entries(jsonl_path, [stale])

    updated = QuickExportEntry(
        track_id=42,
        filepath="/music/track.mp3",
        loop_start=10.0,
        loop_end=40.0,
        exported_at="2026-07-10T12:00:00+00:00",
    )
    QuickExportWorker(jsonl_path, updated).run()

    entries = read_entries(jsonl_path)
    assert entries == [updated]
    # The stale render no longer matches the new loop bounds: cleared, not carried over.
    assert entries[0].rendered_at is None
    assert entries[0].output_path is None


def test_run_preserves_other_entries_when_updating_one(tmp_path: Path, qapp: object) -> None:
    """Updating one track's entry leaves unrelated entries untouched, in place."""
    jsonl_path = tmp_path / "quick_exports.jsonl"
    other = QuickExportEntry(
        track_id=99, filepath="/music/other.mp3", loop_start=0.0, loop_end=20.0, exported_at="x"
    )
    write_entries(jsonl_path, [other, _ENTRY])

    updated = QuickExportEntry(
        track_id=42, filepath="/music/track.mp3", loop_start=5.0, loop_end=25.0, exported_at="y"
    )
    QuickExportWorker(jsonl_path, updated).run()

    assert read_entries(jsonl_path) == [other, updated]


def test_run_emits_error_on_oserror(tmp_path: Path, qapp: object) -> None:
    """An OSError while writing is reported via the error signal, not raised."""
    # A regular file cannot also be used as a parent directory: mkdir(parents=True) raises.
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("occupied")
    jsonl_path = blocking_file / "quick_exports.jsonl"

    worker = QuickExportWorker(jsonl_path, _ENTRY)
    errors: list[str] = []
    finished_calls: list[None] = []
    worker.error.connect(errors.append)
    worker.finished.connect(lambda: finished_calls.append(None))

    worker.run()

    assert len(errors) == 1
    assert finished_calls == []
