#!/usr/bin/env python3
"""Batch audio analysis script with multiprocessing.

This script performs the same audio analysis as the audio_analyzer plugin
but uses multiprocessing for faster processing of large music libraries.

Usage:
    uv run scripts/batch_audio_analysis.py [OPTIONS]

Options:
    --workers N     Number of parallel workers (default: CPU count - 1)
    --mode MODE     Only analyze tracks in this mode (jukebox/curating)
    --force         Re-analyze tracks that already have analysis
    --limit N       Limit to N tracks (for testing)
    --db PATH       Path to database (default: ~/.jukebox/jukebox.db)
    --verbose       Show detailed progress
"""

import argparse
import os
import sqlite3
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

# Suppress librosa warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

# Default database path
DEFAULT_DB_PATH = Path.home() / ".jukebox" / "jukebox.db"

# Columns to save (must match database schema)
AUDIO_ANALYSIS_COLUMNS = frozenset([
    "tempo", "rms_energy", "spectral_centroid", "zero_crossing_rate",
    "rms_mean", "rms_std", "rms_p10", "rms_p90", "peak_amplitude",
    "crest_factor", "loudness_variation",
    "sub_bass_mean", "sub_bass_ratio", "bass_mean", "bass_ratio",
    "low_mid_mean", "low_mid_ratio", "mid_mean", "mid_ratio",
    "high_mid_mean", "high_mid_ratio", "high_mean", "high_ratio",
    "spectral_centroid_std", "spectral_bandwidth", "spectral_rolloff",
    "spectral_flatness", "spectral_contrast", "spectral_entropy",
    "mfcc_1", "mfcc_2", "mfcc_3", "mfcc_4", "mfcc_5",
    "mfcc_6", "mfcc_7", "mfcc_8", "mfcc_9", "mfcc_10",
    "harmonic_energy", "percussive_energy", "perc_harm_ratio",
    "onset_strength_mean", "percussive_onset_rate",
    "tempo_confidence", "beat_interval_mean", "beat_interval_std",
    "onset_rate", "tempogram_periodicity",
    "chroma_entropy", "chroma_centroid", "chroma_energy_std", "tonnetz_mean",
    "intro_energy_ratio", "core_energy_ratio", "outro_energy_ratio", "energy_slope",
    "dynamic_range",
])


def analyze_audio_file(filepath: str) -> dict[str, float]:
    """Analyze audio file and extract ML features.

    This is the same analysis as the audio_analyzer plugin.

    Args:
        filepath: Path to audio file

    Returns:
        Dict with ML features

    Raises:
        Exception: If analysis fails
    """
    import librosa

    # Load audio
    y, sr = librosa.load(filepath, sr=None, mono=True)

    if len(y) == 0:
        raise ValueError("Empty audio file")

    features: dict[str, float] = {}

    # Core stats: tempo, brightness (spectral_centroid), percussive (zcr), RMS
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    features["tempo"] = float(tempo) if tempo else 0.0

    rms = librosa.feature.rms(y=y)[0]
    features["rms_energy"] = float(np.mean(rms))

    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    features["spectral_centroid"] = float(np.mean(centroid))

    zcr = librosa.feature.zero_crossing_rate(y)[0]
    features["zero_crossing_rate"] = float(np.mean(zcr))

    # 1. Energy & dynamics (8 features)
    features["rms_mean"] = float(np.mean(rms))
    features["rms_std"] = float(np.std(rms))
    features["rms_p10"] = float(np.percentile(rms, 10))
    features["rms_p90"] = float(np.percentile(rms, 90))
    features["peak_amplitude"] = float(np.max(np.abs(y)))
    features["crest_factor"] = float(features["peak_amplitude"] / (features["rms_mean"] + 1e-10))
    features["loudness_variation"] = float(np.std(rms))

    # Dynamic range (from RMS)
    rms_db = librosa.amplitude_to_db(rms + 1e-10)
    features["dynamic_range"] = float(np.percentile(rms_db, 95) - np.percentile(rms_db, 5))

    # 2. Frequency band energies (12 features)
    stft = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)

    def band_energy(stft_mat: np.ndarray, freqs: np.ndarray, f_min: float, f_max: float) -> tuple[float, float]:
        mask = (freqs >= f_min) & (freqs < f_max)
        band = stft_mat[mask, :]
        band_mean = float(np.mean(band))
        total_energy = float(np.mean(stft_mat))
        ratio = band_mean / (total_energy + 1e-10)
        return band_mean, ratio

    features["sub_bass_mean"], features["sub_bass_ratio"] = band_energy(stft, freqs, 20, 60)
    features["bass_mean"], features["bass_ratio"] = band_energy(stft, freqs, 60, 150)
    features["low_mid_mean"], features["low_mid_ratio"] = band_energy(stft, freqs, 150, 500)
    features["mid_mean"], features["mid_ratio"] = band_energy(stft, freqs, 500, 2000)
    features["high_mid_mean"], features["high_mid_ratio"] = band_energy(stft, freqs, 2000, 6000)
    features["high_mean"], features["high_ratio"] = band_energy(stft, freqs, 6000, 20000)

    # 3. Spectral features (6 features)
    features["spectral_centroid_std"] = float(np.std(centroid))
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
    features["spectral_bandwidth"] = float(np.mean(bandwidth))
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
    features["spectral_rolloff"] = float(np.mean(rolloff))
    flatness = librosa.feature.spectral_flatness(y=y)[0]
    features["spectral_flatness"] = float(np.mean(flatness))
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
    features["spectral_contrast"] = float(np.mean(contrast))
    spec_norm = stft / (np.sum(stft, axis=0, keepdims=True) + 1e-10)
    spec_entropy = -np.sum(spec_norm * np.log(spec_norm + 1e-10), axis=0)
    features["spectral_entropy"] = float(np.mean(spec_entropy))

    # 4. MFCC (10 coefficients)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=10)
    for i in range(10):
        features[f"mfcc_{i+1}"] = float(np.mean(mfcc[i, :]))

    # 5. Percussive vs harmonic (5 features)
    y_harmonic, y_percussive = librosa.effects.hpss(y)
    features["harmonic_energy"] = float(np.mean(librosa.feature.rms(y=y_harmonic)[0]))
    features["percussive_energy"] = float(np.mean(librosa.feature.rms(y=y_percussive)[0]))
    features["perc_harm_ratio"] = features["percussive_energy"] / (features["harmonic_energy"] + 1e-10)

    onset_env = librosa.onset.onset_strength(y=y_percussive, sr=sr)
    features["onset_strength_mean"] = float(np.mean(onset_env))
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)
    duration = len(y) / sr
    features["percussive_onset_rate"] = len(onsets) / duration if duration > 0 else 0.0

    # 6. Rhythm & tempo (5 additional features)
    features["tempo_confidence"] = 1.0
    if len(beats) > 1:
        beat_times = librosa.frames_to_time(beats, sr=sr)
        beat_intervals = np.diff(beat_times)
        features["beat_interval_mean"] = float(np.mean(beat_intervals))
        features["beat_interval_std"] = float(np.std(beat_intervals))
    else:
        features["beat_interval_mean"] = 0.0
        features["beat_interval_std"] = 0.0

    all_onsets = librosa.onset.onset_detect(y=y, sr=sr)
    features["onset_rate"] = len(all_onsets) / duration if duration > 0 else 0.0

    tempogram = librosa.feature.tempogram(onset_envelope=onset_env, sr=sr)
    features["tempogram_periodicity"] = float(np.mean(tempogram))

    # 7. Harmony (4 features)
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    chroma_norm = chroma / (np.sum(chroma, axis=0, keepdims=True) + 1e-10)
    chroma_entropy = -np.sum(chroma_norm * np.log(chroma_norm + 1e-10), axis=0)
    features["chroma_entropy"] = float(np.mean(chroma_entropy))
    features["chroma_centroid"] = float(np.mean(np.argmax(chroma, axis=0)))
    features["chroma_energy_std"] = float(np.std(np.sum(chroma, axis=0)))

    tonnetz = librosa.feature.tonnetz(y=y_harmonic, sr=sr)
    features["tonnetz_mean"] = float(np.mean(tonnetz))

    # 8. Structure (4 features)
    n_samples = len(y)
    intro_end = int(n_samples * 0.2)
    core_start = intro_end
    core_end = int(n_samples * 0.8)
    outro_start = core_end

    intro_energy = float(np.mean(np.abs(y[:intro_end])))
    core_energy = float(np.mean(np.abs(y[core_start:core_end])))
    outro_energy = float(np.mean(np.abs(y[outro_start:])))
    total_energy = float(np.mean(np.abs(y)))

    features["intro_energy_ratio"] = intro_energy / (total_energy + 1e-10)
    features["core_energy_ratio"] = core_energy / (total_energy + 1e-10)
    features["outro_energy_ratio"] = outro_energy / (total_energy + 1e-10)

    time_indices = np.arange(len(rms))
    slope, _ = np.polyfit(time_indices, rms, 1)
    features["energy_slope"] = float(slope)

    return features


def process_track(args: tuple[int, str]) -> tuple[int, str, dict[str, float] | None, str | None]:
    """Process a single track (worker function for multiprocessing).

    Args:
        args: Tuple of (track_id, filepath)

    Returns:
        Tuple of (track_id, filepath, features_dict or None, error_message or None)
    """
    track_id, filepath = args
    try:
        features = analyze_audio_file(filepath)
        return (track_id, filepath, features, None)
    except Exception as e:
        return (track_id, filepath, None, str(e))


def get_tracks_to_analyze(
    db_path: Path,
    mode: str | None = None,
    force: bool = False,
    limit: int | None = None,
) -> list[tuple[int, str]]:
    """Get list of tracks that need analysis.

    Args:
        db_path: Path to database
        mode: Filter by mode (optional)
        force: If True, include tracks that already have analysis
        limit: Maximum number of tracks to return

    Returns:
        List of (track_id, filepath) tuples
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if force:
        # Get all tracks
        query = "SELECT id, filepath FROM tracks"
        params: list = []
        if mode:
            query += " WHERE mode = ?"
            params.append(mode)
        if limit:
            query += f" LIMIT {limit}"
        rows = conn.execute(query, params).fetchall()
    else:
        # Get tracks without complete analysis
        query = """
            SELECT t.id, t.filepath
            FROM tracks t
            LEFT JOIN audio_analysis a ON t.id = a.track_id
            WHERE a.track_id IS NULL
               OR a.tempo IS NULL
               OR a.rms_mean IS NULL
               OR a.spectral_centroid IS NULL
        """
        params = []
        if mode:
            query += " AND t.mode = ?"
            params.append(mode)
        if limit:
            query += f" LIMIT {limit}"
        rows = conn.execute(query, params).fetchall()

    conn.close()
    return [(row["id"], row["filepath"]) for row in rows]


def save_analysis(db_path: Path, track_id: int, features: dict[str, float]) -> None:
    """Save analysis results to database.

    Args:
        db_path: Path to database
        track_id: Track ID
        features: Analysis features dict
    """
    conn = sqlite3.connect(db_path)

    # Filter to valid columns
    safe_features = {k: v for k, v in features.items() if k in AUDIO_ANALYSIS_COLUMNS}

    # Build upsert query
    columns = list(safe_features.keys())
    placeholders = ", ".join(["?"] * len(columns))
    column_names = ", ".join(columns)
    update_set = ", ".join([f"{col} = excluded.{col}" for col in columns])

    query = f"""
        INSERT INTO audio_analysis (track_id, {column_names})
        VALUES (?, {placeholders})
        ON CONFLICT(track_id) DO UPDATE SET {update_set}
    """

    values = [track_id] + [safe_features[col] for col in columns]
    conn.execute(query, values)
    conn.commit()
    conn.close()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Batch audio analysis with multiprocessing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=max(1, os.cpu_count() - 1),
        help=f"Number of parallel workers (default: {max(1, os.cpu_count() - 1)})",
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["jukebox", "curating"],
        help="Only analyze tracks in this mode",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Re-analyze tracks that already have analysis",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        help="Limit to N tracks (for testing)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed progress",
    )

    args = parser.parse_args()

    if not args.db.exists():
        print(f"Error: Database not found: {args.db}", file=sys.stderr)
        return 1

    # Get tracks to analyze
    print(f"Scanning database for tracks to analyze...")
    tracks = get_tracks_to_analyze(args.db, args.mode, args.force, args.limit)

    if not tracks:
        print("No tracks need analysis.")
        return 0

    print(f"Found {len(tracks)} tracks to analyze")
    print(f"Using {args.workers} parallel workers")
    print()

    # Process tracks with multiprocessing
    start_time = time.time()
    completed = 0
    errors = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        # Submit all tasks
        futures = {executor.submit(process_track, track): track for track in tracks}

        # Process results as they complete
        for future in as_completed(futures):
            track_id, filepath, features, error = future.result()
            filename = os.path.basename(filepath)

            if features:
                # Save to database
                save_analysis(args.db, track_id, features)
                completed += 1
                if args.verbose:
                    print(f"✓ {filename}")
            else:
                errors += 1
                if args.verbose:
                    print(f"✗ {filename}: {error}")

            # Progress update
            total = completed + errors
            if total % 10 == 0 or total == len(tracks):
                elapsed = time.time() - start_time
                rate = total / elapsed if elapsed > 0 else 0
                remaining = (len(tracks) - total) / rate if rate > 0 else 0
                print(
                    f"Progress: {total}/{len(tracks)} "
                    f"({completed} ok, {errors} errors) "
                    f"- {rate:.1f} tracks/sec "
                    f"- ETA: {remaining/60:.1f} min",
                    end="\r",
                )

    print()  # New line after progress
    elapsed = time.time() - start_time

    print()
    print(f"Completed in {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
    print(f"  Analyzed: {completed}")
    print(f"  Errors: {errors}")
    print(f"  Rate: {len(tracks)/elapsed:.2f} tracks/second")

    return 0


if __name__ == "__main__":
    sys.exit(main())
