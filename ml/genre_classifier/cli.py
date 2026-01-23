#!/usr/bin/env python3
"""Command-line interface for genre classifier."""

import argparse
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
    print(f"Tracks with analysis: {stats['tracks_with_analysis']}")
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

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
