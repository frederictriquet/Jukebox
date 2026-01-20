"""SQLite database manager with FTS5 support."""

import sqlite3
from pathlib import Path
from typing import Any


class Database:
    """SQLite database manager with FTS5 support."""

    def __init__(self, db_path: Path):
        """Initialize database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Connect to database and enable foreign keys."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

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
        existing_columns = {row[1] for row in cursor.fetchall()}

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
        existing_columns = {row[1] for row in cursor.fetchall()}

        if "mode" not in existing_columns:
            # Add mode column with default "curating" for existing tracks
            self.conn.execute(
                "ALTER TABLE tracks ADD COLUMN mode TEXT NOT NULL DEFAULT 'curating'"
            )
            # Create index for efficient mode filtering
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tracks_mode ON tracks(mode)"
            )
            self.conn.commit()

    def add_track(self, track_data: dict[str, Any], mode: str = "jukebox") -> int:
        """Add a track to the database.

        Args:
            track_data: Track metadata dictionary
            mode: Application mode ("jukebox" or "curating")

        Returns:
            Track ID
        """
        if self.conn is None:
            raise RuntimeError("Database not connected")

        cursor = self.conn.execute(
            """
            INSERT OR REPLACE INTO tracks (
                filepath, filename, title, artist, album, album_artist,
                genre, year, track_number, duration_seconds, bitrate,
                sample_rate, file_size, date_modified, mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                str(track_data["filepath"]),
                track_data["filename"],
                track_data.get("title"),
                track_data.get("artist"),
                track_data.get("album"),
                track_data.get("album_artist"),
                track_data.get("genre"),
                track_data.get("year"),
                track_data.get("track_number"),
                track_data.get("duration_seconds"),
                track_data.get("bitrate"),
                track_data.get("sample_rate"),
                track_data.get("file_size"),
                track_data.get("date_modified"),
                mode,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid) if cursor.lastrowid is not None else 0

    def search_tracks(
        self, query: str, limit: int = 100, mode: str | None = None
    ) -> list[sqlite3.Row]:
        """Search tracks using FTS5.

        Args:
            query: Search query
            limit: Maximum results
            mode: Optional mode filter ("jukebox" or "curating")

        Returns:
            List of matching tracks
        """
        if self.conn is None:
            raise RuntimeError("Database not connected")

        if mode:
            cursor = self.conn.execute(
                """
                SELECT t.*
                FROM tracks t
                JOIN tracks_fts fts ON t.id = fts.rowid
                WHERE tracks_fts MATCH ? AND t.mode = ?
                ORDER BY rank
                LIMIT ?
            """,
                (query, mode, limit),
            )
        else:
            cursor = self.conn.execute(
                """
                SELECT t.*
                FROM tracks t
                JOIN tracks_fts fts ON t.id = fts.rowid
                WHERE tracks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """,
                (query, limit),
            )
        return cursor.fetchall()

    def get_all_tracks(
        self, limit: int | None = None, mode: str | None = None
    ) -> list[sqlite3.Row]:
        """Get all tracks, optionally filtered by mode.

        Args:
            limit: Optional limit
            mode: Optional mode filter ("jukebox" or "curating")

        Returns:
            List of tracks
        """
        if self.conn is None:
            raise RuntimeError("Database not connected")

        if mode:
            query = "SELECT * FROM tracks WHERE mode = ? ORDER BY date_added DESC"
            params: tuple[str, ...] = (mode,)
            if limit:
                query += f" LIMIT {limit}"
            return self.conn.execute(query, params).fetchall()
        else:
            query = "SELECT * FROM tracks ORDER BY date_added DESC"
            if limit:
                query += f" LIMIT {limit}"
            return self.conn.execute(query).fetchall()

    def update_track_mode(self, track_id: int, mode: str) -> bool:
        """Update the mode of a track.

        Args:
            track_id: Track ID
            mode: New mode ("jukebox" or "curating")

        Returns:
            True if updated, False if track not found
        """
        if self.conn is None:
            raise RuntimeError("Database not connected")

        cursor = self.conn.execute(
            "UPDATE tracks SET mode = ? WHERE id = ?",
            (mode, track_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_track_by_id(self, track_id: int) -> sqlite3.Row | None:
        """Get track by ID.

        Args:
            track_id: Track ID

        Returns:
            Track row or None
        """
        if self.conn is None:
            raise RuntimeError("Database not connected")

        cursor = self.conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
        result = cursor.fetchone()
        return result if result is not None else None

    def record_play(self, track_id: int, duration: float, completed: bool) -> None:
        """Record a play in history.

        Args:
            track_id: Track ID
            duration: Play duration in seconds
            completed: Whether track was completed
        """
        if self.conn is None:
            raise RuntimeError("Database not connected")

        self.conn.execute(
            """
            INSERT INTO play_history (track_id, play_duration_seconds, completed)
            VALUES (?, ?, ?)
        """,
            (track_id, duration, completed),
        )

        self.conn.execute(
            """
            UPDATE tracks
            SET play_count = play_count + 1, last_played = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (track_id,),
        )

        self.conn.commit()

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
