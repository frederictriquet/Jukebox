#!/usr/bin/env python3
"""Diagnostic tool for shazamix matcher false positives.

Analyses why the matcher returns an incorrect track for a given mix segment.
Useful for investigating false positives in both Stage 1 (fingerprint) and
Stage 2 (MFCC+chroma) of the matching pipeline.

Usage:
    # Basic: diagnose what the matcher finds for a segment
    uv run scripts/diagnose_match.py --mix /path/to/mix.mp3 \
        --start 0 --end 330000

    # With expected track: compare scores between found and expected
    uv run scripts/diagnose_match.py --mix /path/to/mix.mp3 \
        --start 0 --end 330000 \
        --expected "/path/to/expected_track.mp3"

    # With known incorrect match for three-way comparison
    uv run scripts/diagnose_match.py --mix /path/to/mix.mp3 \
        --start 0 --end 330000 \
        --expected "/path/to/expected_track.mp3" \
        --incorrect "/path/to/wrong_match.mp3"

    # Only run screening (Stage 2a), skip heavy re-ranking
    uv run scripts/diagnose_match.py --mix /path/to/mix.mp3 \
        --start 0 --end 330000 --screening-only

    # Increase candidate pool
    uv run scripts/diagnose_match.py --mix /path/to/mix.mp3 \
        --start 0 --end 330000 --top-n 500

Experiment modes (require --expected and --incorrect):

    # Exp 1: Compare alternative scoring formulas
    uv run scripts/diagnose_match.py --mix /path/to/mix.mp3 \
        --start 0 --end 330000 \
        --expected "/path/to/correct.mp3" --incorrect "/path/to/wrong.mp3" \
        --exp-scoring

    # Exp 2: Test multiple sub-segment time windows
    uv run scripts/diagnose_match.py --mix /path/to/mix.mp3 \
        --start 0 --end 330000 \
        --expected "/path/to/correct.mp3" --incorrect "/path/to/wrong.mp3" \
        --exp-windows

    # Exp 3: Windowed screening (split query into 30s windows)
    uv run scripts/diagnose_match.py --mix /path/to/mix.mp3 \
        --start 0 --end 330000 \
        --expected "/path/to/correct.mp3" --incorrect "/path/to/wrong.mp3" \
        --exp-windowed-screening --window-size 30

    # Exp 4: Combined improved pipeline (windowed screening + sub-segment rerank)
    uv run scripts/diagnose_match.py --mix /path/to/mix.mp3 \
        --start 0 --end 330000 \
        --expected "/path/to/correct.mp3" --incorrect "/path/to/wrong.mp3" \
        --exp-combined --window-size 30 --rerank-window 90

    # Exp 5: Tempo drift root cause analysis
    uv run scripts/diagnose_match.py --mix /path/to/mix.mp3 \
        --start 0 --end 330000 \
        --expected "/path/to/correct.mp3" --incorrect "/path/to/wrong.mp3" \
        --exp-tempo-drift

    # Run ALL experiments at once
    uv run scripts/diagnose_match.py --mix /path/to/mix.mp3 \
        --start 0 --end 330000 \
        --expected "/path/to/correct.mp3" --incorrect "/path/to/wrong.mp3" \
        --exp-all

Outputs:
    - Stage 2a screening: compact MFCC+chroma cosine similarity ranking
    - Stage 2b re-ranking: dual-feature sustained run scores
    - Comparison between expected vs incorrect tracks (if provided)
    - Position of expected track in candidate rankings
    - Experiment results (if experiment flags used)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shazamix.database import DEFAULT_DB_PATH, FingerprintDB
from shazamix.matcher import Matcher


def _find_track_by_filepath(db: FingerprintDB, filepath: str) -> dict | None:
    """Find a track in the database by filepath (exact or partial match)."""
    conn = db._get_connection()

    # Try exact match first
    row = conn.execute(
        "SELECT id, filepath, filename, title, artist FROM tracks WHERE filepath = ?",
        (filepath,),
    ).fetchone()

    if not row:
        # Try partial match (filename only)
        filename = Path(filepath).name
        row = conn.execute(
            "SELECT id, filepath, filename, title, artist FROM tracks WHERE filename = ?",
            (filename,),
        ).fetchone()

    if not row:
        # Try LIKE match
        row = conn.execute(
            "SELECT id, filepath, filename, title, artist FROM tracks WHERE filepath LIKE ?",
            (f"%{Path(filepath).name}%",),
        ).fetchone()

    conn.close()
    return dict(row) if row else None


def _check_features(db: FingerprintDB, track_id: int) -> dict[str, bool]:
    """Check if a track has precomputed audio features."""
    conn = db._get_connection()
    rows = conn.execute(
        "SELECT feature_type FROM audio_features WHERE track_id = ?",
        (track_id,),
    ).fetchall()
    conn.close()
    types = {r[0] for r in rows}
    return {
        "mfcc_summary": "mfcc_summary" in types,
        "chroma_summary": "chroma_summary" in types,
    }


def _run_screening(
    matcher: Matcher,
    mix_path: str,
    start_ms: int,
    end_ms: int,
    top_n: int,
    track_ids_of_interest: list[int],
) -> dict:
    """Run Stage 2a screening and return detailed results."""
    import librosa

    sr = matcher.fingerprinter.sample_rate

    # Load summaries
    mfcc_summaries = matcher.db.get_all_audio_features("mfcc_summary")
    chroma_summaries = matcher.db.get_all_audio_features("chroma_summary")
    both_ids = set(mfcc_summaries.keys()) & set(chroma_summaries.keys())

    if not both_ids:
        return {"error": "No audio features in database"}

    # Load mix segment
    start_s = start_ms / 1000.0
    duration_s = (end_ms - start_ms) / 1000.0
    y, _ = librosa.load(mix_path, sr=sr, mono=True, offset=start_s, duration=duration_s)

    if len(y) == 0:
        return {"error": "Empty audio segment"}

    # Compute query features
    q_mfcc = Matcher.compute_mfcc_summary(y, sr)
    q_chroma = Matcher.compute_chroma_summary(y, sr)
    q_mfcc_norm = np.linalg.norm(q_mfcc)
    q_chroma_norm = np.linalg.norm(q_chroma)

    if q_mfcc_norm == 0 or q_chroma_norm == 0:
        return {"error": "Zero-norm query features"}

    q_combined = np.concatenate([q_mfcc / q_mfcc_norm, q_chroma / q_chroma_norm])
    q_combined_norm = np.linalg.norm(q_combined)

    scores: list[tuple[int, float, float, float]] = []
    for track_id in both_ids:
        m = mfcc_summaries[track_id]
        c = chroma_summaries[track_id]
        mn = np.linalg.norm(m)
        cn = np.linalg.norm(c)
        if mn == 0 or cn == 0:
            continue

        # Combined score (same as matcher)
        ref_combined = np.concatenate([m / mn, c / cn])
        rn = np.linalg.norm(ref_combined)
        cos_sim = float(np.dot(q_combined, ref_combined) / (q_combined_norm * rn))

        # Individual scores for diagnostic
        mfcc_sim = float(np.dot(q_mfcc / q_mfcc_norm, m / mn))
        chroma_sim = float(np.dot(q_chroma / q_chroma_norm, c / cn))

        scores.append((track_id, cos_sim, mfcc_sim, chroma_sim))

    scores.sort(key=lambda x: -x[1])

    # Find positions of tracks of interest
    positions = {}
    for tid in track_ids_of_interest:
        for i, (sid, _, _, _) in enumerate(scores):
            if sid == tid:
                positions[tid] = i
                break
        else:
            positions[tid] = -1  # Not found in scores

    return {
        "total_candidates": len(both_ids),
        "scored_candidates": len(scores),
        "top_n": scores[:top_n],
        "all_scores": scores,
        "positions": positions,
        "audio": y,
        "sr": sr,
    }


def _run_reranking(
    matcher: Matcher,
    y_query: np.ndarray,
    sr: int,
    track_ids: list[int],
) -> dict[int, dict]:
    """Run Stage 2b re-ranking on specific tracks and return detailed results."""
    import librosa

    hop = 2048
    slide_step = 15
    min_overlap = 30

    # Compute query features
    query_combined = Matcher._compute_combined_frame_features(y_query, sr, hop)
    query_chroma = librosa.feature.chroma_cqt(y=y_query, sr=sr, hop_length=hop)
    qn = np.linalg.norm(query_chroma, axis=0, keepdims=True)
    qn[qn == 0] = 1.0
    query_chroma_normed = query_chroma / qn

    results = {}

    for track_id in track_ids:
        track_info = matcher.db.get_track_info(track_id)
        if not track_info:
            results[track_id] = {"error": "Track not found in DB"}
            continue

        filepath = track_info.get("filepath", "")
        if not filepath or not Path(filepath).exists():
            results[track_id] = {"error": f"File not found: {filepath}"}
            continue

        try:
            y_ref, _ = librosa.load(filepath, sr=sr, mono=True)
            if len(y_ref) == 0:
                results[track_id] = {"error": "Empty reference audio"}
                continue

            ref_combined = Matcher._compute_combined_frame_features(y_ref, sr, hop)
            ref_chroma = librosa.feature.chroma_cqt(y=y_ref, sr=sr, hop_length=hop)
            rn = np.linalg.norm(ref_chroma, axis=0, keepdims=True)
            rn[rn == 0] = 1.0
            ref_chroma_normed = ref_chroma / rn

            if ref_combined.shape[1] < min_overlap:
                results[track_id] = {"error": f"Too short ({ref_combined.shape[1]} frames)"}
                continue

            comb_run, comb_sim = Matcher._best_sustained_run(
                query_combined, ref_combined, slide_step, min_overlap, 0.80
            )
            chro_run, chro_sim = Matcher._best_sustained_run(
                query_chroma_normed, ref_chroma_normed, slide_step, min_overlap, 0.92
            )

            score = min(comb_run, chro_run)
            avg_sim = min(comb_sim, chro_sim) if score > 0 else 0.0

            results[track_id] = {
                "combined_run": comb_run,
                "combined_sim": comb_sim,
                "combined_seconds": comb_run * hop / sr,
                "chroma_run": chro_run,
                "chroma_sim": chro_sim,
                "chroma_seconds": chro_run * hop / sr,
                "final_score": score,
                "final_sim": avg_sim,
                "final_seconds": score * hop / sr,
                "ref_frames": ref_combined.shape[1],
                "query_frames": query_combined.shape[1],
                "track_info": track_info,
            }

        except Exception as e:
            results[track_id] = {"error": str(e)}

    return results


def _print_header(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def _print_track(label: str, info: dict) -> None:
    artist = info.get("artist", "?")
    title = info.get("title", "?")
    filepath = info.get("filepath", "?")
    tid = info.get("id", "?")
    print(f"  {label}:")
    print(f"    ID={tid} | {artist} - {title}")
    print(f"    {filepath}")


def _print_screening_entry(rank: int, track_id: int, combined: float, mfcc: float,
                           chroma: float, db: FingerprintDB, marker: str = "") -> None:
    info = db.get_track_info(track_id)
    name = "?"
    if info:
        name = f"{info.get('artist', '?')} - {info.get('title', '?')}"
    marker_str = f" {marker}" if marker else ""
    print(f"  #{rank + 1:>3d}  combined={combined:.4f}  mfcc={mfcc:.4f}  "
          f"chroma={chroma:.4f}  | {name}{marker_str}")


def _print_reranking_entry(label: str, data: dict) -> None:
    if "error" in data:
        print(f"  {label}: ERROR - {data['error']}")
        return

    info = data["track_info"]
    print(f"  {label}: {info.get('artist', '?')} - {info.get('title', '?')}")
    print(f"    Combined: run={data['combined_run']} frames "
          f"({data['combined_seconds']:.1f}s), avg_sim={data['combined_sim']:.4f}")
    print(f"    Chroma:   run={data['chroma_run']} frames "
          f"({data['chroma_seconds']:.1f}s), avg_sim={data['chroma_sim']:.4f}")
    print(f"    FINAL:    score=min({data['combined_run']}, {data['chroma_run']}) = "
          f"{data['final_score']} frames ({data['final_seconds']:.1f}s), "
          f"sim={data['final_sim']:.4f}")


# ============================================================
# Experiment functions
# ============================================================


def _run_exp_scoring(
    matcher: Matcher,
    y_query: np.ndarray,
    sr: int,
    expected_id: int,
    incorrect_id: int,
) -> None:
    """Experiment 1: Compare alternative scoring formulas.

    Tests whether different combinations of run length and similarity
    would correctly rank the expected track above the incorrect one.
    """
    import librosa

    hop = 2048
    slide_step = 15
    min_overlap = 30

    _print_header("EXPERIMENT 1: SCORING ALTERNATIVES")

    results = {}
    for track_id in [expected_id, incorrect_id]:
        track_info = matcher.db.get_track_info(track_id)
        if not track_info:
            print(f"  ERROR: Track {track_id} not found")
            return
        filepath = track_info.get("filepath", "")
        if not filepath or not Path(filepath).exists():
            print(f"  ERROR: File not found: {filepath}")
            return

        y_ref, _ = librosa.load(filepath, sr=sr, mono=True)

        query_combined = Matcher._compute_combined_frame_features(y_query, sr, hop)
        ref_combined = Matcher._compute_combined_frame_features(y_ref, sr, hop)

        query_chroma = librosa.feature.chroma_cqt(y=y_query, sr=sr, hop_length=hop)
        qn = np.linalg.norm(query_chroma, axis=0, keepdims=True)
        qn[qn == 0] = 1.0
        query_chroma_normed = query_chroma / qn

        ref_chroma = librosa.feature.chroma_cqt(y=y_ref, sr=sr, hop_length=hop)
        rn = np.linalg.norm(ref_chroma, axis=0, keepdims=True)
        rn[rn == 0] = 1.0
        ref_chroma_normed = ref_chroma / rn

        comb_run, comb_sim = Matcher._best_sustained_run(
            query_combined, ref_combined, slide_step, min_overlap, 0.80
        )
        chro_run, chro_sim = Matcher._best_sustained_run(
            query_chroma_normed, ref_chroma_normed, slide_step, min_overlap, 0.92
        )

        results[track_id] = {
            "comb_run": comb_run,
            "comb_sim": comb_sim,
            "chro_run": chro_run,
            "chro_sim": chro_sim,
            "info": track_info,
        }

    exp = results[expected_id]
    inc = results[incorrect_id]

    formulas = [
        (
            "min(run)              [current]",
            lambda r: min(r["comb_run"], r["chro_run"]),
        ),
        (
            "min(run) * min(sim)",
            lambda r: min(r["comb_run"], r["chro_run"]) * min(r["comb_sim"], r["chro_sim"]),
        ),
        (
            "min(run * sim)",
            lambda r: min(r["comb_run"] * r["comb_sim"], r["chro_run"] * r["chro_sim"]),
        ),
        (
            "harmonic_mean(run)",
            lambda r: (
                2 * r["comb_run"] * r["chro_run"] / max(r["comb_run"] + r["chro_run"], 1)
            ),
        ),
        (
            "geometric_mean(run)",
            lambda r: (max(r["comb_run"], 0) * max(r["chro_run"], 0)) ** 0.5,
        ),
        (
            "min(run) * sim^2",
            lambda r: (
                min(r["comb_run"], r["chro_run"]) * min(r["comb_sim"], r["chro_sim"]) ** 2
            ),
        ),
    ]

    exp_name = "{} - {}".format(exp["info"].get("artist", "?"), exp["info"].get("title", "?"))
    inc_name = "{} - {}".format(inc["info"].get("artist", "?"), inc["info"].get("title", "?"))

    print(f"\n  Expected: {exp_name}")
    print(f"    comb_run={exp['comb_run']}, comb_sim={exp['comb_sim']:.4f}")
    print(f"    chro_run={exp['chro_run']}, chro_sim={exp['chro_sim']:.4f}")
    print(f"\n  Incorrect: {inc_name}")
    print(f"    comb_run={inc['comb_run']}, comb_sim={inc['comb_sim']:.4f}")
    print(f"    chro_run={inc['chro_run']}, chro_sim={inc['chro_sim']:.4f}")

    print(f"\n  {'Formula':<35s}  {'Expected':>10s}  {'Incorrect':>10s}  Winner")
    print(f"  {'-' * 75}")
    for name, fn in formulas:
        e_score = fn(exp)
        i_score = fn(inc)
        winner = "EXPECTED" if e_score > i_score else "incorrect" if i_score > e_score else "tie"
        marker = " <<" if winner == "EXPECTED" else ""
        print(f"  {name:<35s}  {e_score:>10.2f}  {i_score:>10.2f}  {winner}{marker}")


def _run_exp_windows(
    matcher: Matcher,
    mix_path: str,
    segment_start_ms: int,
    segment_end_ms: int,
    expected_id: int,
    incorrect_id: int,
) -> None:
    """Experiment 2: Test multiple sub-segment time windows.

    Re-ranks expected vs incorrect track using different time windows
    within the original segment to find which sub-segments discriminate best.
    """
    import librosa

    sr = matcher.fingerprinter.sample_rate
    hop = 2048
    slide_step = 15
    min_overlap = 30

    _print_header("EXPERIMENT 2: SUB-SEGMENT WINDOWS")

    segment_dur_s = (segment_end_ms - segment_start_ms) / 1000.0

    # Generate windows (relative to segment start, in seconds)
    windows = [
        (0, 60),
        (0, 90),
        (0, 120),
        (30, 90),
        (30, 120),
        (60, 120),
        (60, 180),
        (90, 180),
        (120, 210),
    ]
    # Add full segment
    windows.append((0, int(segment_dur_s)))
    # Filter out windows that exceed segment duration
    windows = [(s, e) for s, e in windows if e <= segment_dur_s + 1]

    # Load reference tracks once
    track_refs: dict[int, dict] = {}
    for track_id in [expected_id, incorrect_id]:
        info = matcher.db.get_track_info(track_id)
        if not info:
            print(f"  ERROR: Track {track_id} not found")
            return
        fp = info.get("filepath", "")
        if not fp or not Path(fp).exists():
            print(f"  ERROR: File not found: {fp}")
            return
        y_ref, _ = librosa.load(fp, sr=sr, mono=True)
        ref_combined = Matcher._compute_combined_frame_features(y_ref, sr, hop)
        ref_chroma = librosa.feature.chroma_cqt(y=y_ref, sr=sr, hop_length=hop)
        rn = np.linalg.norm(ref_chroma, axis=0, keepdims=True)
        rn[rn == 0] = 1.0
        ref_chroma_normed = ref_chroma / rn
        track_refs[track_id] = {
            "combined": ref_combined,
            "chroma": ref_chroma_normed,
            "info": info,
        }

    exp_name = "{} - {}".format(
        track_refs[expected_id]["info"].get("artist", "?"),
        track_refs[expected_id]["info"].get("title", "?"),
    )
    inc_name = "{} - {}".format(
        track_refs[incorrect_id]["info"].get("artist", "?"),
        track_refs[incorrect_id]["info"].get("title", "?"),
    )

    print(f"  Expected: {exp_name} (id={expected_id})")
    print(f"  Incorrect: {inc_name} (id={incorrect_id})")
    print(f"  Testing {len(windows)} windows...")

    print(f"\n  {'Window (s)':<15s}  {'Exp score':>10s}  {'Inc score':>10s}  Winner")
    print(f"  {'-' * 60}")

    for w_start_s, w_end_s in windows:
        offset_s = segment_start_ms / 1000.0 + w_start_s
        duration_s = w_end_s - w_start_s
        y_win, _ = librosa.load(
            mix_path, sr=sr, mono=True, offset=offset_s, duration=duration_s
        )
        if len(y_win) == 0:
            continue

        q_combined = Matcher._compute_combined_frame_features(y_win, sr, hop)
        q_chroma = librosa.feature.chroma_cqt(y=y_win, sr=sr, hop_length=hop)
        qn = np.linalg.norm(q_chroma, axis=0, keepdims=True)
        qn[qn == 0] = 1.0
        q_chroma_normed = q_chroma / qn

        scores = {}
        for tid in [expected_id, incorrect_id]:
            ref = track_refs[tid]
            if ref["combined"].shape[1] < min_overlap:
                scores[tid] = 0
                continue
            comb_run, _ = Matcher._best_sustained_run(
                q_combined, ref["combined"], slide_step, min_overlap, 0.80
            )
            chro_run, _ = Matcher._best_sustained_run(
                q_chroma_normed, ref["chroma"], slide_step, min_overlap, 0.92
            )
            scores[tid] = min(comb_run, chro_run)

        e_score = scores[expected_id]
        i_score = scores[incorrect_id]
        winner = "EXPECTED" if e_score > i_score else "incorrect" if i_score > e_score else "tie"
        marker = " <<" if winner == "EXPECTED" else ""
        label = "{}-{}".format(w_start_s, w_end_s)
        print(f"  {label:<15s}  {e_score:>10d}  {i_score:>10d}  {winner}{marker}")


def _run_exp_windowed_screening(
    matcher: Matcher,
    mix_path: str,
    start_ms: int,
    end_ms: int,
    window_size_s: int,
    top_n: int,
    track_ids_of_interest: list[int],
    show_top: int,
    db: FingerprintDB,
) -> dict:
    """Experiment 3: Windowed screening.

    Instead of computing a single summary for the full segment, splits the
    query into N-second windows and takes the max cosine similarity per track
    across all windows. This improves discrimination for long segments.

    Returns dict with ranking results.
    """
    import librosa

    sr = matcher.fingerprinter.sample_rate

    _print_header("EXPERIMENT 3: WINDOWED SCREENING")

    mfcc_summaries = matcher.db.get_all_audio_features("mfcc_summary")
    chroma_summaries = matcher.db.get_all_audio_features("chroma_summary")
    both_ids = set(mfcc_summaries.keys()) & set(chroma_summaries.keys())

    start_s = start_ms / 1000.0
    duration_s = (end_ms - start_ms) / 1000.0
    y, _ = librosa.load(mix_path, sr=sr, mono=True, offset=start_s, duration=duration_s)

    # Split into windows
    window_samples = window_size_s * sr
    n_windows = max(1, len(y) // window_samples)
    windows = []
    for i in range(n_windows):
        w_start = i * window_samples
        w_end = min((i + 1) * window_samples, len(y))
        if w_end - w_start > sr:  # At least 1 second
            windows.append(y[w_start:w_end])

    print(f"  Segment: {start_ms}ms - {end_ms}ms ({duration_s:.1f}s)")
    print(f"  Window size: {window_size_s}s")
    print(f"  Number of windows: {len(windows)}")
    print(f"  Tracks with features: {len(both_ids)}")

    # Precompute query summaries for each window
    t0 = time.time()
    query_features: list[tuple[np.ndarray, float]] = []
    for w in windows:
        q_mfcc = Matcher.compute_mfcc_summary(w, sr)
        q_chroma = Matcher.compute_chroma_summary(w, sr)
        q_mn = np.linalg.norm(q_mfcc)
        q_cn = np.linalg.norm(q_chroma)
        if q_mn == 0 or q_cn == 0:
            continue
        q_combined = np.concatenate([q_mfcc / q_mn, q_chroma / q_cn])
        q_norm = float(np.linalg.norm(q_combined))
        query_features.append((q_combined, q_norm))

    # For each track, compute max cosine similarity across windows
    track_max: dict[int, float] = {}
    for track_id in both_ids:
        m = mfcc_summaries[track_id]
        c = chroma_summaries[track_id]
        mn = np.linalg.norm(m)
        cn = np.linalg.norm(c)
        if mn == 0 or cn == 0:
            continue
        ref_combined = np.concatenate([m / mn, c / cn])
        rn = float(np.linalg.norm(ref_combined))

        max_sim = 0.0
        for q_feat, q_norm in query_features:
            sim = float(np.dot(q_feat, ref_combined) / (q_norm * rn))
            if sim > max_sim:
                max_sim = sim
        track_max[track_id] = max_sim

    elapsed = time.time() - t0

    # Sort by score
    ranked = sorted(track_max.items(), key=lambda x: -x[1])

    # Find positions of interest
    positions: dict[int, int] = {}
    for tid in track_ids_of_interest:
        for i, (sid, _) in enumerate(ranked):
            if sid == tid:
                positions[tid] = i
                break
        else:
            positions[tid] = -1

    print(f"  Scored: {len(ranked)}")
    print(f"  Time: {elapsed:.1f}s")

    # Show positions of interest
    if track_ids_of_interest:
        print("\n  Tracks of interest:")
        for tid in track_ids_of_interest:
            pos = positions.get(tid, -1)
            info = db.get_track_info(tid)
            name = "?"
            if info:
                name = "{} - {}".format(info.get("artist", "?"), info.get("title", "?"))
            if pos >= 0:
                score = ranked[pos][1]
                print(f"    id={tid}: rank #{pos + 1}, score={score:.4f} | {name}")
            else:
                print(f"    id={tid}: NOT FOUND | {name}")

    # Show top results
    top = ranked[:show_top]
    print(f"\n  Top {len(top)} results:")
    interest_set = set(track_ids_of_interest)
    for i, (tid, score) in enumerate(top):
        info = db.get_track_info(tid)
        name = "?"
        if info:
            name = "{} - {}".format(info.get("artist", "?"), info.get("title", "?"))
        marker = " << INTEREST" if tid in interest_set else ""
        print(f"  #{i + 1:>3d}  score={score:.4f}  | {name}{marker}")

    return {
        "ranked": ranked,
        "positions": positions,
        "audio": y,
        "sr": sr,
        "n_windows": len(windows),
    }


def _run_exp_combined(
    matcher: Matcher,
    mix_path: str,
    start_ms: int,
    end_ms: int,
    window_size_s: int,
    rerank_window_s: int,
    top_n: int,
    track_ids_of_interest: list[int],
    db: FingerprintDB,
) -> None:
    """Experiment 4: Combined improved pipeline.

    1. Windowed screening (Stage 2a improved) to get candidates
    2. Sub-segment re-ranking on top candidates (Stage 2b with shorter window)
    """
    import librosa

    _print_header("EXPERIMENT 4: COMBINED IMPROVED PIPELINE")

    sr = matcher.fingerprinter.sample_rate

    # Step 1: Windowed screening
    print(f"  Step 1: Windowed screening (window={window_size_s}s)")

    mfcc_summaries = matcher.db.get_all_audio_features("mfcc_summary")
    chroma_summaries = matcher.db.get_all_audio_features("chroma_summary")
    both_ids = set(mfcc_summaries.keys()) & set(chroma_summaries.keys())

    start_s = start_ms / 1000.0
    duration_s = (end_ms - start_ms) / 1000.0
    y, _ = librosa.load(mix_path, sr=sr, mono=True, offset=start_s, duration=duration_s)

    window_samples = window_size_s * sr
    n_windows = max(1, len(y) // window_samples)
    windows = []
    for i in range(n_windows):
        w_start = i * window_samples
        w_end = min((i + 1) * window_samples, len(y))
        if w_end - w_start > sr:
            windows.append(y[w_start:w_end])

    query_features: list[tuple[np.ndarray, float]] = []
    for w in windows:
        q_mfcc = Matcher.compute_mfcc_summary(w, sr)
        q_chroma = Matcher.compute_chroma_summary(w, sr)
        q_mn = np.linalg.norm(q_mfcc)
        q_cn = np.linalg.norm(q_chroma)
        if q_mn == 0 or q_cn == 0:
            continue
        q_combined = np.concatenate([q_mfcc / q_mn, q_chroma / q_cn])
        q_norm = float(np.linalg.norm(q_combined))
        query_features.append((q_combined, q_norm))

    track_max: dict[int, float] = {}
    for track_id in both_ids:
        m = mfcc_summaries[track_id]
        c = chroma_summaries[track_id]
        mn = np.linalg.norm(m)
        cn = np.linalg.norm(c)
        if mn == 0 or cn == 0:
            continue
        ref_combined = np.concatenate([m / mn, c / cn])
        rn = float(np.linalg.norm(ref_combined))
        max_sim = 0.0
        for q_feat, q_norm in query_features:
            sim = float(np.dot(q_feat, ref_combined) / (q_norm * rn))
            if sim > max_sim:
                max_sim = sim
        track_max[track_id] = max_sim

    ranked_screening = sorted(track_max.items(), key=lambda x: -x[1])
    candidates = [tid for tid, _ in ranked_screening[:top_n]]

    # Ensure interest tracks are included
    for tid in track_ids_of_interest:
        if tid not in candidates:
            candidates.append(tid)

    # Show screening positions for interest tracks
    interest_set = set(track_ids_of_interest)
    for tid in track_ids_of_interest:
        for i, (sid, sc) in enumerate(ranked_screening):
            if sid == tid:
                info = db.get_track_info(tid)
                name = "?"
                if info:
                    name = "{} - {}".format(info.get("artist", "?"), info.get("title", "?"))
                print(f"    Screening rank #{i + 1}: {name} (score={sc:.4f})")
                break

    # Step 2: Re-rank with sub-segment
    rerank_duration = min(rerank_window_s, duration_s)
    print(f"\n  Step 2: Re-ranking top {len(candidates)} with {rerank_duration:.0f}s window")

    y_rerank, _ = librosa.load(
        mix_path, sr=sr, mono=True, offset=start_s, duration=rerank_duration
    )

    hop = 2048
    slide_step = 15
    min_overlap = 30

    query_combined = Matcher._compute_combined_frame_features(y_rerank, sr, hop)
    query_chroma = librosa.feature.chroma_cqt(y=y_rerank, sr=sr, hop_length=hop)
    qn = np.linalg.norm(query_chroma, axis=0, keepdims=True)
    qn[qn == 0] = 1.0
    query_chroma_normed = query_chroma / qn

    t0 = time.time()
    rerank_results: list[tuple[int, int, float, dict]] = []
    for tid in candidates:
        info = db.get_track_info(tid)
        if not info:
            continue
        fp = info.get("filepath", "")
        if not fp or not Path(fp).exists():
            continue
        try:
            y_ref, _ = librosa.load(fp, sr=sr, mono=True)
            if len(y_ref) == 0:
                continue
            ref_combined = Matcher._compute_combined_frame_features(y_ref, sr, hop)
            ref_chroma = librosa.feature.chroma_cqt(y=y_ref, sr=sr, hop_length=hop)
            rn = np.linalg.norm(ref_chroma, axis=0, keepdims=True)
            rn[rn == 0] = 1.0
            ref_chroma_normed = ref_chroma / rn

            if ref_combined.shape[1] < min_overlap:
                continue

            comb_run, comb_sim = Matcher._best_sustained_run(
                query_combined, ref_combined, slide_step, min_overlap, 0.80
            )
            chro_run, chro_sim = Matcher._best_sustained_run(
                query_chroma_normed, ref_chroma_normed, slide_step, min_overlap, 0.92
            )
            score = min(comb_run, chro_run)
            avg_sim = min(comb_sim, chro_sim) if score > 0 else 0.0

            rerank_results.append((tid, score, avg_sim, info))
        except Exception:
            continue

    elapsed = time.time() - t0
    rerank_results.sort(key=lambda r: (-r[1], -r[2]))

    print(f"  Re-ranking time: {elapsed:.1f}s")
    print(f"\n  Final ranking (top {min(20, len(rerank_results))}):")
    for i, (tid, score, sim, info) in enumerate(rerank_results[:20]):
        name = "{} - {}".format(info.get("artist", "?"), info.get("title", "?"))
        marker = " << INTEREST" if tid in interest_set else ""
        seconds = score * hop / sr
        print(f"  #{i + 1:>3d}  score={score} ({seconds:.1f}s) sim={sim:.4f} | {name}{marker}")


def _run_exp_tempo_drift(
    matcher: Matcher,
    y_query: np.ndarray,
    sr: int,
    expected_id: int,
    incorrect_id: int,
    db: FingerprintDB,
) -> None:
    """Experiment 5: Tempo drift root cause analysis.

    Tests whether tempo compensation (time-stretching the reference) improves
    the sustained run for the expected track vs the incorrect one.

    ROOT CAUSE: DJs typically play tracks at ±2-8% tempo.  Stage 1 (fingerprint)
    compensates by testing 15 stretch ratios.  Stage 2 (MFCC+chroma) does NOT,
    causing progressive frame drift that limits sustained runs for true matches
    while coincidental false positives are unaffected.

    This experiment:
    1. Tests ratios 0.92..1.08 (step 0.01) on both tracks
    2. Computes combined run, chroma run, and final score at each ratio
    3. Identifies the optimal ratio for each track
    4. Shows whether tempo compensation would fix the false positive
    """
    import librosa

    hop = 2048
    slide_step = 15
    min_overlap = 30

    _print_header("EXPERIMENT 5: TEMPO DRIFT ROOT CAUSE ANALYSIS")

    # Compute query features once
    query_combined = Matcher._compute_combined_frame_features(y_query, sr, hop)
    query_chroma = librosa.feature.chroma_cqt(y=y_query, sr=sr, hop_length=hop)
    qn = np.linalg.norm(query_chroma, axis=0, keepdims=True)
    qn[qn == 0] = 1.0
    query_chroma_normed = query_chroma / qn

    ratios = [round(0.92 + i * 0.01, 2) for i in range(17)]  # 0.92..1.08

    for label, track_id in [("EXPECTED", expected_id), ("INCORRECT", incorrect_id)]:
        track_info = db.get_track_info(track_id)
        if not track_info:
            print(f"\n  {label}: Track {track_id} not found")
            continue
        filepath = track_info.get("filepath", "")
        if not filepath or not Path(filepath).exists():
            print(f"\n  {label}: File not found: {filepath}")
            continue

        name = "{} - {}".format(
            track_info.get("artist", "?"), track_info.get("title", "?")
        )
        print(f"\n  --- {label}: {name} (id={track_id}) ---")
        print(
            f"  {'Ratio':>6s}  {'Comb run':>9s}  {'Comb s':>7s}  {'Comb sim':>9s}  "
            f"{'Chro run':>9s}  {'Chro s':>7s}  {'Chro sim':>9s}  "
            f"{'Score':>6s}  {'Score s':>8s}"
        )
        print(f"  {'-' * 95}")

        best_score = 0
        best_ratio = 1.0
        best_comb_run = 0
        best_comb_ratio = 1.0
        baseline_score = 0
        baseline_comb = 0
        baseline_chro = 0

        for ratio in ratios:
            y_ref, _ = librosa.load(filepath, sr=sr, mono=True)
            if ratio != 1.0:
                y_ref = librosa.effects.time_stretch(y_ref, rate=ratio)

            ref_combined = Matcher._compute_combined_frame_features(y_ref, sr, hop)
            ref_chroma = librosa.feature.chroma_cqt(y=y_ref, sr=sr, hop_length=hop)
            rn = np.linalg.norm(ref_chroma, axis=0, keepdims=True)
            rn[rn == 0] = 1.0
            ref_chroma_normed = ref_chroma / rn

            if ref_combined.shape[1] < min_overlap:
                continue

            comb_run, comb_sim = Matcher._best_sustained_run(
                query_combined, ref_combined, slide_step, min_overlap, 0.80
            )
            chro_run, chro_sim = Matcher._best_sustained_run(
                query_chroma_normed, ref_chroma_normed, slide_step, min_overlap, 0.92
            )

            score = min(comb_run, chro_run)
            comb_s = comb_run * hop / sr
            chro_s = chro_run * hop / sr
            score_s = score * hop / sr

            marker = ""
            if ratio == 1.00:
                marker = "  << baseline"
                baseline_score = score
                baseline_comb = comb_run
                baseline_chro = chro_run
            if score > best_score:
                best_score = score
                best_ratio = ratio
            if comb_run > best_comb_run:
                best_comb_run = comb_run
                best_comb_ratio = ratio

            print(
                f"  {ratio:6.2f}  {comb_run:9d}  {comb_s:6.1f}s  {comb_sim:9.4f}  "
                f"{chro_run:9d}  {chro_s:6.1f}s  {chro_sim:9.4f}  "
                f"{score:6d}  {score_s:7.1f}s{marker}"
            )

        # Summary for this track
        if baseline_score > 0 or best_score > 0:
            comb_improvement = (
                (best_comb_run - baseline_comb) / baseline_comb * 100
                if baseline_comb > 0
                else 0
            )
            score_improvement = (
                (best_score - baseline_score) / baseline_score * 100
                if baseline_score > 0
                else 0
            )
            print(f"\n  Summary for {label}:")
            print(
                f"    Baseline (1.00): combined={baseline_comb} frames, "
                f"chroma={baseline_chro} frames, score={baseline_score} frames"
            )
            print(
                f"    Best combined run: {best_comb_run} frames at ratio={best_comb_ratio:.2f} "
                f"({comb_improvement:+.0f}%)"
            )
            print(
                f"    Best final score: {best_score} frames at ratio={best_ratio:.2f} "
                f"({score_improvement:+.0f}%)"
            )

    # ---- Verdict ----
    print(f"\n  {'=' * 70}")
    print("  TEMPO DRIFT VERDICT")
    print(f"  {'=' * 70}")
    print(
        "\n  If the EXPECTED track shows a dramatic improvement (>100%) at a "
        "specific ratio"
    )
    print(
        "  while the INCORRECT track shows only moderate variation (<50%), "
        "this confirms"
    )
    print("  that TEMPO DRIFT is the root cause of the false positive.")
    print(
        "\n  Mechanism: The DJ played the track at a different tempo. "
        "match_segment_by_mfcc()"
    )
    print(
        "  does NOT time-stretch references (unlike Stage 1 fingerprinting "
        "which tests"
    )
    print(
        "  15 ratios). The progressive frame misalignment limits the sustained "
        "run for"
    )
    print(
        "  the true match, allowing coincidental false positives to win by "
        "narrow margins."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose shazamix matcher false positives",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--mix", required=True, help="Path to the mix audio file")
    parser.add_argument("--start", type=int, required=True, help="Segment start (ms)")
    parser.add_argument("--end", type=int, required=True, help="Segment end (ms)")
    parser.add_argument("--expected", help="Filepath of the expected correct track")
    parser.add_argument("--incorrect", help="Filepath of the incorrectly matched track")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Database path")
    parser.add_argument("--top-n", type=int, default=200, help="Screening candidates (default 200)")
    parser.add_argument("--show-top", type=int, default=20,
                        help="Number of top screening results to display (default 20)")
    parser.add_argument("--screening-only", action="store_true",
                        help="Only run Stage 2a screening, skip re-ranking")

    # Experiment modes
    exp_group = parser.add_argument_group("experiments")
    exp_group.add_argument("--exp-scoring", action="store_true",
                           help="Exp 1: Compare alternative scoring formulas")
    exp_group.add_argument("--exp-windows", action="store_true",
                           help="Exp 2: Test multiple sub-segment time windows")
    exp_group.add_argument("--exp-windowed-screening", action="store_true",
                           help="Exp 3: Windowed screening (split query into windows)")
    exp_group.add_argument("--exp-combined", action="store_true",
                           help="Exp 4: Combined improved pipeline")
    exp_group.add_argument("--exp-tempo-drift", action="store_true",
                           help="Exp 5: Tempo drift root cause analysis")
    exp_group.add_argument("--exp-all", action="store_true",
                           help="Run ALL experiments")
    exp_group.add_argument("--window-size", type=int, default=30,
                           help="Window size in seconds for windowed experiments (default 30)")
    exp_group.add_argument("--rerank-window", type=int, default=90,
                           help="Re-ranking window in seconds for combined pipeline (default 90)")

    args = parser.parse_args()

    # --exp-all enables all experiments
    if args.exp_all:
        args.exp_scoring = True
        args.exp_windows = True
        args.exp_windowed_screening = True
        args.exp_combined = True
        args.exp_tempo_drift = True

    any_experiment = (
        args.exp_scoring or args.exp_windows
        or args.exp_windowed_screening or args.exp_combined
        or args.exp_tempo_drift
    )

    # Validate inputs
    mix_path = Path(args.mix)
    if not mix_path.exists():
        print(f"ERROR: Mix file not found: {mix_path}")
        sys.exit(1)

    db = FingerprintDB(args.db)
    matcher = Matcher(db)

    _print_header("MATCH DIAGNOSTIC")
    print(f"  Mix: {mix_path}")
    print(f"  Segment: {args.start}ms - {args.end}ms "
          f"({(args.end - args.start) / 1000:.1f}s)")

    # Resolve tracks of interest
    tracks_of_interest: dict[str, dict] = {}
    track_ids_of_interest: list[int] = []

    if args.expected:
        info = _find_track_by_filepath(db, args.expected)
        if info:
            tracks_of_interest["EXPECTED"] = info
            track_ids_of_interest.append(info["id"])
            features = _check_features(db, info["id"])
            _print_track("Expected (correct) track", info)
            print(f"    Features: mfcc={features['mfcc_summary']}, "
                  f"chroma={features['chroma_summary']}")
        else:
            print(f"\n  WARNING: Expected track not found in DB: {args.expected}")

    if args.incorrect:
        info = _find_track_by_filepath(db, args.incorrect)
        if info:
            tracks_of_interest["INCORRECT"] = info
            track_ids_of_interest.append(info["id"])
            features = _check_features(db, info["id"])
            _print_track("Incorrect (false positive) track", info)
            print(f"    Features: mfcc={features['mfcc_summary']}, "
                  f"chroma={features['chroma_summary']}")
        else:
            print(f"\n  WARNING: Incorrect track not found in DB: {args.incorrect}")

    # ---- Stage 2a: Screening ----
    _print_header("STAGE 2a: MFCC+CHROMA SCREENING")
    t0 = time.time()
    screening = _run_screening(
        matcher, str(mix_path), args.start, args.end, args.top_n, track_ids_of_interest
    )
    elapsed = time.time() - t0

    if "error" in screening:
        print(f"  ERROR: {screening['error']}")
        sys.exit(1)

    print(f"  Candidates with features: {screening['total_candidates']}")
    print(f"  Scored: {screening['scored_candidates']}")
    print(f"  Time: {elapsed:.1f}s")

    # Show positions of tracks of interest
    if track_ids_of_interest:
        print(f"\n  Tracks of interest in screening ranking:")
        for label, tinfo in tracks_of_interest.items():
            tid = tinfo["id"]
            pos = screening["positions"].get(tid, -1)
            if pos >= 0:
                entry = screening["all_scores"][pos]
                print(f"    {label} (id={tid}): rank #{pos + 1}, "
                      f"combined={entry[1]:.4f}, mfcc={entry[2]:.4f}, chroma={entry[3]:.4f}")
            else:
                print(f"    {label} (id={tid}): NOT FOUND in scores (missing features?)")

    # Show top results
    top = screening["top_n"][:args.show_top]
    print(f"\n  Top {len(top)} screening results:")
    interest_ids = {t["id"] for t in tracks_of_interest.values()}
    for i, (tid, combined, mfcc, chroma) in enumerate(top):
        marker = ""
        for label, tinfo in tracks_of_interest.items():
            if tinfo["id"] == tid:
                marker = f"<< {label}"
                break
        _print_screening_entry(i, tid, combined, mfcc, chroma, db, marker)

    if args.screening_only and not any_experiment:
        print("\n  (--screening-only: skipping Stage 2b)")
        return

    if args.screening_only and any_experiment:
        print("\n  (--screening-only: skipping Stage 2b, running experiments below)")
        # Skip to experiments section at the end
        if "EXPECTED" not in tracks_of_interest or "INCORRECT" not in tracks_of_interest:
            print("\n  WARNING: Experiments require both --expected and --incorrect tracks.")
            return

        exp_id = tracks_of_interest["EXPECTED"]["id"]
        inc_id = tracks_of_interest["INCORRECT"]["id"]

        if args.exp_scoring:
            _run_exp_scoring(
                matcher, screening["audio"], screening["sr"], exp_id, inc_id
            )
        if args.exp_windows:
            _run_exp_windows(
                matcher, str(mix_path), args.start, args.end, exp_id, inc_id
            )
        if args.exp_windowed_screening:
            _run_exp_windowed_screening(
                matcher, str(mix_path), args.start, args.end, args.window_size,
                args.top_n, track_ids_of_interest, args.show_top, db,
            )
        if args.exp_combined:
            _run_exp_combined(
                matcher, str(mix_path), args.start, args.end, args.window_size,
                args.rerank_window, args.top_n, track_ids_of_interest, db,
            )
        if args.exp_tempo_drift:
            _run_exp_tempo_drift(
                matcher, screening["audio"], screening["sr"], exp_id, inc_id, db,
            )
        return

    # ---- Stage 2b: Re-ranking ----
    _print_header("STAGE 2b: DUAL-FEATURE RE-RANKING")

    # Re-rank tracks of interest + top-5 screening candidates
    rerank_ids = list(track_ids_of_interest)
    for tid, _, _, _ in screening["top_n"][:5]:
        if tid not in rerank_ids:
            rerank_ids.append(tid)

    print(f"  Re-ranking {len(rerank_ids)} tracks...")
    t0 = time.time()
    reranking = _run_reranking(
        matcher, screening["audio"], screening["sr"], rerank_ids
    )
    elapsed = time.time() - t0
    print(f"  Time: {elapsed:.1f}s")

    # Print results for tracks of interest first
    if tracks_of_interest:
        print(f"\n  Tracks of interest:")
        for label, tinfo in tracks_of_interest.items():
            tid = tinfo["id"]
            if tid in reranking:
                _print_reranking_entry(label, reranking[tid])
            else:
                print(f"  {label}: not re-ranked")

    # Print other top candidates
    others = [tid for tid in rerank_ids if tid not in {t["id"] for t in tracks_of_interest.values()}]
    if others:
        print(f"\n  Other top screening candidates:")
        for tid in others:
            if tid in reranking:
                _print_reranking_entry(f"Track {tid}", reranking[tid])

    # Sort all re-ranked by final_score
    ranked = []
    for tid, data in reranking.items():
        if "error" not in data:
            ranked.append((tid, data["final_score"], data["final_sim"], data))
    ranked.sort(key=lambda r: (-r[1], -r[2]))

    if ranked:
        _print_header("FINAL RANKING (by min(combined_run, chroma_run))")
        for i, (tid, score, sim, data) in enumerate(ranked):
            info = data["track_info"]
            marker = ""
            for label, tinfo in tracks_of_interest.items():
                if tinfo["id"] == tid:
                    marker = f" << {label}"
                    break
            print(f"  #{i + 1}  score={score} ({data['final_seconds']:.1f}s) "
                  f"sim={sim:.4f} | "
                  f"{info.get('artist', '?')} - {info.get('title', '?')}{marker}")

    # ---- Diagnosis summary ----
    if "EXPECTED" in tracks_of_interest and "INCORRECT" in tracks_of_interest:
        _print_header("DIAGNOSIS SUMMARY")
        exp_id = tracks_of_interest["EXPECTED"]["id"]
        inc_id = tracks_of_interest["INCORRECT"]["id"]
        exp_data = reranking.get(exp_id, {})
        inc_data = reranking.get(inc_id, {})

        if "error" in exp_data or "error" in inc_data:
            print("  Cannot compare: one or both tracks had errors during re-ranking")
        else:
            exp_pos = screening["positions"].get(exp_id, -1)
            inc_pos = screening["positions"].get(inc_id, -1)

            print(f"  Screening position: expected=#{exp_pos + 1}, incorrect=#{inc_pos + 1}")

            if exp_pos >= args.top_n:
                print(f"  >> EXPECTED TRACK NOT IN TOP-{args.top_n} CANDIDATES!")
                print(f"     This means the correct track is filtered out before re-ranking.")
                print(f"     Consider: --top-n {max(args.top_n * 2, exp_pos + 50)}")

            exp_cs = exp_data.get("combined_run", 0)
            inc_cs = inc_data.get("combined_run", 0)
            exp_cr = exp_data.get("chroma_run", 0)
            inc_cr = inc_data.get("chroma_run", 0)
            exp_fs = exp_data.get("final_score", 0)
            inc_fs = inc_data.get("final_score", 0)

            print(f"\n  Combined run:  expected={exp_cs} vs incorrect={inc_cs}  "
                  f"({'expected wins' if exp_cs > inc_cs else 'incorrect wins' if inc_cs > exp_cs else 'tie'})")
            print(f"  Chroma run:    expected={exp_cr} vs incorrect={inc_cr}  "
                  f"({'expected wins' if exp_cr > inc_cr else 'incorrect wins' if inc_cr > exp_cr else 'tie'})")
            print(f"  Final score:   expected={exp_fs} vs incorrect={inc_fs}  "
                  f"({'expected wins' if exp_fs > inc_fs else 'INCORRECT WINS' if inc_fs > exp_fs else 'tie'})")

            if inc_fs > exp_fs:
                print(f"\n  CONCLUSION: False positive confirmed.")
                if exp_cs > inc_cs and exp_cr < inc_cr:
                    print("  Root cause: Expected track wins on timbre (combined) but "
                          "loses on harmony (chroma).")
                    print("  Possible fix: Adjust chroma threshold or weighting.")
                elif exp_cs < inc_cs and exp_cr > inc_cr:
                    print("  Root cause: Expected track wins on harmony (chroma) but "
                          "loses on timbre (combined).")
                    print("  Possible fix: Adjust combined threshold or weighting.")
                elif exp_cs < inc_cs and exp_cr < inc_cr:
                    print("  Root cause: Expected track loses on BOTH metrics.")
                    print("  Possible causes: tempo shift, key change, or different "
                          "version/remix in DB.")
                else:
                    print("  Root cause: Needs further investigation.")
            elif exp_fs > inc_fs:
                print(f"\n  CONCLUSION: Expected track scores HIGHER in re-ranking.")
                print("  The false positive may be a Stage 2a screening issue "
                      "(expected track filtered out).")

    # ---- Experiment modes ----
    if any_experiment:
        if "EXPECTED" not in tracks_of_interest or "INCORRECT" not in tracks_of_interest:
            print("\n  WARNING: Experiments require both --expected and --incorrect tracks.")
            print("  Skipping experiments.")
            return

        exp_id = tracks_of_interest["EXPECTED"]["id"]
        inc_id = tracks_of_interest["INCORRECT"]["id"]

        if args.exp_scoring:
            _run_exp_scoring(
                matcher, screening["audio"], screening["sr"], exp_id, inc_id
            )

        if args.exp_windows:
            _run_exp_windows(
                matcher, str(mix_path), args.start, args.end, exp_id, inc_id
            )

        if args.exp_windowed_screening:
            _run_exp_windowed_screening(
                matcher,
                str(mix_path),
                args.start,
                args.end,
                args.window_size,
                args.top_n,
                track_ids_of_interest,
                args.show_top,
                db,
            )

        if args.exp_combined:
            _run_exp_combined(
                matcher,
                str(mix_path),
                args.start,
                args.end,
                args.window_size,
                args.rerank_window,
                args.top_n,
                track_ids_of_interest,
                db,
            )

        if args.exp_tempo_drift:
            _run_exp_tempo_drift(
                matcher, screening["audio"], screening["sr"], exp_id, inc_id, db,
            )


if __name__ == "__main__":
    main()
