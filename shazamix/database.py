"""Database storage for audio fingerprints.

Stores fingerprints in the Jukebox SQLite database, creating a new table
for fingerprints that references the existing tracks table.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

from .fingerprint import Fingerprint  # type: ignore[import]


def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict[str, Any]:
    """Row factory that returns dicts instead of sqlite3.Row."""
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


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

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Fournit une connexion fermée automatiquement, même en cas d'exception."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = _dict_factory  # type: ignore[assignment]
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_tables(self) -> None:
        """Create fingerprint tables if they don't exist."""
        with self._connection() as conn:
            # Main fingerprints table
            # Using hash as primary lookup, with index for fast querying
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fingerprints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    track_id INTEGER NOT NULL,
                    hash INTEGER NOT NULL,
                    time_offset_ms INTEGER NOT NULL,
                    freq_bin INTEGER,
                    FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
                )
            """
            )

            # Index on hash for fast lookup during matching
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_fingerprints_hash
                ON fingerprints(hash)
            """
            )

            # Index on track_id for fast deletion/lookup by track
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_fingerprints_track_id
                ON fingerprints(track_id)
            """
            )

            # Track indexing status
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fingerprint_status (
                    track_id INTEGER PRIMARY KEY,
                    fingerprint_count INTEGER NOT NULL,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
                )
            """
            )

            # Audio feature summaries (MFCC etc.) for similarity matching
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audio_features (
                    track_id INTEGER NOT NULL,
                    feature_type TEXT NOT NULL,
                    feature_data BLOB NOT NULL,
                    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (track_id, feature_type),
                    FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
                )
            """
            )

            conn.commit()

    def is_indexed(self, track_id: int) -> bool:
        """Check if a track has been fingerprinted.

        Args:
            track_id: Track ID

        Returns:
            True if track has fingerprints
        """
        with self._connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM fingerprint_status WHERE track_id = ?", (track_id,)
            ).fetchone()
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
        with self._connection() as conn:
            if replace:
                conn.execute("DELETE FROM fingerprints WHERE track_id = ?", (track_id,))
                conn.execute("DELETE FROM fingerprint_status WHERE track_id = ?", (track_id,))

            # Batch insert fingerprints
            conn.executemany(
                """
                INSERT INTO fingerprints (track_id, hash, time_offset_ms, freq_bin)
                VALUES (?, ?, ?, ?)
                """,
                [(track_id, fp.hash, fp.time_offset_ms, fp.freq_bin) for fp in fingerprints],
            )

            # Update status
            conn.execute(
                """
                INSERT OR REPLACE INTO fingerprint_status (track_id, fingerprint_count)
                VALUES (?, ?)
                """,
                (track_id, len(fingerprints)),
            )

            conn.commit()

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

        with self._connection() as conn:
            # Use temporary table + JOIN for better performance with large hash lists
            conn.execute("CREATE TEMP TABLE IF NOT EXISTS query_hashes (hash INTEGER PRIMARY KEY)")
            conn.execute("DELETE FROM query_hashes")

            # Batch insert hashes into temp table
            conn.executemany(
                "INSERT OR IGNORE INTO query_hashes (hash) VALUES (?)", [(h,) for h in hashes]
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

        return [(row["track_id"], row["time_offset_ms"], row["hash"]) for row in rows]

    def get_track_info(self, track_id: int) -> dict | None:
        """Get track information from the tracks table.

        Args:
            track_id: Track ID

        Returns:
            Dict with track info or None
        """
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, filepath, filename, title, artist, album, duration_seconds
                FROM tracks
                WHERE id = ?
                """,
                (track_id,),
            ).fetchone()

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
            # LIMIT paramétré plutôt qu'interpolé : évite tout risque d'injection.
            query += " LIMIT ?"
            params.append(limit)

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [dict(row) for row in rows]

    def get_all_indexed_tracks(self) -> list[dict]:
        """Get all tracks that have been fingerprinted.

        Returns:
            List of track dicts
        """
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT t.id, t.filepath, t.filename, t.title, t.artist,
                       fs.fingerprint_count, fs.indexed_at
                FROM tracks t
                JOIN fingerprint_status fs ON t.id = fs.track_id
                ORDER BY fs.indexed_at DESC
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        """Get fingerprint database statistics.

        Returns:
            Dict with stats
        """
        with self._connection() as conn:
            total_tracks = conn.execute("SELECT COUNT(*) AS count FROM tracks").fetchone()["count"]
            indexed_tracks = conn.execute(
                "SELECT COUNT(*) AS count FROM fingerprint_status"
            ).fetchone()["count"]
            total_fingerprints = conn.execute(
                "SELECT COUNT(*) AS count FROM fingerprints"
            ).fetchone()["count"]

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
        with self._connection() as conn:
            conn.execute("DELETE FROM fingerprints WHERE track_id = ?", (track_id,))
            conn.execute("DELETE FROM fingerprint_status WHERE track_id = ?", (track_id,))
            conn.commit()

    def cleanup_orphans(self) -> dict[str, int]:
        """Delete fingerprint data for tracks that no longer exist in the tracks table.

        Returns:
            Dict with counts of deleted rows per table.
        """
        with self._connection() as conn:
            r_status = conn.execute(
                "DELETE FROM fingerprint_status WHERE track_id NOT IN (SELECT id FROM tracks)"
            )
            r_fp = conn.execute(
                "DELETE FROM fingerprints WHERE track_id NOT IN (SELECT id FROM tracks)"
            )
            conn.commit()
            status_count = r_status.rowcount
            fp_count = r_fp.rowcount

        # VACUUM doit s'exécuter hors transaction, sur une connexion dédiée.
        vacuum_conn = sqlite3.connect(self.db_path)
        try:
            vacuum_conn.execute("VACUUM")
        finally:
            vacuum_conn.close()
        return {"fingerprint_status": status_count, "fingerprints": fp_count}

    def clear_all_fingerprints(self) -> None:
        """Delete all fingerprints from the database."""
        with self._connection() as conn:
            conn.execute("DELETE FROM fingerprints")
            conn.execute("DELETE FROM fingerprint_status")
            conn.commit()

    def store_audio_features(self, track_id: int, feature_type: str, features: np.ndarray) -> None:
        """Store audio feature vector for a track.

        Args:
            track_id: Track ID
            feature_type: Feature type identifier (e.g. 'mfcc_summary')
            features: Numpy array of feature values
        """
        import numpy as np

        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO audio_features (track_id, feature_type, feature_data)
                VALUES (?, ?, ?)
                """,
                (track_id, feature_type, features.astype(np.float32).tobytes()),
            )
            conn.commit()

    def get_all_audio_features(self, feature_type: str) -> dict[int, np.ndarray]:
        """Load all audio features of a given type.

        Args:
            feature_type: Feature type identifier (e.g. 'mfcc_summary')

        Returns:
            Dict mapping track_id to feature numpy array
        """
        import numpy as np

        with self._connection() as conn:
            rows = conn.execute(
                "SELECT track_id, feature_data FROM audio_features WHERE feature_type = ?",
                (feature_type,),
            ).fetchall()

        result: dict[int, np.ndarray] = {}
        for row in rows:
            result[row["track_id"]] = np.frombuffer(row["feature_data"], dtype=np.float32)
        return result

    def count_audio_features(self, feature_type: str) -> int:
        """Count tracks with a given audio feature type.

        Args:
            feature_type: Feature type identifier

        Returns:
            Number of tracks with this feature type stored
        """
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM audio_features WHERE feature_type = ?",
                (feature_type,),
            ).fetchone()
        return row["cnt"] if row else 0
