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

    def add_track(self, track_data: dict[str, Any]) -> int:
        """Add a track to the database.

        Args:
            track_data: Track metadata dictionary

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
                sample_rate, file_size, date_modified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid) if cursor.lastrowid is not None else 0

    def search_tracks(self, query: str, limit: int = 100) -> list[sqlite3.Row]:
        """Search tracks using FTS5.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching tracks
        """
        if self.conn is None:
            raise RuntimeError("Database not connected")

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

    def get_all_tracks(self, limit: int | None = None) -> list[sqlite3.Row]:
        """Get all tracks.

        Args:
            limit: Optional limit

        Returns:
            List of tracks
        """
        if self.conn is None:
            raise RuntimeError("Database not connected")

        query = "SELECT * FROM tracks ORDER BY date_added DESC"
        if limit:
            query += f" LIMIT {limit}"
        return self.conn.execute(query).fetchall()

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
