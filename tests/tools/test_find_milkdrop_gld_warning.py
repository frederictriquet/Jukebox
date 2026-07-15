"""Tests for the pure logic of the GLD texture warning diagnostic tool.

Subprocess-driving functions (probe_preset_in_subprocess, main) aren't tested
here: they require the real libprojectM/moderngl stack and are exercised
manually via `uv run python -m jukebox.tools.find_milkdrop_gld_warning`.
"""

from __future__ import annotations

from pathlib import Path

from jukebox.tools.find_milkdrop_gld_warning import ProbeResult, collect_presets


def test_collect_presets_finds_milk_files_recursively(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.milk").write_text("")
    (tmp_path / "sub" / "b.milk").write_text("")
    (tmp_path / "not_a_preset.txt").write_text("")

    result = collect_presets(tmp_path, limit=None, seed=0)

    assert {p.name for p in result} == {"a.milk", "b.milk"}


def test_collect_presets_respects_limit(tmp_path: Path) -> None:
    for i in range(10):
        (tmp_path / f"{i}.milk").write_text("")

    result = collect_presets(tmp_path, limit=3, seed=0)

    assert len(result) == 3


def test_collect_presets_is_deterministic_for_a_given_seed(tmp_path: Path) -> None:
    for i in range(10):
        (tmp_path / f"{i}.milk").write_text("")

    first = collect_presets(tmp_path, limit=None, seed=7)
    second = collect_presets(tmp_path, limit=None, seed=7)

    assert first == second


def test_collect_presets_order_varies_with_seed(tmp_path: Path) -> None:
    for i in range(10):
        (tmp_path / f"{i}.milk").write_text("")

    a = collect_presets(tmp_path, limit=None, seed=1)
    b = collect_presets(tmp_path, limit=None, seed=2)

    assert a != b


def test_probe_result_labels_ok() -> None:
    result = ProbeResult(triggered=False, crashed=False, errored=False, output="")
    assert result.labels == []


def test_probe_result_labels_warning_only() -> None:
    result = ProbeResult(triggered=True, crashed=False, errored=False, output="")
    assert result.labels == ["WARNING"]


def test_probe_result_labels_crashed_only() -> None:
    result = ProbeResult(triggered=False, crashed=True, errored=False, output="")
    assert result.labels == ["CRASHED"]


def test_probe_result_labels_errored_only() -> None:
    result = ProbeResult(triggered=False, crashed=False, errored=True, output="")
    assert result.labels == ["ERRORED"]


def test_probe_result_labels_all() -> None:
    result = ProbeResult(triggered=True, crashed=True, errored=True, output="")
    assert result.labels == ["WARNING", "CRASHED", "ERRORED"]
