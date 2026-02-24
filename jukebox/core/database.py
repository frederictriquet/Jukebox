"""SQLite database manager with FTS5 support."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jukebox.core.repositories import (
        AnalysisRepository,
        PluginSettingsRepository,
        TrackRepository,
        WaveformRepository,
    )


def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict[str, Any]:
    """Row factory that returns dicts instead of sqlite3.Row."""
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


class Database:
    """SQLite database manager with FTS5 support.

    Provides access to specialized repositories for database operations:
        - tracks: TrackRepository for track operations
        - waveforms: WaveformRepository for waveform cache
        - analysis: AnalysisRepository for audio analysis
        - settings: PluginSettingsRepository for plugin settings

    Legacy methods are preserved for backward compatibility but delegate
    to the repositories internally.
    """

    def __init__(self, db_path: Path):
        """Initialize database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None
        self._in_transaction: bool = False
        # Repositories (lazy initialized after connect)
        self._tracks: TrackRepository | None = None
        self._waveforms: WaveformRepository | None = None
        self._analysis: AnalysisRepository | None = None
        self._settings: PluginSettingsRepository | None = None

    def connect(self) -> None:
        """Connect to database and enable foreign keys."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = _dict_factory
        self.conn.execute("PRAGMA foreign_keys = ON")

    # ========== Repository Properties ==========

    @property
    def tracks(self) -> TrackRepository:
        """Get the track repository."""
        if self._tracks is None:
            from jukebox.core.repositories import TrackRepository

            self._tracks = TrackRepository(self)
        return self._tracks

    @property
    def waveforms(self) -> WaveformRepository:
        """Get the waveform repository."""
        if self._waveforms is None:
            from jukebox.core.repositories import WaveformRepository

            self._waveforms = WaveformRepository(self)
        return self._waveforms

    @property
    def analysis(self) -> AnalysisRepository:
        """Get the analysis repository."""
        if self._analysis is None:
            from jukebox.core.repositories import AnalysisRepository

            self._analysis = AnalysisRepository(self)
        return self._analysis

    @property
    def settings(self) -> PluginSettingsRepository:
        """Get the plugin settings repository."""
        if self._settings is None:
            from jukebox.core.repositories import PluginSettingsRepository

            self._settings = PluginSettingsRepository(self)
        return self._settings

    # ========== Transaction Management ==========

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Context manager for database transactions.

        Provides atomic operations with automatic commit on success
        or rollback on failure. Repository methods will skip their
        individual commits while inside a transaction.

        Usage:
            with database.transaction():
                database.tracks.add(track1)
                database.tracks.add(track2)
                database.waveforms.save(track_id, data)
            # All operations committed, or all rolled back on error

        Raises:
            RuntimeError: If database not connected
        """
        if self.conn is None:
            raise RuntimeError("Database not connected")

        self._in_transaction = True
        try:
            # SQLite auto-commits by default, so we start a transaction explicitly
            self.conn.execute("BEGIN")
            yield
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            self._in_transaction = False

    # ========== Schema Management ==========

    def initialize_schema(self) -> None:
        """Create database schema."""
        if self.conn is None:
            raise RuntimeError("Database not connected")

        # Tracks table
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filepath TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                title TEXT,
                artist TEXT,
                album TEXT,
                album_artist TEXT,
                genre TEXT,
                year INTEGER,
                track_number INTEGER,
                duration_seconds REAL,
                bitrate INTEGER,
                sample_rate INTEGER,
                file_size INTEGER,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_modified TIMESTAMP,
                play_count INTEGER DEFAULT 0,
                last_played TIMESTAMP
            )
        """
        )

        # FTS5 search index
        self.conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS tracks_fts USING fts5(
                title, artist, album, album_artist, filename, genre,
                content=tracks,
                content_rowid=id
            )
        """
        )

        # Triggers to keep FTS5 in sync
        self.conn.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS tracks_ai AFTER INSERT ON tracks BEGIN
                INSERT INTO tracks_fts(rowid, title, artist, album, album_artist, filename, genre)
                VALUES (new.id, new.title, new.artist, new.album, new.album_artist, new.filename, new.genre);
            END;

            CREATE TRIGGER IF NOT EXISTS tracks_ad AFTER DELETE ON tracks BEGIN
                INSERT INTO tracks_fts(tracks_fts, rowid, title, artist, album, album_artist, filename, genre)
                VALUES('delete', old.id, old.title, old.artist, old.album, old.album_artist, old.filename, old.genre);
            END;

            CREATE TRIGGER IF NOT EXISTS tracks_au AFTER UPDATE ON tracks BEGIN
                INSERT INTO tracks_fts(tracks_fts, rowid, title, artist, album, album_artist, filename, genre)
                VALUES('delete', old.id, old.title, old.artist, old.album, old.album_artist, old.filename, old.genre);
                INSERT INTO tracks_fts(rowid, title, artist, album, album_artist, filename, genre)
                VALUES (new.id, new.title, new.artist, new.album, new.album_artist, new.filename, new.genre);
            END;
        """
        )

        # Playlists
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_modified TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS playlist_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                track_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE,
                UNIQUE(playlist_id, track_id)
            );
        """
        )

        # Play history
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS play_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER NOT NULL,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                play_duration_seconds REAL,
                completed BOOLEAN DEFAULT 0,
                FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
            )
        """
        )

        # Waveform cache
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS waveform_cache (
                track_id INTEGER PRIMARY KEY,
                waveform_data BLOB,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
            )
        """
        )

        # Audio analysis
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audio_analysis (
                track_id INTEGER PRIMARY KEY,
                tempo REAL,
                energy REAL,
                bass_energy REAL,
                mid_energy REAL,
                treble_energy REAL,
                spectral_centroid REAL,
                zero_crossing_rate REAL,
                rms_energy REAL,
                dynamic_range REAL,
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
            )
        """
        )

        # Migrate schema to add ML features columns if they don't exist
        self._migrate_ml_features()

        # Migrate schema to add mode column if it doesn't exist
        self._migrate_track_mode()

        # Plugin settings (runtime configuration overrides)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plugin_settings (
                plugin_name TEXT NOT NULL,
                setting_key TEXT NOT NULL,
                setting_value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (plugin_name, setting_key)
            )
        """
        )

        self.conn.commit()

    def _migrate_ml_features(self) -> None:
        """Add ML feature columns to audio_analysis table if they don't exist."""
        if self.conn is None:
            return

        # Get existing columns
        cursor = self.conn.execute("PRAGMA table_info(audio_analysis)")
        existing_columns = {row["name"] for row in cursor.fetchall()}

        # Define all ML feature columns to add
        ml_columns = {
            # Energy & dynamics (8)
            "rms_mean": "REAL",
            "rms_std": "REAL",
            "rms_p10": "REAL",
            "rms_p90": "REAL",
            "peak_amplitude": "REAL",
            "crest_factor": "REAL",
            # dynamic_range already exists
            "loudness_variation": "REAL",
            # Frequency band energies (12) - sub_bass, bass, low_mid, mid, high_mid, high
            "sub_bass_mean": "REAL",
            "sub_bass_ratio": "REAL",
            "bass_mean": "REAL",
            "bass_ratio": "REAL",
            "low_mid_mean": "REAL",
            "low_mid_ratio": "REAL",
            "mid_mean": "REAL",
            "mid_ratio": "REAL",
            "high_mid_mean": "REAL",
            "high_mid_ratio": "REAL",
            "high_mean": "REAL",
            "high_ratio": "REAL",
            # Spectral features (8) - centroid already exists
            "spectral_centroid_std": "REAL",
            "spectral_bandwidth": "REAL",
            "spectral_rolloff": "REAL",
            "spectral_flatness": "REAL",
            "spectral_contrast": "REAL",
            "spectral_entropy": "REAL",
            # MFCC (10 coefficients mean)
            "mfcc_1": "REAL",
            "mfcc_2": "REAL",
            "mfcc_3": "REAL",
            "mfcc_4": "REAL",
            "mfcc_5": "REAL",
            "mfcc_6": "REAL",
            "mfcc_7": "REAL",
            "mfcc_8": "REAL",
            "mfcc_9": "REAL",
            "mfcc_10": "REAL",
            # Percussive vs harmonic (5)
            "percussive_energy": "REAL",
            "harmonic_energy": "REAL",
            "perc_harm_ratio": "REAL",
            "percussive_onset_rate": "REAL",
            "onset_strength_mean": "REAL",
            # Rhythm & tempo (6) - tempo already exists
            "tempo_confidence": "REAL",
            "beat_interval_mean": "REAL",
            "beat_interval_std": "REAL",
            "onset_rate": "REAL",
            "tempogram_periodicity": "REAL",
            # Harmony (4)
            "chroma_entropy": "REAL",
            "chroma_centroid": "REAL",
            "chroma_energy_std": "REAL",
            "tonnetz_mean": "REAL",
            # Structure (4)
            "intro_energy_ratio": "REAL",
            "core_energy_ratio": "REAL",
            "outro_energy_ratio": "REAL",
            "energy_slope": "REAL",
        }

        # Add missing columns
        for column_name, column_type in ml_columns.items():
            if column_name not in existing_columns:
                try:
                    self.conn.execute(
                        f"ALTER TABLE audio_analysis ADD COLUMN {column_name} {column_type}"
                    )
                except sqlite3.OperationalError:
                    # Column might already exist (concurrent migration)
                    pass

        self.conn.commit()

    def _migrate_track_mode(self) -> None:
        """Add mode column to tracks table if it doesn't exist."""
        if self.conn is None:
            return

        # Get existing columns
        cursor = self.conn.execute("PRAGMA table_info(tracks)")
        existing_columns = {row["name"] for row in cursor.fetchall()}

        if "mode" not in existing_columns:
            # Add mode column with default "curating" for existing tracks
            self.conn.execute("ALTER TABLE tracks ADD COLUMN mode TEXT NOT NULL DEFAULT 'curating'")
            # Create index for efficient mode filtering
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_mode ON tracks(mode)")
            self.conn.commit()

    # ========== Legacy Methods (delegate to repositories) ==========

    def add_track(self, track_data: dict[str, Any], mode: str = "jukebox") -> int:
        """Add a track to the database.

        Args:
            track_data: Track metadata dictionary
            mode: Application mode ("jukebox" or "curating")

        Returns:
            Track ID

        Note:
            Prefer using database.tracks.add() for new code.
        """
        return self.tracks.add(track_data, mode)

    def search_tracks(
        self, query: str, limit: int = 100, mode: str | None = None
    ) -> list[dict[str, Any]]:
        """Search tracks using FTS5.

        Note:
            Prefer using database.tracks.search() for new code.
        """
        return self.tracks.search(query, limit, mode)

    def get_all_tracks(
        self, limit: int | None = None, mode: str | None = None
    ) -> list[dict[str, Any]]:
        """Get all tracks, optionally filtered by mode.

        Note:
            Prefer using database.tracks.get_all() for new code.
        """
        return self.tracks.get_all(limit, mode)

    def update_track_mode(self, track_id: int, mode: str) -> bool:
        """Update the mode of a track.

        Note:
            Prefer using database.tracks.update_mode() for new code.
        """
        return self.tracks.update_mode(track_id, mode)

    def get_track_by_id(self, track_id: int) -> dict[str, Any] | None:
        """Get track by ID.

        Note:
            Prefer using database.tracks.get_by_id() for new code.
        """
        return self.tracks.get_by_id(track_id)

    def record_play(self, track_id: int, duration: float, completed: bool) -> None:
        """Record a play in history.

        Note:
            Prefer using database.tracks.record_play() for new code.
        """
        self.tracks.record_play(track_id, duration, completed)

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()

    # ========== Legacy Track Methods ==========

    def get_track_by_filepath(self, filepath: str | Path) -> dict[str, Any] | None:
        """Get track by filepath.

        Note:
            Prefer using database.tracks.get_by_filepath() for new code.
        """
        return self.tracks.get_by_filepath(filepath)

    def delete_track(self, track_id: int) -> bool:
        """Delete a track from the database.

        Note:
            Prefer using database.tracks.delete() for new code.
        """
        return self.tracks.delete(track_id)

    def delete_track_by_filepath(self, filepath: str | Path) -> bool:
        """Delete a track by filepath.

        Note:
            Prefer using database.tracks.delete_by_filepath() for new code.
        """
        return self.tracks.delete_by_filepath(filepath)

    def update_track_metadata(self, track_id: int, metadata: dict[str, Any]) -> bool:
        """Update track metadata fields.

        Note:
            Prefer using database.tracks.update_metadata() for new code.
        """
        return self.tracks.update_metadata(track_id, metadata)

    def update_track_filepath(
        self, track_id: int, new_filepath: str | Path, new_filename: str | None = None
    ) -> bool:
        """Update track filepath (after file move/rename).

        Note:
            Prefer using database.tracks.update_filepath() for new code.
        """
        return self.tracks.update_filepath(track_id, new_filepath, new_filename)

    # ========== Legacy Waveform Methods ==========

    def get_waveform_cache(self, track_id: int) -> bytes | None:
        """Get cached waveform data for a track.

        Note:
            Prefer using database.waveforms.get() for new code.
        """
        return self.waveforms.get(track_id)

    def get_tracks_without_waveform(
        self, mode: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Get tracks that don't have cached waveform data.

        Note:
            Prefer using database.waveforms.get_tracks_without_waveform() for new code.
        """
        return self.waveforms.get_tracks_without_waveform(mode, limit)

    # ========== Legacy Analysis Methods ==========

    def get_audio_analysis(self, track_id: int) -> dict[str, Any] | None:
        """Get audio analysis for a track.

        Note:
            Prefer using database.analysis.get() for new code.
        """
        return self.analysis.get(track_id)

    def save_audio_analysis(self, track_id: int, analysis: dict[str, Any]) -> None:
        """Save audio analysis data.

        Note:
            Prefer using database.analysis.save() for new code.
        """
        self.analysis.save(track_id, analysis)

    def get_tracks_without_analysis(
        self, mode: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Get tracks that don't have audio analysis.

        Note:
            Prefer using database.analysis.get_tracks_without_analysis() for new code.
        """
        return self.analysis.get_tracks_without_analysis(mode, limit)

    def has_audio_analysis(self, track_id: int) -> bool:
        """Check if a track has audio analysis.

        Note:
            Prefer using database.analysis.exists() for new code.
        """
        return self.analysis.exists(track_id)

    # ========== Legacy Plugin Settings Methods ==========

    def get_plugin_setting(self, plugin_name: str, key: str) -> str | None:
        """Get a plugin setting value.

        Note:
            Prefer using database.settings.get() for new code.
        """
        return self.settings.get(plugin_name, key)

    def save_plugin_setting(self, plugin_name: str, key: str, value: str) -> None:
        """Save a plugin setting.

        Note:
            Prefer using database.settings.save() for new code.
        """
        self.settings.save(plugin_name, key, value)
