"""Database storage for audio fingerprints.

Stores fingerprints in the Jukebox SQLite database, creating a new table
for fingerprints that references the existing tracks table.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

from .fingerprint import Fingerprint


# Default Jukebox database path
DEFAULT_DB_PATH = Path.home() / ".jukebox" / "jukebox.db"


class FingerprintDB:
    """Database interface for storing and querying fingerprints.

    Uses the Jukebox SQLite database, adding a fingerprints table.
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path)
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        """Create fingerprint tables if they don't exist."""
        conn = self._get_connection()

        # Main fingerprints table
        # Using hash as primary lookup, with index for fast querying
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fingerprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER NOT NULL,
                hash INTEGER NOT NULL,
                time_offset_ms INTEGER NOT NULL,
                freq_bin INTEGER,
                FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
            )
        """)

        # Index on hash for fast lookup during matching
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_fingerprints_hash
            ON fingerprints(hash)
        """)

        # Index on track_id for fast deletion/lookup by track
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_fingerprints_track_id
            ON fingerprints(track_id)
        """)

        # Track indexing status
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fingerprint_status (
                track_id INTEGER PRIMARY KEY,
                fingerprint_count INTEGER NOT NULL,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
            )
        """)

        conn.commit()
        conn.close()

    def is_indexed(self, track_id: int) -> bool:
        """Check if a track has been fingerprinted.

        Args:
            track_id: Track ID

        Returns:
            True if track has fingerprints
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT 1 FROM fingerprint_status WHERE track_id = ?",
            (track_id,)
        ).fetchone()
        conn.close()
        return row is not None

    def store_fingerprints(
        self,
        track_id: int,
        fingerprints: list[Fingerprint],
        replace: bool = False,
    ) -> int:
        """Store fingerprints for a track.

        Args:
            track_id: Track ID from tracks table
            fingerprints: List of fingerprints to store
            replace: If True, delete existing fingerprints first

        Returns:
            Number of fingerprints stored
        """
        conn = self._get_connection()

        if replace:
            conn.execute("DELETE FROM fingerprints WHERE track_id = ?", (track_id,))
            conn.execute("DELETE FROM fingerprint_status WHERE track_id = ?", (track_id,))

        # Batch insert fingerprints
        conn.executemany(
            """
            INSERT INTO fingerprints (track_id, hash, time_offset_ms, freq_bin)
            VALUES (?, ?, ?, ?)
            """,
            [
                (track_id, fp.hash, fp.time_offset_ms, fp.freq_bin)
                for fp in fingerprints
            ]
        )

        # Update status
        conn.execute(
            """
            INSERT OR REPLACE INTO fingerprint_status (track_id, fingerprint_count)
            VALUES (?, ?)
            """,
            (track_id, len(fingerprints))
        )

        conn.commit()
        conn.close()

        return len(fingerprints)

    def query_fingerprints(
        self,
        hashes: list[int],
    ) -> list[tuple[int, int, int]]:
        """Query fingerprints by hash values.

        Uses a temporary table for efficient lookup with large hash lists.

        Args:
            hashes: List of hash values to search for

        Returns:
            List of (track_id, time_offset_ms, hash) tuples
        """
        if not hashes:
            return []

        conn = self._get_connection()

        # Use temporary table + JOIN for better performance with large hash lists
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS query_hashes (hash INTEGER PRIMARY KEY)")
        conn.execute("DELETE FROM query_hashes")

        # Batch insert hashes into temp table
        conn.executemany(
            "INSERT OR IGNORE INTO query_hashes (hash) VALUES (?)",
            [(h,) for h in hashes]
        )

        # JOIN is faster than IN clause for large lists
        rows = conn.execute(
            """
            SELECT f.track_id, f.time_offset_ms, f.hash
            FROM fingerprints f
            INNER JOIN query_hashes q ON f.hash = q.hash
            """
        ).fetchall()

        conn.execute("DELETE FROM query_hashes")
        conn.close()

        return [(row["track_id"], row["time_offset_ms"], row["hash"]) for row in rows]

    def get_track_info(self, track_id: int) -> dict | None:
        """Get track information from the tracks table.

        Args:
            track_id: Track ID

        Returns:
            Dict with track info or None
        """
        conn = self._get_connection()
        row = conn.execute(
            """
            SELECT id, filepath, filename, title, artist, album, duration_seconds
            FROM tracks
            WHERE id = ?
            """,
            (track_id,)
        ).fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def get_tracks_to_index(self, mode: str | None = None, limit: int | None = None) -> list[dict]:
        """Get tracks that haven't been fingerprinted yet.

        Args:
            mode: Filter by mode (jukebox/curating)
            limit: Maximum number of tracks

        Returns:
            List of track dicts with id and filepath
        """
        conn = self._get_connection()

        query = """
            SELECT t.id, t.filepath, t.filename
            FROM tracks t
            LEFT JOIN fingerprint_status fs ON t.id = fs.track_id
            WHERE fs.track_id IS NULL
        """
        params: list = []

        if mode:
            query += " AND t.mode = ?"
            params.append(mode)

        if limit:
            query += f" LIMIT {limit}"

        rows = conn.execute(query, params).fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_all_indexed_tracks(self) -> list[dict]:
        """Get all tracks that have been fingerprinted.

        Returns:
            List of track dicts
        """
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT t.id, t.filepath, t.filename, t.title, t.artist,
                   fs.fingerprint_count, fs.indexed_at
            FROM tracks t
            JOIN fingerprint_status fs ON t.id = fs.track_id
            ORDER BY fs.indexed_at DESC
            """
        ).fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        """Get fingerprint database statistics.

        Returns:
            Dict with stats
        """
        conn = self._get_connection()

        total_tracks = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        indexed_tracks = conn.execute("SELECT COUNT(*) FROM fingerprint_status").fetchone()[0]
        total_fingerprints = conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]

        conn.close()

        return {
            "total_tracks": total_tracks,
            "indexed_tracks": indexed_tracks,
            "unindexed_tracks": total_tracks - indexed_tracks,
            "total_fingerprints": total_fingerprints,
            "avg_fingerprints_per_track": (
                total_fingerprints / indexed_tracks if indexed_tracks > 0 else 0
            ),
        }

    def delete_track_fingerprints(self, track_id: int) -> None:
        """Delete fingerprints for a track.

        Args:
            track_id: Track ID
        """
        conn = self._get_connection()
        conn.execute("DELETE FROM fingerprints WHERE track_id = ?", (track_id,))
        conn.execute("DELETE FROM fingerprint_status WHERE track_id = ?", (track_id,))
        conn.commit()
        conn.close()

    def clear_all_fingerprints(self) -> None:
        """Delete all fingerprints from the database."""
        conn = self._get_connection()
        conn.execute("DELETE FROM fingerprints")
        conn.execute("DELETE FROM fingerprint_status")
        conn.commit()
        conn.close()
