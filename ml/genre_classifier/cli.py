#!/usr/bin/env python3
"""Command-line interface for genre classifier."""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from .data_loader import DEFAULT_DB_PATH, get_dataset_stats, load_track_features
from .models import MODEL_REGISTRY
from .trainer import GenreClassifierTrainer, TrainedModel, train_best_model


def cmd_stats(args: argparse.Namespace) -> int:
    """Show dataset statistics."""
    try:
        stats = get_dataset_stats(args.database)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print("=== Dataset Statistics ===")
    print(f"Total tracks: {stats['total_tracks']}")
    print(f"Tracks with genre: {stats['tracks_with_genre']}")
    print(f"Tracks with basic analysis: {stats['tracks_with_analysis']}")
    print(f"Tracks with ML features: {stats['tracks_with_ml_features']}")
    missing_ml = stats['tracks_with_analysis'] - stats['tracks_with_ml_features']
    if missing_ml > 0:
        print(f"  → {missing_ml} tracks need ML analysis (run: analyze)")
    print(f"Usable for training: {stats['usable_for_training']}")
    print(f"Unique genres: {stats['unique_genres']}")
    print(f"Excluded genres: {', '.join(stats['excluded_genres'])}")
    print()
    print("Genre distribution (multi-label, tracks can have multiple genres):")
    for genre, count in stats["genre_distribution"].items():
        print(f"  {genre}: {count}")

    return 0


def cmd_train(args: argparse.Namespace) -> int:
    """Train a genre classifier."""
    print(f"Training {args.model} model...")

    try:
        model, result = train_best_model(
            db_path=args.database,
            model_name=args.model,
            save_path=args.output,
            min_samples_per_genre=args.min_samples,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if result.feature_importance is not None and args.show_features:
        print("\nTop 20 Important Features:")
        print(result.feature_importance.head(20).to_string(index=False))

    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Compare all available models."""
    print("Comparing all models...")

    trainer = GenreClassifierTrainer()

    try:
        n_samples, n_features, n_genres = trainer.load_data(
            db_path=args.database,
            min_samples_per_genre=args.min_samples,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Data: {n_samples} samples, {n_features} features, {n_genres} genres")
    print(f"Genres: {', '.join(trainer.genres)}")
    print()

    comparison = trainer.compare_models()

    print("\n=== Model Comparison ===")
    print(comparison.to_string(index=False))

    return 0


def cmd_predict(args: argparse.Namespace) -> int:
    """Predict genre for a track."""
    try:
        model = TrainedModel.load(args.model_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    try:
        features = load_track_features(args.track_id, args.database)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if features is None:
        print(f"Error: No audio analysis found for track {args.track_id}")
        return 1

    if args.top_n:
        predictions = model.predict_top_n(features, n=args.top_n)
        print(f"Top {args.top_n} genre predictions for track {args.track_id}:")
        for genre, prob in predictions:
            marker = "●" if prob >= args.threshold else "○"
            print(f"  {marker} {genre}: {prob:.2%}")
    else:
        genres = model.predict(features, threshold=args.threshold)
        proba = model.predict_proba(features)
        if genres:
            print(f"Predicted genres for track {args.track_id}: {', '.join(sorted(genres))}")
            print("Probabilities:")
            for g in sorted(genres):
                print(f"  {g}: {proba[g]:.2%}")
        else:
            print(f"No genres predicted above threshold ({args.threshold:.0%})")
            print("Top probabilities:")
            for genre, prob in sorted(proba.items(), key=lambda x: -x[1])[:3]:
                print(f"  {genre}: {prob:.2%}")

    return 0


def cmd_info(args: argparse.Namespace) -> int:
    """Show information about a saved model."""
    try:
        model = TrainedModel.load(args.model_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print("=== Model Information ===")
    print(f"Model type: {model.metadata.get('model_name', 'unknown')}")
    print(f"Trained at: {model.metadata.get('trained_at', 'unknown')}")
    print(f"Samples: {model.metadata.get('n_samples', 'unknown')}")
    print(f"Features: {model.metadata.get('n_features', 'unknown')}")
    print(f"Genres: {model.metadata.get('n_genres', 'unknown')}")
    print()
    print("Genre labels:")
    for genre in model.metadata.get("genres", []):
        print(f"  - {genre}")
    print()
    print("Metrics (multi-label):")
    metrics = model.metadata.get("metrics", {})
    print(f"  Hamming Loss: {metrics.get('hamming_loss', 0):.4f} (lower is better)")
    print(f"  Subset Accuracy: {metrics.get('subset_accuracy', 0):.4f} (exact match)")
    print(f"  F1 (micro): {metrics.get('f1_micro', 0):.4f}")
    print(f"  F1 (macro): {metrics.get('f1_macro', 0):.4f}")
    print(f"  F1 (samples): {metrics.get('f1_samples', 0):.4f}")
    print()
    print("Model parameters:")
    for key, value in model.metadata.get("model_params", {}).items():
        print(f"  {key}: {value}")

    return 0



def _analyze_track(args: tuple[int, str]) -> tuple[int, str, dict | None, str | None]:
    """Analyze a single track (worker function for multiprocessing).

    Args:
        args: Tuple of (track_id, filepath)

    Returns:
        Tuple of (track_id, filepath, features_dict or None, error_message or None)
    """
    from plugins.audio_analyzer import analyze_audio_file

    track_id, filepath = args
    try:
        features = analyze_audio_file(filepath, extract_ml_features=True)
        return (track_id, filepath, features, None)
    except Exception as e:
        return (track_id, filepath, None, str(e))


def _save_analysis(db_path: Path, track_id: int, features: dict) -> None:
    """Save analysis results to database.

    Args:
        db_path: Path to database
        track_id: Track ID
        features: Analysis features dict
    """
    conn = sqlite3.connect(db_path)

    columns = list(features.keys())
    placeholders = ", ".join(["?"] * (len(columns) + 1))
    col_names = ", ".join(["track_id"] + columns)
    values = [track_id] + list(features.values())

    conn.execute(f"""
        INSERT OR REPLACE INTO audio_analysis ({col_names})
        VALUES ({placeholders})
    """, values)
    conn.commit()
    conn.close()

def cmd_analyze(args: argparse.Namespace) -> int:
    """Analyze tracks that don't have audio analysis yet."""
    import time
    from concurrent.futures import ProcessPoolExecutor, as_completed

    db_path = args.database
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get tracks without analysis
    params: list = []
    if args.force:
        # Re-analyze all tracks
        query = "SELECT id, filepath FROM tracks"
        if args.mode:
            query += " WHERE mode = ?"
            params.append(args.mode)
        if args.limit:
            query += f" LIMIT {args.limit}"
        cursor = conn.execute(query, params)
    else:
        # Only tracks without ML features
        query = """
            SELECT t.id, t.filepath
            FROM tracks t
            LEFT JOIN audio_analysis a ON t.id = a.track_id
            WHERE (a.track_id IS NULL OR a.rms_mean IS NULL)
        """
        if args.mode:
            query += " AND t.mode = ?"
            params.append(args.mode)
        if args.limit:
            query += f" LIMIT {args.limit}"
        cursor = conn.execute(query, params)

    tracks = [(row["id"], row["filepath"]) for row in cursor.fetchall()]
    conn.close()

    total = len(tracks)
    if total == 0:
        print("All tracks are already analyzed.")
        return 0

    # Filter out missing files
    valid_tracks = []
    for track_id, filepath in tracks:
        if Path(filepath).exists():
            valid_tracks.append((track_id, filepath))
        elif args.verbose:
            print(f"SKIP (file not found): {filepath}")

    if not valid_tracks:
        print("No valid tracks to analyze (files not found).")
        return 1

    print(f"Analyzing {len(valid_tracks)} tracks with {args.workers} workers...")
    start_time = time.time()
    success = 0
    errors = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(_analyze_track, track): track
            for track in valid_tracks
        }

        # Process results as they complete
        for future in as_completed(futures):
            track_id, filepath, features, error = future.result()
            filename = Path(filepath).name

            if features:
                # Save to database
                _save_analysis(db_path, track_id, features)
                success += 1
                if args.verbose:
                    print(f"✓ {filename}")
            else:
                errors += 1
                if args.verbose:
                    print(f"✗ {filename}: {error}")

            # Progress update
            processed = success + errors
            if processed % 10 == 0 or processed == len(valid_tracks):
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = (len(valid_tracks) - processed) / rate if rate > 0 else 0
                print(
                    f"Progress: {processed}/{len(valid_tracks)} "
                    f"({success} ok, {errors} errors) "
                    f"- {rate:.1f} tracks/sec "
                    f"- ETA: {remaining/60:.1f} min",
                    end="\r",
                )

    print()  # New line after progress
    elapsed = time.time() - start_time

    print()
    print(f"Completed in {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
    print(f"  Analyzed: {success}")
    print(f"  Errors: {errors}")
    if elapsed > 0:
        print(f"  Rate: {len(valid_tracks)/elapsed:.2f} tracks/second")

    return 0 if errors == 0 else 1


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Genre Classifier - ML-based music genre classification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--database",
        "-d",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to Jukebox database (default: {DEFAULT_DB_PATH})",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # stats command
    stats_parser = subparsers.add_parser("stats", help="Show dataset statistics")
    stats_parser.set_defaults(func=cmd_stats)

    # train command
    train_parser = subparsers.add_parser("train", help="Train a genre classifier")
    train_parser.add_argument(
        "--model",
        "-m",
        choices=list(MODEL_REGISTRY.keys()),
        default="random_forest",
        help="Model type to train (default: random_forest)",
    )
    train_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Path to save trained model",
    )
    train_parser.add_argument(
        "--min-samples",
        type=int,
        default=5,
        help="Minimum samples per genre (default: 5)",
    )
    train_parser.add_argument(
        "--show-features",
        action="store_true",
        help="Show feature importance after training",
    )
    train_parser.set_defaults(func=cmd_train)

    # compare command
    compare_parser = subparsers.add_parser("compare", help="Compare all models")
    compare_parser.add_argument(
        "--min-samples",
        type=int,
        default=5,
        help="Minimum samples per genre (default: 5)",
    )
    compare_parser.set_defaults(func=cmd_compare)

    # predict command
    predict_parser = subparsers.add_parser("predict", help="Predict genre for a track")
    predict_parser.add_argument(
        "model_path",
        type=Path,
        help="Path to trained model file",
    )
    predict_parser.add_argument(
        "track_id",
        type=int,
        help="Track ID to predict genre for",
    )
    predict_parser.add_argument(
        "--top-n",
        "-n",
        type=int,
        help="Show top N predictions with probabilities",
    )
    predict_parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=0.5,
        help="Probability threshold for prediction (default: 0.5)",
    )
    predict_parser.set_defaults(func=cmd_predict)

    # info command
    info_parser = subparsers.add_parser("info", help="Show model information")
    info_parser.add_argument(
        "model_path",
        type=Path,
        help="Path to trained model file",
    )
    info_parser.set_defaults(func=cmd_info)

    # analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze tracks (extract ML features)")
    analyze_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Re-analyze all tracks (even already analyzed)",
    )
    analyze_parser.add_argument(
        "--mode",
        "-m",
        choices=["jukebox", "curating"],
        help="Only analyze tracks in this mode",
    )
    analyze_parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=max(1, (os.cpu_count() or 4) - 1),
        help=f"Number of parallel workers (default: {max(1, (os.cpu_count() or 4) - 1)})",
    )
    analyze_parser.add_argument(
        "--limit",
        "-l",
        type=int,
        help="Limit to N tracks (for testing)",
    )
    analyze_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed progress for each track",
    )
    analyze_parser.set_defaults(func=cmd_analyze)

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
