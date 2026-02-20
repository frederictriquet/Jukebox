"""Persistent cache for mix fingerprints and waveform data."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".jukebox" / "cue_cache"


def _cache_key(mix_path: str) -> str:
    """Build a cache key from mix file path, size and mtime."""
    p = Path(mix_path)
    stat = p.stat()
    raw = f"{p.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _fingerprints_cache_file(mix_path: str) -> Path:
    """Return the fingerprints cache file path for a given mix."""
    return CACHE_DIR / f"{_cache_key(mix_path)}_fingerprints.npz"


def _waveform_cache_file(mix_path: str) -> Path:
    """Return the waveform cache file path for a given mix."""
    return CACHE_DIR / f"{_cache_key(mix_path)}_waveform.npz"


def load_cached_fingerprints(mix_path: str) -> list[list] | None:
    """Load cached segment-grouped fingerprints for a mix, or None if not cached.

    Returns a list of lists of Fingerprint objects (one inner list per segment).
    """
    path = _fingerprints_cache_file(mix_path)
    if not path.exists():
        return None

    try:
        from shazamix.fingerprint import Fingerprint

        data = np.load(path)
        hashes = data["hashes"]
        time_offsets = data["time_offsets"]
        freq_bins = data["freq_bins"]
        segment_boundaries = data["segment_boundaries"]

        # Reconstruct segment-grouped fingerprints
        segments: list[list] = []
        for seg_idx in range(len(segment_boundaries) - 1):
            start = int(segment_boundaries[seg_idx])
            end = int(segment_boundaries[seg_idx + 1])
            seg_fps = [
                Fingerprint(
                    hash=int(hashes[i]),
                    time_offset_ms=int(time_offsets[i]),
                    freq_bin=int(freq_bins[i]),
                )
                for i in range(start, end)
            ]
            segments.append(seg_fps)

        total = sum(len(s) for s in segments)
        logger.info(
            "[Cache] Loaded %d cached fingerprints (%d segments) for %s",
            total,
            len(segments),
            mix_path,
        )
        return segments
    except Exception:
        logger.warning("[Cache] Failed to read fingerprints cache for %s", mix_path, exc_info=True)
        return None


def save_fingerprints_cache(mix_path: str, segment_fps_list: list[list]) -> None:
    """Save segment-grouped fingerprints to disk cache as compressed numpy arrays.

    Stores three arrays (hashes, time_offsets, freq_bins) plus a segment_boundaries
    array to reconstruct the grouping on load.
    """
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Flatten all segments into single arrays, tracking boundaries
        all_hashes = []
        all_time_offsets = []
        all_freq_bins = []
        boundaries = [0]

        for seg_fps in segment_fps_list:
            for fp in seg_fps:
                all_hashes.append(fp.hash)
                all_time_offsets.append(fp.time_offset_ms)
                all_freq_bins.append(fp.freq_bin)
            boundaries.append(len(all_hashes))

        np.savez_compressed(
            _fingerprints_cache_file(mix_path),
            hashes=np.array(all_hashes, dtype=np.int64),
            time_offsets=np.array(all_time_offsets, dtype=np.int32),
            freq_bins=np.array(all_freq_bins, dtype=np.int32),
            segment_boundaries=np.array(boundaries, dtype=np.int32),
        )
        total = sum(len(s) for s in segment_fps_list)
        logger.info(
            "[Cache] Saved %d fingerprints (%d segments) for %s",
            total,
            len(segment_fps_list),
            mix_path,
        )
    except Exception:
        logger.warning("[Cache] Failed to save fingerprints cache for %s", mix_path, exc_info=True)


def load_cached_waveform(mix_path: str) -> dict[str, np.ndarray] | None:
    """Load cached waveform data for a mix, or None if not cached."""
    path = _waveform_cache_file(mix_path)
    if not path.exists():
        return None

    try:
        data = np.load(path)
        waveform = {
            "bass": data["bass"],
            "mid": data["mid"],
            "treble": data["treble"],
        }
        logger.info("[Cache] Loaded cached waveform for %s", mix_path)
        return waveform
    except Exception:
        logger.warning("[Cache] Failed to read waveform cache for %s", mix_path, exc_info=True)
        return None


def save_waveform_cache(mix_path: str, waveform: dict[str, np.ndarray]) -> None:
    """Save waveform data to disk cache."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            _waveform_cache_file(mix_path),
            bass=waveform["bass"],
            mid=waveform["mid"],
            treble=waveform["treble"],
        )
        logger.info("[Cache] Saved waveform for %s", mix_path)
    except Exception:
        logger.warning("[Cache] Failed to save waveform cache for %s", mix_path, exc_info=True)


def _entries_cache_file(mix_path: str) -> Path:
    """Return the entries cache file path for a given mix."""
    return CACHE_DIR / f"{_cache_key(mix_path)}_entries.json"


def save_entries_cache(mix_path: str, entries: list) -> None:
    """Save cue entries to disk cache as JSON."""
    try:
        import json

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "start_time_ms": e.start_time_ms,
                "artist": e.artist,
                "title": e.title,
                "confidence": e.confidence,
                "duration_ms": e.duration_ms,
                "status": e.status.value,
                "filepath": e.filepath,
                "track_id": e.track_id,
                "time_stretch_ratio": e.time_stretch_ratio,
            }
            for e in entries
        ]
        path = _entries_cache_file(mix_path)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[Cache] Saved %d entries for %s", len(entries), mix_path)
    except Exception:
        logger.warning("[Cache] Failed to save entries cache for %s", mix_path, exc_info=True)


def load_cached_entries(mix_path: str) -> list | None:
    """Load cached cue entries for a mix, or None if not cached."""
    try:
        path = _entries_cache_file(mix_path)
    except OSError:
        logger.debug("[Cache] Cannot stat mix file for cache key: %s", mix_path)
        return None
    if not path.exists():
        return None

    try:
        import json

        from plugins.cue_maker.model import CueEntry, EntryStatus

        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = [
            CueEntry(
                start_time_ms=d["start_time_ms"],
                artist=d["artist"],
                title=d["title"],
                confidence=d["confidence"],
                duration_ms=d["duration_ms"],
                status=EntryStatus(d["status"]),
                filepath=d.get("filepath", ""),
                track_id=d.get("track_id"),
                time_stretch_ratio=d.get("time_stretch_ratio", 1.0),
            )
            for d in raw
        ]
        logger.info("[Cache] Loaded %d cached entries for %s", len(entries), mix_path)
        return entries
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        logger.warning(
            "[Cache] Failed to read entries cache for %s (%s: %s)",
            mix_path,
            type(e).__name__,
            e,
        )
        return None
