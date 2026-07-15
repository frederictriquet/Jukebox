"""Shared helpers for building video export configs and sidecar files.

Extracted so the GUI export dialog (export_dialog.py) and the headless
quick-export renderer (jukebox/tools/quick_export_render_tui.py) derive
export settings from the exact same source: the VideoExporterConfig object.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jukebox.core.config import GenreCodeConfig
    from jukebox.core.protocols import VideoExporterConfigProtocol

# Resolution presets: name -> (width, height)
RESOLUTION_PRESETS: dict[str, tuple[int, int]] = {
    "1080p": (1920, 1080),
    "720p": (1280, 720),
    "square_1080": (1080, 1080),
    "square_720": (720, 720),
    "reels_9x16 (1080×1920)": (1080, 1920),  # Reels / Stories — boostable
    "feed_4x5 (1080×1350)": (1080, 1350),  # Feed portrait standard
    "feed_3x4 (1080×1440)": (1080, 1440),  # Wide feed portrait
}


def compute_deterministic_seed(track_metadata: dict[str, Any]) -> int:
    """Derive a stable RNG seed from title+genre so VJing effects are reproducible.

    SHA-256 instead of hash(): hash() is randomized by PYTHONHASHSEED, which
    would break reproducibility from one session/process to the next.
    """
    seed_str = f"{track_metadata.get('title', '')}:{track_metadata.get('genre', '')}"
    return int.from_bytes(hashlib.sha256(seed_str.encode()).digest()[:4], "big")


def default_output_filename(track_metadata: dict[str, Any]) -> str:
    """Build a safe 'Artist - Title.mp4' filename from track metadata."""
    artist = str(track_metadata.get("artist") or "Unknown")
    title = str(track_metadata.get("title") or "Unknown")
    safe_artist = "".join(c if c.isalnum() or c in " -_" else "_" for c in artist)
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    return f"{safe_artist} - {safe_title}.mp4"


def build_default_export_config(
    filepath: Path,
    loop_start: float,
    loop_end: float,
    track_metadata: dict[str, Any],
    config: VideoExporterConfigProtocol,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Build a VideoExportWorker config dict entirely from VideoExporterConfig defaults.

    Mirrors ExportDialog._get_export_config(), replacing every UI-widget value
    with its equivalent default: the persisted config field where one exists,
    or the same hardcoded default the dialog's widgets start at otherwise.
    """
    width, height = RESOLUTION_PRESETS[config.default_resolution]
    resolved_output_path = output_path or (
        Path(config.output_directory) / default_output_filename(track_metadata)
    )

    return {
        "filepath": filepath,
        "loop_start": loop_start,
        "loop_end": loop_end,
        "width": width,
        "height": height,
        "fps": config.default_fps,
        "output_path": resolved_output_path,
        "track_metadata": track_metadata,
        "layers": {
            "waveform": config.waveform_enabled,
            "text": config.text_enabled,
            "dynamics": config.dynamics_enabled,
            "vjing": config.vjing_enabled,
            "video_background": config.video_background_enabled,
            "milkdrop_enabled": config.milkdrop_enabled,
            "milkdrop_preset_path": config.milkdrop_preset_path,
            "milkdrop_texture_path": config.milkdrop_texture_path,
            "milkdrop_preset_duration": config.milkdrop_preset_duration,
            "milkdrop_hard_cut_on_beat": config.milkdrop_hard_cut_on_beat,
        },
        "video_clips_folder": config.video_clips_folder,
        "vjing_mappings": {m.letter: m.get_effects() for m in config.vjing_mappings},
        "vjing_preset": config.vjing_default_preset,
        "vjing_presets": {p.name: p.effects for p in config.vjing_presets},
        "color_palette": "neon",  # Same hardcoded default as ExportDialog's palette grid
        "waveform_height_ratio": config.waveform_height_ratio,
        "waveform_bass_color": config.waveform_bass_color,
        "waveform_mid_color": config.waveform_mid_color,
        "waveform_treble_color": config.waveform_treble_color,
        "waveform_cursor_color": config.waveform_cursor_color,
        "effect_intensities": {"_global": 1.0},  # Same as the dialog's 100% global slider
        "audio_sensitivity": {"bass": 1.0, "mid": 1.0, "treble": 1.0},
        "transitions_enabled": True,
        "simultaneous_effects": config.vjing_simultaneous_effects,
        "use_all_effects": False,
        "enabled_post_processing": [],
        "fade_duration": 1.0,  # Same default as the dialog's fade spinbox
        "intro_video_path": config.intro_video_path,
        "rng_seed": compute_deterministic_seed(track_metadata),
        "ffmpeg_video_codec": config.ffmpeg_video_codec,
        "ffmpeg_preset": config.ffmpeg_preset,
        "ffmpeg_crf": config.ffmpeg_crf,
        "ffmpeg_pixel_format": config.ffmpeg_pixel_format,
        "ffmpeg_audio_codec": config.ffmpeg_audio_codec,
        "ffmpeg_audio_bitrate": config.ffmpeg_audio_bitrate,
    }


def write_video_description(
    video_path: str | Path,
    track_metadata: dict[str, Any],
    genre_codes: list[GenreCodeConfig],
) -> None:
    """Write a .txt sidecar file with 'Artist - Title' and genre hashtags."""
    lines: list[str] = []

    artist = (track_metadata.get("artist") or "").strip()
    title = (track_metadata.get("title") or "").strip()
    if artist and title:
        lines.append(f"{artist} - {title}")
    elif artist or title:
        lines.append(artist or title)

    genre_str = (track_metadata.get("genre") or "").strip()
    if genre_str:
        code_to_hashtags: dict[str, list[str]] = {}
        for gc in genre_codes:
            if gc.hashtags:
                code_to_hashtags[gc.code] = [
                    t if t.startswith("#") else f"#{t}" for t in gc.hashtags
                ]
        codes = [p for p in genre_str.split("-") if not p.startswith("*")]
        hashtags: list[str] = []
        for c in codes:
            if c in code_to_hashtags:
                hashtags.extend(code_to_hashtags[c])
        if hashtags:
            lines.append(" ".join(hashtags))

    if not lines:
        return

    txt_path = Path(video_path).with_suffix(".txt")
    try:
        txt_path.write_text("\n".join(lines), encoding="utf-8")
        logging.info("[Video Exporter] Description written to %s", txt_path)
    except OSError as e:
        logging.warning("[Video Exporter] Failed to write description file: %s", e)
