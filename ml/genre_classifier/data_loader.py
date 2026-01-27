"""Data loader for extracting training data from Jukebox database."""

import re
import sqlite3
from pathlib import Path

import pandas as pd


# Default database path
DEFAULT_DB_PATH = Path.home() / ".jukebox" / "jukebox.db"

# Genres to exclude from training (personal/subjective tags that can't be learned from audio)
EXCLUDED_GENRES = {"C", "R", "L"}

# All ML feature columns from audio_analysis table
ML_FEATURE_COLUMNS = [
    # Base analysis features
    "tempo",
    "energy",
    "bass_energy",
    "mid_energy",
    "treble_energy",
    "spectral_centroid",
    "zero_crossing_rate",
    "rms_energy",
    "dynamic_range",
    # Energy & dynamics
    "rms_mean",
    "rms_std",
    "rms_p10",
    "rms_p90",
    "peak_amplitude",
    "crest_factor",
    "loudness_variation",
    # Frequency band energies
    "sub_bass_mean",
    "sub_bass_ratio",
    "bass_mean",
    "bass_ratio",
    "low_mid_mean",
    "low_mid_ratio",
    "mid_mean",
    "mid_ratio",
    "high_mid_mean",
    "high_mid_ratio",
    "high_mean",
    "high_ratio",
    # Spectral features
    "spectral_centroid_std",
    "spectral_bandwidth",
    "spectral_rolloff",
    "spectral_flatness",
    "spectral_contrast",
    "spectral_entropy",
    # MFCC
    "mfcc_1",
    "mfcc_2",
    "mfcc_3",
    "mfcc_4",
    "mfcc_5",
    "mfcc_6",
    "mfcc_7",
    "mfcc_8",
    "mfcc_9",
    "mfcc_10",
    # Percussive vs harmonic
    "percussive_energy",
    "harmonic_energy",
    "perc_harm_ratio",
    "percussive_onset_rate",
    "onset_strength_mean",
    # Rhythm & tempo
    "tempo_confidence",
    "beat_interval_mean",
    "beat_interval_std",
    "onset_rate",
    "tempogram_periodicity",
    # Harmony
    "chroma_entropy",
    "chroma_centroid",
    "chroma_energy_std",
    "tonnetz_mean",
    # Structure
    "intro_energy_ratio",
    "core_energy_ratio",
    "outro_energy_ratio",
    "energy_slope",
]


def parse_genres(
    genre_str: str | None,
    exclude: set[str] | None = None,
) -> set[str]:
    """Parse genre string into a set of individual genres.

    The genre format uses:
    - Letters/words for genre names (e.g., "H", "Rock", "Jazz")
    - Hyphens (-) as separators between genres
    - Digits and stars (★, ☆, *) are ignored (ratings)

    Examples:
        "H-L-W 3★" -> {"H", "W"} (with default exclusions)
        "Rock-Jazz 4★" -> {"Rock", "Jazz"}
        "Electronic" -> {"Electronic"}

    Args:
        genre_str: Raw genre string from database
        exclude: Set of genres to exclude (defaults to EXCLUDED_GENRES)

    Returns:
        Set of genre strings (empty set if invalid)
    """
    if not genre_str or not isinstance(genre_str, str):
        return set()

    if exclude is None:
        exclude = EXCLUDED_GENRES

    # Remove digits, stars, and extra whitespace
    cleaned = re.sub(r"[0-9★☆*]", "", genre_str)

    # Split by hyphens and clean each part
    parts = [p.strip() for p in cleaned.split("-")]

    # Filter out empty strings and excluded genres
    genres = {p for p in parts if p and p not in exclude}

    return genres


def extract_genre_letter(genre_str: str | None, exclude: set[str] | None = None) -> str | None:
    """Extract the genre letter(s) from a genre string (legacy single-label).

    Kept for backward compatibility. For multi-label, use parse_genres().

    Args:
        genre_str: Raw genre string from database
        exclude: Set of genres to exclude (defaults to EXCLUDED_GENRES)

    Returns:
        First genre found or None if invalid
    """
    genres = parse_genres(genre_str, exclude=exclude)
    return next(iter(sorted(genres)), None) if genres else None


def load_training_data(
    db_path: Path | str = DEFAULT_DB_PATH,
    min_samples_per_genre: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Load training data from Jukebox database (multi-label).

    Joins tracks with audio_analysis to get features and genre labels.
    Only includes tracks that have both a valid genre and audio analysis.

    Args:
        db_path: Path to the Jukebox SQLite database
        min_samples_per_genre: Minimum samples required per genre to include it

    Returns:
        Tuple of (features DataFrame, labels DataFrame (binary), list of genre names)
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Build feature columns string
    feature_cols = ", ".join(f"a.{col}" for col in ML_FEATURE_COLUMNS)

    query = f"""
        SELECT
            t.id as track_id,
            t.title,
            t.artist,
            t.genre,
            {feature_cols}
        FROM tracks t
        INNER JOIN audio_analysis a ON t.id = a.track_id
        WHERE t.genre IS NOT NULL AND t.genre != ''
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        raise ValueError("No tracks with both genre and audio analysis found")

    # Parse genres into sets
    df["genres_set"] = df["genre"].apply(parse_genres)

    # Remove rows with no valid genres
    df = df[df["genres_set"].apply(len) > 0]

    if df.empty:
        raise ValueError("No tracks with valid genres found")

    # Count occurrences of each genre
    genre_counts: dict[str, int] = {}
    for genres in df["genres_set"]:
        for g in genres:
            genre_counts[g] = genre_counts.get(g, 0) + 1

    # Filter to genres with sufficient samples
    valid_genres = sorted([g for g, count in genre_counts.items()
                          if count >= min_samples_per_genre])

    if not valid_genres:
        raise ValueError(
            f"No genres with at least {min_samples_per_genre} samples found"
        )

    # Create binary label matrix
    labels_data = []
    valid_indices = []
    for idx, genres in df["genres_set"].items():
        # Keep only valid genres for this track
        track_genres = genres & set(valid_genres)
        if track_genres:  # Only keep tracks with at least one valid genre
            row = {g: 1 if g in track_genres else 0 for g in valid_genres}
            labels_data.append(row)
            valid_indices.append(idx)

    if not labels_data:
        raise ValueError("No tracks remaining after filtering")

    # Filter dataframe to valid indices
    df = df.loc[valid_indices]

    # Create labels DataFrame
    labels = pd.DataFrame(labels_data, index=valid_indices)

    # Separate features
    features = df[ML_FEATURE_COLUMNS].copy()

    return features, labels, valid_genres


def load_track_features(
    track_id: int,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> pd.DataFrame | None:
    """Load features for a single track.

    Args:
        track_id: ID of the track to load
        db_path: Path to the Jukebox SQLite database

    Returns:
        DataFrame with features for the track, or None if not found
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)

    feature_cols = ", ".join(ML_FEATURE_COLUMNS)
    query = f"""
        SELECT {feature_cols}
        FROM audio_analysis
        WHERE track_id = ?
    """

    df = pd.read_sql_query(query, conn, params=(track_id,))
    conn.close()

    return df if not df.empty else None


def get_dataset_stats(db_path: Path | str = DEFAULT_DB_PATH) -> dict:
    """Get statistics about the available training data.

    Args:
        db_path: Path to the Jukebox SQLite database

    Returns:
        Dictionary with dataset statistics
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Total tracks
    total_tracks = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]

    # Tracks with genre
    tracks_with_genre = conn.execute(
        "SELECT COUNT(*) FROM tracks WHERE genre IS NOT NULL AND genre != ''"
    ).fetchone()[0]

    # Tracks with basic analysis (any entry in audio_analysis)
    tracks_with_analysis = conn.execute(
        "SELECT COUNT(*) FROM audio_analysis"
    ).fetchone()[0]

    # Tracks with ML features (rms_mean is not null)
    tracks_with_ml_features = conn.execute(
        "SELECT COUNT(*) FROM audio_analysis WHERE rms_mean IS NOT NULL"
    ).fetchone()[0]

    # Tracks with both genre and ML features (usable for training)
    usable_tracks = conn.execute("""
        SELECT COUNT(*)
        FROM tracks t
        INNER JOIN audio_analysis a ON t.id = a.track_id
        WHERE t.genre IS NOT NULL AND t.genre != ''
        AND a.rms_mean IS NOT NULL
    """).fetchone()[0]

    # Genre distribution (multi-label aware)
    genre_query = """
        SELECT t.genre
        FROM tracks t
        INNER JOIN audio_analysis a ON t.id = a.track_id
        WHERE t.genre IS NOT NULL AND t.genre != ''
        AND a.rms_mean IS NOT NULL
    """
    genre_dist: dict[str, int] = {}
    for row in conn.execute(genre_query):
        genres = parse_genres(row["genre"])
        for g in genres:
            genre_dist[g] = genre_dist.get(g, 0) + 1

    conn.close()

    return {
        "total_tracks": total_tracks,
        "tracks_with_genre": tracks_with_genre,
        "tracks_with_analysis": tracks_with_analysis,
        "tracks_with_ml_features": tracks_with_ml_features,
        "usable_for_training": usable_tracks,
        "genre_distribution": dict(sorted(genre_dist.items(), key=lambda x: -x[1])),
        "unique_genres": len(genre_dist),
        "excluded_genres": sorted(EXCLUDED_GENRES),
    }
