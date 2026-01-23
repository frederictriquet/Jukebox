"""Command-line interface for Shazamix.

Commands:
    index     - Index tracks from Jukebox database
    identify  - Identify a single audio file
    analyze   - Analyze a mix to find all tracks
    stats     - Show indexing statistics
    clear     - Clear all fingerprints
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from .database import FingerprintDB, DEFAULT_DB_PATH


def cmd_stats(args: argparse.Namespace) -> int:
    """Show fingerprint database statistics."""
    db = FingerprintDB(args.db)
    stats = db.get_stats()

    print("Shazamix Fingerprint Database Statistics")
    print("=" * 40)
    print(f"Total tracks in Jukebox:    {stats['total_tracks']:,}")
    print(f"Indexed tracks:             {stats['indexed_tracks']:,}")
    print(f"Unindexed tracks:           {stats['unindexed_tracks']:,}")
    print(f"Total fingerprints:         {stats['total_fingerprints']:,}")
    print(f"Avg fingerprints/track:     {stats['avg_fingerprints_per_track']:.0f}")
    print()

    if stats['indexed_tracks'] > 0:
        progress = stats['indexed_tracks'] / stats['total_tracks'] * 100
        print(f"Indexing progress:          {progress:.1f}%")

    return 0


def _index_single_track(args: tuple[int, str]) -> tuple[int, str, int | None, str | None]:
    """Index a single track (worker function for multiprocessing).

    Args:
        args: Tuple of (track_id, filepath)

    Returns:
        Tuple of (track_id, filepath, fingerprint_count or None, error or None)
    """
    from .fingerprint import Fingerprinter

    track_id, filepath = args

    try:
        fp = Fingerprinter()
        fingerprints = fp.extract_fingerprints(filepath)
        return (track_id, filepath, len(fingerprints), None)
    except Exception as e:
        return (track_id, filepath, None, str(e))


def cmd_index(args: argparse.Namespace) -> int:
    """Index tracks from Jukebox database."""
    db = FingerprintDB(args.db)

    # Get tracks to index
    tracks = db.get_tracks_to_index(mode=args.mode, limit=args.limit)

    if not tracks:
        print("All tracks are already indexed.")
        return 0

    print(f"Indexing {len(tracks)} tracks...")
    print(f"Using {args.workers} workers")
    print()

    start_time = time.time()
    indexed = 0
    errors = 0

    # Process with multiprocessing
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(_index_single_track, (t["id"], t["filepath"])): t
            for t in tracks
        }

        for future in as_completed(futures):
            track_id, filepath, fp_count, error = future.result()
            filename = os.path.basename(filepath)

            if fp_count is not None:
                # Store fingerprints (need to re-extract in main process due to pickle)
                from .fingerprint import Fingerprinter
                fp = Fingerprinter()
                fingerprints = fp.extract_fingerprints(filepath)
                db.store_fingerprints(track_id, fingerprints)

                indexed += 1
                if args.verbose:
                    print(f"  {filename}: {fp_count} fingerprints")
            else:
                errors += 1
                if args.verbose:
                    print(f"  {filename}: ERROR - {error}")

            # Progress update
            total = indexed + errors
            if total % 10 == 0 or total == len(tracks):
                elapsed = time.time() - start_time
                rate = total / elapsed if elapsed > 0 else 0
                remaining = (len(tracks) - total) / rate if rate > 0 else 0
                print(
                    f"Progress: {total}/{len(tracks)} "
                    f"({indexed} ok, {errors} errors) "
                    f"- {rate:.1f}/sec "
                    f"- ETA: {remaining/60:.1f} min",
                    end="\r"
                )

    print()
    elapsed = time.time() - start_time
    print()
    print(f"Completed in {elapsed:.1f} seconds")
    print(f"  Indexed: {indexed}")
    print(f"  Errors: {errors}")

    return 0


def cmd_identify(args: argparse.Namespace) -> int:
    """Identify a single audio file."""
    from .database import FingerprintDB
    from .matcher import Matcher

    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        return 1

    db = FingerprintDB(args.db)
    matcher = Matcher(db, min_matches=args.min_matches)

    print(f"Identifying: {args.file}")
    print()

    start = time.time()
    matches = matcher.identify_track(args.file)
    elapsed = time.time() - start

    if not matches:
        print("No matches found.")
        return 0

    print(f"Found {len(matches)} match(es) in {elapsed:.1f}s:")
    print()

    for i, m in enumerate(matches[:args.top_n], 1):
        if m.artist and m.title:
            track_str = f"{m.artist} - {m.title}"
        elif m.title:
            track_str = m.title
        else:
            track_str = m.filename

        print(f"{i}. {track_str}")
        print(f"   Confidence: {m.confidence:.0%}")
        print(f"   Matches: {m.match_count}")
        if abs(m.time_stretch_ratio - 1.0) > 0.01:
            print(f"   Tempo change: {m.time_stretch_ratio:.2f}x")
        print()

    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    """Analyze a mix to identify all tracks."""
    from .database import FingerprintDB
    from .matcher import Matcher

    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        return 1

    db = FingerprintDB(args.db)
    matcher = Matcher(db, min_matches=args.min_matches, min_confidence=args.min_confidence)

    print(f"Analyzing mix: {args.file}")
    print(f"Segment duration: {args.segment}s, overlap: {args.overlap}s")
    print()

    start = time.time()
    matches = matcher.analyze_mix(
        args.file,
        segment_duration_sec=args.segment,
        overlap_sec=args.overlap,
    )
    elapsed = time.time() - start

    if not matches:
        print("No tracks identified.")
        return 0

    print(f"Analysis completed in {elapsed:.1f}s")
    print()

    # Generate and print cue sheet
    cues = matcher.generate_cue_sheet(matches)
    cue_text = matcher.format_cue_sheet(cues)
    print(cue_text)

    # Save to file if requested
    if args.output:
        with open(args.output, "w") as f:
            f.write(cue_text)
        print(f"Cue sheet saved to: {args.output}")

    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    """Clear all fingerprints."""
    if not args.force:
        confirm = input("This will delete ALL fingerprints. Are you sure? [y/N] ")
        if confirm.lower() != "y":
            print("Aborted.")
            return 1

    db = FingerprintDB(args.db)
    db.clear_all_fingerprints()
    print("All fingerprints cleared.")
    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="shazamix",
        description="Audio fingerprinting for DJ mix track identification",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to database (default: {DEFAULT_DB_PATH})",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # stats command
    stats_parser = subparsers.add_parser("stats", help="Show indexing statistics")
    stats_parser.set_defaults(func=cmd_stats)

    # index command
    index_parser = subparsers.add_parser("index", help="Index tracks from Jukebox")
    index_parser.add_argument(
        "--mode", "-m",
        choices=["jukebox", "curating"],
        help="Only index tracks in this mode",
    )
    index_parser.add_argument(
        "--limit", "-l",
        type=int,
        help="Limit to N tracks",
    )
    index_parser.add_argument(
        "--workers", "-w",
        type=int,
        default=max(1, os.cpu_count() - 1),
        help=f"Number of parallel workers (default: {max(1, os.cpu_count() - 1)})",
    )
    index_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed progress",
    )
    index_parser.set_defaults(func=cmd_index)

    # identify command
    identify_parser = subparsers.add_parser("identify", help="Identify a single audio file")
    identify_parser.add_argument("file", help="Audio file to identify")
    identify_parser.add_argument(
        "--top-n", "-n",
        type=int,
        default=5,
        help="Show top N matches (default: 5)",
    )
    identify_parser.add_argument(
        "--min-matches",
        type=int,
        default=5,
        help="Minimum matching fingerprints (default: 5)",
    )
    identify_parser.set_defaults(func=cmd_identify)

    # analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a mix file")
    analyze_parser.add_argument("file", help="Mix file to analyze")
    analyze_parser.add_argument(
        "--output", "-o",
        help="Save cue sheet to file",
    )
    analyze_parser.add_argument(
        "--segment", "-s",
        type=float,
        default=30.0,
        help="Segment duration in seconds (default: 30)",
    )
    analyze_parser.add_argument(
        "--overlap",
        type=float,
        default=15.0,
        help="Segment overlap in seconds (default: 15)",
    )
    analyze_parser.add_argument(
        "--min-matches",
        type=int,
        default=5,
        help="Minimum matching fingerprints (default: 5)",
    )
    analyze_parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.1,
        help="Minimum confidence to report (default: 0.1)",
    )
    analyze_parser.set_defaults(func=cmd_analyze)

    # clear command
    clear_parser = subparsers.add_parser("clear", help="Clear all fingerprints")
    clear_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Skip confirmation",
    )
    clear_parser.set_defaults(func=cmd_clear)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
