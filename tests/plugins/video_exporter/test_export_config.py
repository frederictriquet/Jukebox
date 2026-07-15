"""Tests for the shared export config/description helpers (export_config.py).

These helpers back both ExportDialog (GUI) and the headless quick-export
renderer, so their defaults must exactly match what VideoExporterConfig holds.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jukebox.core.config import GenreCodeConfig, VideoExporterConfig
from plugins.video_exporter.export_config import (
    RESOLUTION_PRESETS,
    build_default_export_config,
    compute_deterministic_seed,
    default_output_filename,
    write_video_description,
)


def test_compute_deterministic_seed_is_stable() -> None:
    """The same title/genre always yields the same seed."""
    metadata = {"title": "Song", "genre": "D-W"}

    assert compute_deterministic_seed(metadata) == compute_deterministic_seed(metadata)


def test_compute_deterministic_seed_varies_with_metadata() -> None:
    """Different title/genre yields a different seed."""
    seed_a = compute_deterministic_seed({"title": "Song A", "genre": "D-W"})
    seed_b = compute_deterministic_seed({"title": "Song B", "genre": "D-W"})

    assert seed_a != seed_b


def test_default_output_filename_sanitizes_special_characters() -> None:
    """Characters unsafe for filenames are replaced with underscores."""
    filename = default_output_filename({"artist": "AC/DC", "title": "T:N:T"})

    assert filename == "AC_DC - T_N_T.mp4"


def test_default_output_filename_falls_back_to_unknown() -> None:
    """Missing artist/title falls back to 'Unknown', matching the dialog's behavior."""
    assert default_output_filename({}) == "Unknown - Unknown.mp4"


def test_build_default_export_config_uses_config_values() -> None:
    """Every config-backed field comes from VideoExporterConfig, not a hardcoded value."""
    config = VideoExporterConfig(
        default_resolution="720p",
        default_fps=24,
        output_directory="/videos",
        ffmpeg_crf=18,
    )

    result = build_default_export_config(
        filepath=Path("/music/track.mp3"),
        loop_start=10.0,
        loop_end=40.0,
        track_metadata={"artist": "Artist", "title": "Title"},
        config=config,
    )

    assert (result["width"], result["height"]) == RESOLUTION_PRESETS["720p"]
    assert result["fps"] == 24
    assert result["ffmpeg_crf"] == 18
    assert result["output_path"] == Path("/videos") / "Artist - Title.mp4"
    assert result["layers"]["waveform"] == config.waveform_enabled
    assert result["rng_seed"] == compute_deterministic_seed({"artist": "Artist", "title": "Title"})


def test_build_default_export_config_respects_output_path_override() -> None:
    """An explicit output_path is used verbatim instead of the generated one."""
    config = VideoExporterConfig()
    override = Path("/custom/out.mp4")

    result = build_default_export_config(
        filepath=Path("/music/track.mp3"),
        loop_start=0.0,
        loop_end=30.0,
        track_metadata={},
        config=config,
        output_path=override,
    )

    assert result["output_path"] == override


def test_write_video_description_writes_artist_and_title(tmp_path: Path) -> None:
    """Both artist and title present -> single 'Artist - Title' line."""
    video_path = tmp_path / "clip.mp4"

    write_video_description(video_path, {"artist": "Artist", "title": "Title"}, [])

    assert video_path.with_suffix(".txt").read_text(encoding="utf-8") == "Artist - Title"


def test_write_video_description_writes_only_title_when_artist_missing(tmp_path: Path) -> None:
    """Only one of artist/title present -> that value alone, no dangling separator."""
    video_path = tmp_path / "clip.mp4"

    write_video_description(video_path, {"title": "Title"}, [])

    assert video_path.with_suffix(".txt").read_text(encoding="utf-8") == "Title"


def test_write_video_description_skips_file_when_nothing_to_write(tmp_path: Path) -> None:
    """No artist/title/genre -> no .txt file created at all."""
    video_path = tmp_path / "clip.mp4"

    write_video_description(video_path, {}, [])

    assert not video_path.with_suffix(".txt").exists()


def test_write_video_description_includes_matching_genre_hashtags(tmp_path: Path) -> None:
    """Genre codes are mapped to hashtags, starred/unknown codes are ignored."""
    video_path = tmp_path / "clip.mp4"
    codes = [
        GenreCodeConfig(key="D", code="D", name="Deep", hashtags=["deephouse", "#house"]),
        GenreCodeConfig(key="C", code="C", name="Classic", hashtags=[]),
    ]

    write_video_description(video_path, {"genre": "D-C-*W"}, codes)

    lines = video_path.with_suffix(".txt").read_text(encoding="utf-8").splitlines()
    assert lines[-1] == "#deephouse #house"


def test_write_video_description_handles_write_failure(tmp_path: Path) -> None:
    """An OSError while writing the sidecar file is swallowed, not raised."""
    # A directory sharing the .txt sidecar's name makes write_text() raise OSError.
    video_path = tmp_path / "clip.mp4"
    (tmp_path / "clip.txt").mkdir()

    write_video_description(video_path, {"artist": "Artist", "title": "Title"}, [])  # no raise


@pytest.mark.parametrize("preset", list(RESOLUTION_PRESETS))
def test_all_resolution_presets_are_valid_dimensions(preset: str) -> None:
    """Every advertised resolution preset resolves to a positive (width, height)."""
    width, height = RESOLUTION_PRESETS[preset]

    assert width > 0
    assert height > 0
