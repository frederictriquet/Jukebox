"""Repository classes for database operations."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jukebox.core.database import Database


class BaseRepository:
    """Base class for repositories."""

    def __init__(self, database: Database) -> None:
        """Initialize repository with database reference.

        Args:
            database: Database instance
        """
        self._db = database

    @property
    def _conn(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._db.conn is None:
            raise RuntimeError("Database not connected")
        return self._db.conn

    def _commit(self) -> None:
        """Commit if not inside a transaction.

        When inside a database.transaction() block, commits are deferred
        to the transaction manager.
        """
        if not self._db._in_transaction:
            self._conn.commit()


class TrackRepository(BaseRepository):
    """Repository for track operations."""

    def add(self, track_data: dict[str, Any], mode: str = "jukebox") -> int:
        """Add a track to the database.

        Args:
            track_data: Track metadata dictionary
            mode: Application mode ("jukebox" or "curating")

        Returns:
            Track ID
        """
        cursor = self._conn.execute(
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
        self._commit()
        return int(cursor.lastrowid) if cursor.lastrowid is not None else 0

    def search(self, query: str, limit: int = 100, mode: str | None = None) -> list[sqlite3.Row]:
        """Search tracks using FTS5.

        Args:
            query: Search query
            limit: Maximum results
            mode: Optional mode filter ("jukebox" or "curating")

        Returns:
            List of matching tracks
        """
        if mode:
            cursor = self._conn.execute(
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
            cursor = self._conn.execute(
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

    def get_all(self, limit: int | None = None, mode: str | None = None) -> list[sqlite3.Row]:
        """Get all tracks, optionally filtered by mode.

        Args:
            limit: Optional limit
            mode: Optional mode filter ("jukebox" or "curating")

        Returns:
            List of tracks
        """
        if mode:
            query = "SELECT * FROM tracks WHERE mode = ? ORDER BY date_added DESC"
            params: tuple[str, ...] = (mode,)
            if limit:
                query += f" LIMIT {limit}"
            return self._conn.execute(query, params).fetchall()
        else:
            query = "SELECT * FROM tracks ORDER BY date_added DESC"
            if limit:
                query += f" LIMIT {limit}"
            return self._conn.execute(query).fetchall()

    def get_by_id(self, track_id: int) -> sqlite3.Row | None:
        """Get track by ID.

        Args:
            track_id: Track ID

        Returns:
            Track row or None
        """
        cursor = self._conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
        result = cursor.fetchone()
        return result if result is not None else None

    def get_by_filepath(self, filepath: str | Path) -> sqlite3.Row | None:
        """Get track by filepath.

        Args:
            filepath: Track filepath (string or Path)

        Returns:
            Track row or None
        """
        cursor = self._conn.execute("SELECT * FROM tracks WHERE filepath = ?", (str(filepath),))
        result = cursor.fetchone()
        return result if result is not None else None

    def delete(self, track_id: int) -> bool:
        """Delete a track from the database.

        Args:
            track_id: Track ID

        Returns:
            True if deleted, False if track not found
        """
        cursor = self._conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        self._commit()
        return cursor.rowcount > 0

    def delete_by_filepath(self, filepath: str | Path) -> bool:
        """Delete a track by filepath.

        Args:
            filepath: Track filepath (string or Path)

        Returns:
            True if deleted, False if track not found
        """
        cursor = self._conn.execute("DELETE FROM tracks WHERE filepath = ?", (str(filepath),))
        self._commit()
        return cursor.rowcount > 0

    def update_metadata(self, track_id: int, metadata: dict[str, Any]) -> bool:
        """Update track metadata fields.

        Args:
            track_id: Track ID
            metadata: Dict of field names to values (only allowed fields are updated)

        Returns:
            True if updated, False if track not found
        """
        # Allowed fields for update
        allowed_fields = {
            "title",
            "artist",
            "album",
            "album_artist",
            "genre",
            "year",
            "track_number",
            "duration_seconds",
            "bitrate",
            "sample_rate",
            "file_size",
            "date_modified",
        }

        # Filter to allowed fields only
        updates = {k: v for k, v in metadata.items() if k in allowed_fields}
        if not updates:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [track_id]

        cursor = self._conn.execute(f"UPDATE tracks SET {set_clause} WHERE id = ?", values)
        self._commit()
        return cursor.rowcount > 0

    def update_filepath(
        self, track_id: int, new_filepath: str | Path, new_filename: str | None = None
    ) -> bool:
        """Update track filepath (after file move/rename).

        Args:
            track_id: Track ID
            new_filepath: New filepath
            new_filename: New filename (derived from filepath if not provided)

        Returns:
            True if updated, False if track not found
        """
        new_filepath_str = str(new_filepath)
        if new_filename is None:
            new_filename = Path(new_filepath).name

        cursor = self._conn.execute(
            "UPDATE tracks SET filepath = ?, filename = ? WHERE id = ?",
            (new_filepath_str, new_filename, track_id),
        )
        self._commit()
        return cursor.rowcount > 0

    def update_mode(self, track_id: int, mode: str) -> bool:
        """Update the mode of a track.

        Args:
            track_id: Track ID
            mode: New mode ("jukebox" or "curating")

        Returns:
            True if updated, False if track not found
        """
        cursor = self._conn.execute(
            "UPDATE tracks SET mode = ? WHERE id = ?",
            (mode, track_id),
        )
        self._commit()
        return cursor.rowcount > 0

    def record_play(self, track_id: int, duration: float, completed: bool) -> None:
        """Record a play in history.

        Args:
            track_id: Track ID
            duration: Play duration in seconds
            completed: Whether track was completed
        """
        self._conn.execute(
            """
            INSERT INTO play_history (track_id, play_duration_seconds, completed)
            VALUES (?, ?, ?)
        """,
            (track_id, duration, completed),
        )

        self._conn.execute(
            """
            UPDATE tracks
            SET play_count = play_count + 1, last_played = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (track_id,),
        )

        self._commit()


class WaveformRepository(BaseRepository):
    """Repository for waveform cache operations."""

    def get(self, track_id: int) -> bytes | None:
        """Get cached waveform data for a track.

        Args:
            track_id: Track ID

        Returns:
            Waveform data as bytes, or None if not cached
        """
        cursor = self._conn.execute(
            "SELECT waveform_data FROM waveform_cache WHERE track_id = ?",
            (track_id,),
        )
        row = cursor.fetchone()
        return row["waveform_data"] if row else None

    def save(self, track_id: int, waveform_data: bytes) -> None:
        """Save waveform data to cache.

        Args:
            track_id: Track ID
            waveform_data: Waveform data as bytes
        """
        self._conn.execute(
            """
            INSERT OR REPLACE INTO waveform_cache (track_id, waveform_data)
            VALUES (?, ?)
            """,
            (track_id, waveform_data),
        )
        self._commit()

    def delete(self, track_id: int) -> None:
        """Delete waveform data for a track.

        Args:
            track_id: Track ID
        """
        self._conn.execute(
            "DELETE FROM waveform_cache WHERE track_id = ?",
            (track_id,),
        )
        self._commit()

    def get_tracks_without_waveform(
        self, mode: str | None = None, limit: int | None = None
    ) -> list[sqlite3.Row]:
        """Get tracks that don't have cached waveform data.

        Args:
            mode: Optional mode filter ("jukebox" or "curating")
            limit: Optional limit on results

        Returns:
            List of track rows without waveform cache
        """
        query = """
            SELECT t.* FROM tracks t
            LEFT JOIN waveform_cache w ON t.id = w.track_id
            WHERE w.track_id IS NULL
        """
        params: list[Any] = []

        if mode:
            query += " AND t.mode = ?"
            params.append(mode)

        query += " ORDER BY t.date_added DESC"

        if limit:
            query += f" LIMIT {limit}"

        return self._conn.execute(query, params).fetchall()


class AnalysisRepository(BaseRepository):
    """Repository for audio analysis operations."""

    def get(self, track_id: int) -> sqlite3.Row | None:
        """Get audio analysis for a track.

        Args:
            track_id: Track ID

        Returns:
            Analysis row or None if not analyzed
        """
        cursor = self._conn.execute("SELECT * FROM audio_analysis WHERE track_id = ?", (track_id,))
        result = cursor.fetchone()
        return result if result is not None else None

    def save(self, track_id: int, analysis: dict[str, Any]) -> None:
        """Save audio analysis data.

        Args:
            track_id: Track ID
            analysis: Dict of analysis field names to values
        """
        # Check if analysis exists
        existing = self._conn.execute(
            "SELECT 1 FROM audio_analysis WHERE track_id = ?", (track_id,)
        ).fetchone()

        if existing:
            # Update existing
            if analysis:
                set_clause = ", ".join(f"{k} = ?" for k in analysis)
                values = list(analysis.values()) + [track_id]
                self._conn.execute(
                    f"UPDATE audio_analysis SET {set_clause} WHERE track_id = ?",
                    values,
                )
        else:
            # Insert new
            columns = ["track_id"] + list(analysis.keys())
            placeholders = ", ".join(["?"] * len(columns))
            values = [track_id] + list(analysis.values())
            self._conn.execute(
                f"INSERT INTO audio_analysis ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )

        self._commit()

    def exists(self, track_id: int) -> bool:
        """Check if a track has audio analysis.

        Args:
            track_id: Track ID

        Returns:
            True if analysis exists
        """
        cursor = self._conn.execute("SELECT 1 FROM audio_analysis WHERE track_id = ?", (track_id,))
        return cursor.fetchone() is not None

    def get_tracks_without_analysis(
        self, mode: str | None = None, limit: int | None = None
    ) -> list[sqlite3.Row]:
        """Get tracks that don't have audio analysis.

        Args:
            mode: Optional mode filter ("jukebox" or "curating")
            limit: Optional limit on results

        Returns:
            List of track rows without audio analysis
        """
        query = """
            SELECT t.* FROM tracks t
            LEFT JOIN audio_analysis a ON t.id = a.track_id
            WHERE a.track_id IS NULL
        """
        params: list[Any] = []

        if mode:
            query += " AND t.mode = ?"
            params.append(mode)

        query += " ORDER BY t.date_added DESC"

        if limit:
            query += f" LIMIT {limit}"

        return self._conn.execute(query, params).fetchall()


class PluginSettingsRepository(BaseRepository):
    """Repository for plugin settings operations."""

    def get(self, plugin_name: str, key: str) -> str | None:
        """Get a plugin setting value.

        Args:
            plugin_name: Plugin name
            key: Setting key

        Returns:
            Setting value or None if not set
        """
        cursor = self._conn.execute(
            """
            SELECT setting_value FROM plugin_settings
            WHERE plugin_name = ? AND setting_key = ?
            """,
            (plugin_name, key),
        )
        row = cursor.fetchone()
        return row["setting_value"] if row else None

    def save(self, plugin_name: str, key: str, value: str) -> None:
        """Save a plugin setting.

        Args:
            plugin_name: Plugin name
            key: Setting key
            value: Setting value
        """
        self._conn.execute(
            """
            INSERT OR REPLACE INTO plugin_settings (plugin_name, setting_key, setting_value)
            VALUES (?, ?, ?)
            """,
            (plugin_name, key, value),
        )
        self._commit()
