"""Tests for the headless quick-export render TUI."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from jukebox.core.config import VideoExporterConfig
from jukebox.tools.quick_export_render_tui import (
    build_context,
    default_jsonl_path,
    delete_selected,
    render_entry,
    render_selected,
    run_tui,
)
from plugins.video_exporter.quick_export_store import QuickExportEntry

_ENTRY = QuickExportEntry(
    track_id=1,
    filepath="/music/track.mp3",
    loop_start=10.0,
    loop_end=40.0,
    exported_at="2026-07-10T12:00:00+00:00",
)


def _make_context(video_exporter_overrides: dict | None = None) -> Mock:
    context = Mock()
    overrides = {"output_directory": "/videos", **(video_exporter_overrides or {})}
    context.config.video_exporter = VideoExporterConfig(**overrides)
    return context


# ---------------------------------------------------------------------------
# default_jsonl_path
# ---------------------------------------------------------------------------


def test_default_jsonl_path_uses_configured_output_directory() -> None:
    context = _make_context()

    assert default_jsonl_path(context) == Path("/videos/quick_exports.jsonl")


# ---------------------------------------------------------------------------
# build_context (integration: real sqlite DB + real config)
# ---------------------------------------------------------------------------


def test_build_context_applies_db_override_over_yaml_default(tmp_path: Path) -> None:
    """A plugin_settings row overrides the YAML default, exactly like the GUI."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("video_exporter:\n  default_fps: 24\n", encoding="utf-8")
    db_path = tmp_path / "jukebox.db"

    context = build_context(db_path, config_path)
    assert context.config.video_exporter.default_fps == 24  # YAML default, no override yet
    context.database.close()

    # Simulate a DB override written by conf_manager (or by hand).
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO plugin_settings (plugin_name, setting_key, setting_value) VALUES (?, ?, ?)",
        ("video_exporter", "default_fps", "60"),
    )
    conn.commit()
    conn.close()

    context = build_context(db_path, config_path)

    assert context.config.video_exporter.default_fps == 60
    context.database.close()


# ---------------------------------------------------------------------------
# render_entry
# ---------------------------------------------------------------------------


def test_render_entry_track_not_found_skips_without_building_worker() -> None:
    context = _make_context()
    context.database.tracks.get_by_id.return_value = None
    context.database.tracks.get_by_filepath.return_value = None

    with patch("jukebox.tools.quick_export_render_tui.VideoExportWorker") as mock_worker_cls:
        result = render_entry(context, _ENTRY)

    assert result is None
    mock_worker_cls.assert_not_called()


def test_render_entry_mkdir_failure_skips_without_building_worker(tmp_path: Path) -> None:
    context = _make_context()
    context.database.tracks.get_by_id.return_value = {"id": 1, "artist": "A", "title": "T"}
    # A file where a directory needs to be created forces mkdir() to raise OSError.
    blocking_file = tmp_path / "not_a_dir"
    blocking_file.write_text("occupied")
    context.config.video_exporter.output_directory = str(blocking_file)

    with patch("jukebox.tools.quick_export_render_tui.VideoExportWorker") as mock_worker_cls:
        result = render_entry(context, _ENTRY)

    assert result is None
    mock_worker_cls.assert_not_called()


def test_render_entry_success_writes_description_and_returns_path(tmp_path: Path) -> None:
    context = _make_context({"output_directory": str(tmp_path)})
    track = {"id": 1, "artist": "Artist", "title": "Title", "genre": ""}
    context.database.tracks.get_by_id.return_value = track

    fake_worker = MagicMock()

    def _connect_finished(callback: Callable[[str], None]) -> None:
        callback(str(tmp_path / "out.mp4"))

    fake_worker.finished.connect.side_effect = _connect_finished
    fake_worker.error.connect.side_effect = lambda callback: None

    with (
        patch("jukebox.tools.quick_export_render_tui.VideoExportWorker", return_value=fake_worker),
        patch("jukebox.tools.quick_export_render_tui.write_video_description") as mock_write_desc,
    ):
        result = render_entry(context, _ENTRY)

    assert result == str(tmp_path / "out.mp4")
    fake_worker.run.assert_called_once()
    mock_write_desc.assert_called_once_with(
        str(tmp_path / "out.mp4"), track, context.config.genre_editor.codes
    )


def test_render_entry_error_signal_skips_description_and_returns_none(tmp_path: Path) -> None:
    context = _make_context({"output_directory": str(tmp_path)})
    track = {"id": 1, "artist": "Artist", "title": "Title"}
    context.database.tracks.get_by_id.return_value = track

    fake_worker = MagicMock()
    fake_worker.finished.connect.side_effect = lambda callback: None
    fake_worker.error.connect.side_effect = lambda callback: callback("boom")

    with (
        patch("jukebox.tools.quick_export_render_tui.VideoExportWorker", return_value=fake_worker),
        patch("jukebox.tools.quick_export_render_tui.write_video_description") as mock_write_desc,
    ):
        result = render_entry(context, _ENTRY)

    assert result is None
    mock_write_desc.assert_not_called()


# ---------------------------------------------------------------------------
# render_selected / delete_selected
# ---------------------------------------------------------------------------


def test_render_selected_persists_only_successful_renders(tmp_path: Path) -> None:
    context = _make_context()
    jsonl_path = tmp_path / "quick_exports.jsonl"
    entries = [
        QuickExportEntry(1, "/a.mp3", 0.0, 10.0, "2026-07-10T00:00:00+00:00"),
        QuickExportEntry(2, "/b.mp3", 0.0, 10.0, "2026-07-10T00:00:00+00:00"),
    ]

    with (
        patch(
            "jukebox.tools.quick_export_render_tui.render_entry",
            side_effect=["/videos/a.mp4", None],
        ),
        patch("jukebox.tools.quick_export_render_tui.write_entries") as mock_write,
    ):
        render_selected(context, jsonl_path, entries, [0, 1])

    assert entries[0].rendered_at is not None
    assert entries[0].output_path == "/videos/a.mp4"
    assert entries[1].rendered_at is None
    mock_write.assert_called_once_with(jsonl_path, entries)


def test_delete_selected_keeps_unselected_entries_and_persists(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "quick_exports.jsonl"
    entries = [
        QuickExportEntry(1, "/a.mp3", 0.0, 10.0, "2026-07-10T00:00:00+00:00"),
        QuickExportEntry(2, "/b.mp3", 0.0, 10.0, "2026-07-10T00:00:00+00:00"),
        QuickExportEntry(3, "/c.mp3", 0.0, 10.0, "2026-07-10T00:00:00+00:00"),
    ]

    with patch("jukebox.tools.quick_export_render_tui.write_entries") as mock_write:
        remaining = delete_selected(jsonl_path, entries, [0, 2])

    assert [e.track_id for e in remaining] == [2]
    mock_write.assert_called_once_with(jsonl_path, remaining)


# ---------------------------------------------------------------------------
# run_tui control flow
# ---------------------------------------------------------------------------


def _mock_ask(*return_values: object) -> MagicMock:
    """Build a questionary-prompt-like mock whose .ask() yields return_values in order."""
    prompt = MagicMock()
    prompt.ask.side_effect = list(return_values)
    return prompt


def test_run_tui_no_entries_prints_and_returns_without_prompting() -> None:
    context = _make_context()

    with (
        patch("jukebox.tools.quick_export_render_tui.read_entries", return_value=[]),
        patch("jukebox.tools.quick_export_render_tui.questionary.checkbox") as mock_checkbox,
    ):
        run_tui(context, Path("/videos/quick_exports.jsonl"))

    mock_checkbox.assert_not_called()


def test_run_tui_preselects_unrendered_entries_only() -> None:
    """Pending entries are pre-checked; already-rendered ones are not."""
    context = _make_context()
    pending = QuickExportEntry(1, "/a.mp3", 0.0, 10.0, "2026-07-10T00:00:00+00:00")
    rendered = QuickExportEntry(
        2,
        "/b.mp3",
        0.0,
        10.0,
        "2026-07-10T00:00:00+00:00",
        rendered_at="2026-07-10T01:00:00+00:00",
        output_path="/videos/b.mp4",
    )

    with (
        patch(
            "jukebox.tools.quick_export_render_tui.read_entries",
            return_value=[pending, rendered],
        ),
        patch(
            "jukebox.tools.quick_export_render_tui.questionary.checkbox",
            return_value=_mock_ask(None),
        ) as mock_checkbox,
    ):
        run_tui(context, Path("/videos/quick_exports.jsonl"))

    choices = mock_checkbox.call_args.kwargs["choices"]
    assert [c.checked for c in choices] == [True, False]


def test_run_tui_ctrl_c_on_checkbox_returns_immediately() -> None:
    context = _make_context()

    with (
        patch("jukebox.tools.quick_export_render_tui.read_entries", return_value=[_ENTRY]),
        patch(
            "jukebox.tools.quick_export_render_tui.questionary.checkbox",
            return_value=_mock_ask(None),
        ),
    ):
        run_tui(context, Path("/videos/quick_exports.jsonl"))  # must not raise/hang


def test_run_tui_empty_selection_confirms_quit() -> None:
    context = _make_context()

    with (
        patch("jukebox.tools.quick_export_render_tui.read_entries", return_value=[_ENTRY]),
        patch(
            "jukebox.tools.quick_export_render_tui.questionary.checkbox",
            return_value=_mock_ask([]),
        ),
        patch(
            "jukebox.tools.quick_export_render_tui.questionary.confirm",
            return_value=_mock_ask(True),
        ) as mock_confirm,
    ):
        run_tui(context, Path("/videos/quick_exports.jsonl"))

    mock_confirm.assert_called_once()


def test_run_tui_empty_selection_declining_quit_loops_then_ctrl_c() -> None:
    context = _make_context()

    with (
        patch("jukebox.tools.quick_export_render_tui.read_entries", return_value=[_ENTRY]),
        patch(
            "jukebox.tools.quick_export_render_tui.questionary.checkbox",
            return_value=_mock_ask([], None),
        ) as mock_checkbox,
        patch(
            "jukebox.tools.quick_export_render_tui.questionary.confirm",
            return_value=_mock_ask(False),
        ),
    ):
        run_tui(context, Path("/videos/quick_exports.jsonl"))

    assert mock_checkbox.call_count == 2


def test_run_tui_render_action_calls_render_selected() -> None:
    context = _make_context()

    with (
        patch(
            "jukebox.tools.quick_export_render_tui.read_entries",
            side_effect=[[_ENTRY], []],
        ),
        patch(
            "jukebox.tools.quick_export_render_tui.questionary.checkbox",
            return_value=_mock_ask([0]),
        ),
        patch(
            "jukebox.tools.quick_export_render_tui.questionary.select",
            return_value=_mock_ask("Générer la vidéo"),
        ),
        patch("jukebox.tools.quick_export_render_tui.render_selected") as mock_render,
    ):
        run_tui(context, Path("/videos/quick_exports.jsonl"))

    mock_render.assert_called_once_with(context, Path("/videos/quick_exports.jsonl"), [_ENTRY], [0])


def test_run_tui_delete_action_calls_delete_selected() -> None:
    context = _make_context()

    with (
        patch(
            "jukebox.tools.quick_export_render_tui.read_entries",
            side_effect=[[_ENTRY], []],
        ),
        patch(
            "jukebox.tools.quick_export_render_tui.questionary.checkbox",
            return_value=_mock_ask([0]),
        ),
        patch(
            "jukebox.tools.quick_export_render_tui.questionary.select",
            return_value=_mock_ask("Supprimer de la liste"),
        ),
        patch("jukebox.tools.quick_export_render_tui.delete_selected") as mock_delete,
    ):
        run_tui(context, Path("/videos/quick_exports.jsonl"))

    mock_delete.assert_called_once_with(Path("/videos/quick_exports.jsonl"), [_ENTRY], [0])


def test_run_tui_cancel_action_does_nothing_then_ctrl_c() -> None:
    context = _make_context()

    with (
        patch(
            "jukebox.tools.quick_export_render_tui.read_entries",
            return_value=[_ENTRY],
        ),
        patch(
            "jukebox.tools.quick_export_render_tui.questionary.checkbox",
            return_value=_mock_ask([0], None),
        ),
        patch(
            "jukebox.tools.quick_export_render_tui.questionary.select",
            return_value=_mock_ask("Annuler"),
        ),
        patch("jukebox.tools.quick_export_render_tui.render_selected") as mock_render,
        patch("jukebox.tools.quick_export_render_tui.delete_selected") as mock_delete,
    ):
        run_tui(context, Path("/videos/quick_exports.jsonl"))

    mock_render.assert_not_called()
    mock_delete.assert_not_called()
