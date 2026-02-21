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

Outputs:
    - Stage 2a screening: compact MFCC+chroma cosine similarity ranking
    - Stage 2b re-ranking: dual-feature sustained run scores
    - Comparison between expected vs incorrect tracks (if provided)
    - Position of expected track in candidate rankings
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

    args = parser.parse_args()

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

    if args.screening_only:
        print("\n  (--screening-only: skipping Stage 2b)")
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


if __name__ == "__main__":
    main()
