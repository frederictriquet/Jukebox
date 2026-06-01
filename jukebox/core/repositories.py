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
        filepath = str(track_data["filepath"])
        values = (
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
        )

        # INSERT OR IGNORE + UPDATE conditionnel plutôt que INSERT OR REPLACE :
        # REPLACE supprime puis recrée la ligne avec un nouvel id, ce qui déclenche
        # ON DELETE CASCADE et efface waveform_cache + audio_analysis à chaque re-scan.
        # Ici l'id de la piste existante est préservé, donc les données liées aussi.
        cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO tracks (
                filepath, filename, title, artist, album, album_artist,
                genre, year, track_number, duration_seconds, bitrate,
                sample_rate, file_size, date_modified, mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (filepath, *values),
        )

        if cursor.rowcount > 0:
            # Nouvelle piste insérée.
            track_id = int(cursor.lastrowid) if cursor.lastrowid is not None else 0
        else:
            # Piste déjà présente (filepath UNIQUE) : mise à jour sur place.
            self._conn.execute(
                """
                UPDATE tracks SET
                    filename = ?, title = ?, artist = ?, album = ?, album_artist = ?,
                    genre = ?, year = ?, track_number = ?, duration_seconds = ?,
                    bitrate = ?, sample_rate = ?, file_size = ?, date_modified = ?, mode = ?
                WHERE filepath = ?
            """,
                (*values, filepath),
            )
            row = self._conn.execute(
                "SELECT id FROM tracks WHERE filepath = ?", (filepath,)
            ).fetchone()
            track_id = int(row["id"]) if row else 0

        self._commit()
        return track_id

    def search(self, query: str, limit: int = 100, mode: str | None = None) -> list[dict[str, Any]]:
        """Search tracks using FTS5.

        Args:
            query: Search query
            limit: Maximum results
            mode: Optional mode filter ("jukebox" or "curating")

        Returns:
            List of matching tracks
        """
        # Escape FTS5 special characters by quoting each term
        terms = query.split()
        safe_query = " ".join(f'"{t}"' for t in terms) if terms else query

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
                (safe_query, mode, limit),
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
                (safe_query, limit),
            )
        return cursor.fetchall()

    def get_all(self, limit: int | None = None, mode: str | None = None) -> list[dict[str, Any]]:
        """Get all tracks, optionally filtered by mode.

        Args:
            limit: Optional limit
            mode: Optional mode filter ("jukebox" or "curating")

        Returns:
            List of tracks
        """
        query = "SELECT * FROM tracks"
        params: list[Any] = []
        if mode:
            query += " WHERE mode = ?"
            params.append(mode)
        query += " ORDER BY date_added DESC"
        if limit:
            # LIMIT paramétré plutôt qu'interpolé : cohérent avec le reste du code,
            # évite tout risque d'injection si `limit` devenait une source externe.
            query += " LIMIT ?"
            params.append(limit)
        return self._conn.execute(query, params).fetchall()

    def get_by_id(self, track_id: int) -> dict[str, Any] | None:
        """Get track by ID.

        Args:
            track_id: Track ID

        Returns:
            Track row or None
        """
        cursor = self._conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
        result = cursor.fetchone()
        return result if result is not None else None

    def get_by_filepath(self, filepath: str | Path) -> dict[str, Any] | None:
        """Get track by filepath.

        Args:
            filepath: Track filepath (string or Path)

        Returns:
            Track row or None
        """
        cursor = self._conn.execute(
            "SELECT * FROM tracks WHERE filepath = ?", (Path(filepath).as_posix(),)
        )
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
        cursor = self._conn.execute(
            "DELETE FROM tracks WHERE filepath = ?", (Path(filepath).as_posix(),)
        )
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

        # `set_clause` ne contient que des colonnes filtrées via `allowed_fields`.
        cursor = self._conn.execute(
            f"UPDATE tracks SET {set_clause} WHERE id = ?",  # noqa: S608
            values,
        )
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
        new_filepath_str = Path(new_filepath).as_posix()
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

    def get_recently_played_artists_genres(self, limit: int = 20) -> list[dict[str, Any]]:
        """Retourne les couples (artist, genre) distincts des pistes récemment terminées.

        Args:
            limit: Nombre maximum de lignes d'historique à considérer.

        Returns:
            Liste de dicts avec les clés `artist` et `genre`.
        """
        return self._conn.execute(
            """
            SELECT DISTINCT t.artist, t.genre
            FROM tracks t
            JOIN play_history ph ON t.id = ph.track_id
            WHERE ph.completed = 1
            ORDER BY ph.played_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def get_random(self, limit: int) -> list[dict[str, Any]]:
        """Retourne des pistes aléatoires.

        Args:
            limit: Nombre de pistes à retourner.

        Returns:
            Liste de pistes.
        """
        return self._conn.execute(
            "SELECT * FROM tracks ORDER BY RANDOM() LIMIT ?", (limit,)
        ).fetchall()

    def get_random_by_artist_unplayed(
        self, artist: str, limit: int, exclude_days: int = 7
    ) -> list[dict[str, Any]]:
        """Retourne des pistes aléatoires d'un artiste non jouées récemment.

        Args:
            artist: Nom de l'artiste.
            limit: Nombre de pistes à retourner.
            exclude_days: Fenêtre (en jours) d'exclusion des pistes déjà jouées.

        Returns:
            Liste de pistes.
        """
        return self._conn.execute(
            """
            SELECT * FROM tracks
            WHERE artist = ?
            AND id NOT IN (
                SELECT track_id FROM play_history
                WHERE played_at > datetime('now', ?)
            )
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (artist, f"-{exclude_days} days", limit),
        ).fetchall()

    def get_random_by_genre(self, genre: str, limit: int) -> list[dict[str, Any]]:
        """Retourne des pistes aléatoires d'un genre donné.

        Args:
            genre: Nom du genre.
            limit: Nombre de pistes à retourner.

        Returns:
            Liste de pistes.
        """
        return self._conn.execute(
            "SELECT * FROM tracks WHERE genre = ? ORDER BY RANDOM() LIMIT ?",
            (genre, limit),
        ).fetchall()

    def get_stats(self, mode: str | None = None) -> dict[str, Any]:
        """Retourne les statistiques agrégées de la bibliothèque.

        Args:
            mode: Filtre optionnel par mode ("jukebox" ou "curating").

        Returns:
            Dict avec `total_tracks` (int) et `total_duration_seconds` (float).
        """
        query = (
            "SELECT COUNT(*) AS total_tracks, "
            "COALESCE(SUM(duration_seconds), 0) AS total_duration_seconds FROM tracks"
        )
        params: list[Any] = []
        if mode:
            query += " WHERE mode = ?"
            params.append(mode)
        row = self._conn.execute(query, params).fetchone()
        return {
            "total_tracks": row["total_tracks"] if row else 0,
            "total_duration_seconds": row["total_duration_seconds"] if row else 0.0,
        }

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
    ) -> list[dict[str, Any]]:
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
            # LIMIT paramétré plutôt qu'interpolé : évite tout risque d'injection.
            query += " LIMIT ?"
            params.append(limit)

        return self._conn.execute(query, params).fetchall()


class AnalysisRepository(BaseRepository):
    """Repository for audio analysis operations."""

    # Colonnes autorisées de la table audio_analysis (hors track_id, clé primaire).
    # Toute clé du dict `analysis` absente de cette whitelist est rejetée avant
    # construction de la requête SQL pour éviter toute injection via les noms de colonnes.
    _ALLOWED_COLUMNS = frozenset(
        {
            "tempo",
            "energy",
            "bass_energy",
            "mid_energy",
            "treble_energy",
            "spectral_centroid",
            "zero_crossing_rate",
            "rms_energy",
            "dynamic_range",
            "rms_mean",
            "rms_std",
            "rms_p10",
            "rms_p90",
            "peak_amplitude",
            "crest_factor",
            "loudness_variation",
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
            "spectral_centroid_std",
            "spectral_bandwidth",
            "spectral_rolloff",
            "spectral_flatness",
            "spectral_contrast",
            "spectral_entropy",
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
            "percussive_energy",
            "harmonic_energy",
            "perc_harm_ratio",
            "percussive_onset_rate",
            "onset_strength_mean",
            "tempo_confidence",
            "beat_interval_mean",
            "beat_interval_std",
            "onset_rate",
            "tempogram_periodicity",
            "chroma_entropy",
            "chroma_centroid",
            "chroma_energy_std",
            "tonnetz_mean",
            "intro_energy_ratio",
            "core_energy_ratio",
            "outro_energy_ratio",
            "energy_slope",
        }
    )

    def get(self, track_id: int) -> dict[str, Any] | None:
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

        Raises:
            ValueError: Si une clé du dict n'appartient pas à la whitelist de colonnes.
        """
        # Validation des clés contre la whitelist avant toute construction de requête :
        # les noms de colonnes sont interpolés dans le SQL (impossible de les lier),
        # une clé non whitelistée pourrait donc injecter du SQL arbitraire.
        unknown = set(analysis) - self._ALLOWED_COLUMNS
        if unknown:
            raise ValueError(f"Colonnes d'analyse inconnues : {sorted(unknown)}")

        # Check if analysis exists
        existing = self._conn.execute(
            "SELECT 1 FROM audio_analysis WHERE track_id = ?", (track_id,)
        ).fetchone()

        if existing:
            # Update existing
            if analysis:
                set_clause = ", ".join(f"{k} = ?" for k in analysis)
                values = list(analysis.values()) + [track_id]
                # `set_clause` ne contient que des colonnes whitelistées (cf. _ALLOWED_COLUMNS).
                self._conn.execute(
                    f"UPDATE audio_analysis SET {set_clause} WHERE track_id = ?",  # noqa: S608
                    values,
                )
        else:
            # Insert new
            columns = ["track_id"] + list(analysis.keys())
            placeholders = ", ".join(["?"] * len(columns))
            values = [track_id] + list(analysis.values())
            # `columns` ne contient que des colonnes whitelistées (cf. _ALLOWED_COLUMNS).
            self._conn.execute(
                f"INSERT INTO audio_analysis ({', '.join(columns)}) VALUES ({placeholders})",  # noqa: S608
                values,
            )

        self._commit()

    def delete(self, track_id: int) -> None:
        """Delete audio analysis data for a track.

        Args:
            track_id: Track ID
        """
        self._conn.execute(
            "DELETE FROM audio_analysis WHERE track_id = ?",
            (track_id,),
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
    ) -> list[dict[str, Any]]:
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
            # LIMIT paramétré plutôt qu'interpolé : évite tout risque d'injection.
            query += " LIMIT ?"
            params.append(limit)

        return self._conn.execute(query, params).fetchall()


class PlaylistRepository(BaseRepository):
    """Repository for playlist operations."""

    def create(self, name: str) -> int:
        """Crée une playlist et retourne son id.

        Args:
            name: Nom de la playlist (doit être unique).

        Returns:
            Id de la playlist créée.
        """
        cursor = self._conn.execute("INSERT INTO playlists (name) VALUES (?)", (name,))
        self._commit()
        return int(cursor.lastrowid) if cursor.lastrowid is not None else 0

    def get(self, playlist_id: int) -> dict[str, Any] | None:
        """Retourne une playlist par son ID."""
        result = self._conn.execute(
            "SELECT * FROM playlists WHERE id = ?", (playlist_id,)
        ).fetchone()
        return dict(result) if result is not None else None

    def get_all(self) -> list[dict[str, Any]]:
        """Retourne toutes les playlists triées par nom."""
        return self._conn.execute("SELECT * FROM playlists ORDER BY name").fetchall()

    def get_all_with_counts(self) -> list[dict[str, Any]]:
        """Retourne toutes les playlists avec le nombre de pistes (clé track_count)."""
        return self._conn.execute(
            """
            SELECT p.*, COUNT(pt.track_id) AS track_count
            FROM playlists p
            LEFT JOIN playlist_tracks pt ON p.id = pt.playlist_id
            GROUP BY p.id
            ORDER BY p.name
            """
        ).fetchall()

    def delete(self, playlist_id: int) -> bool:
        """Supprime une playlist.

        Args:
            playlist_id: Id de la playlist.

        Returns:
            True si une ligne a été supprimée.
        """
        cursor = self._conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        self._commit()
        return cursor.rowcount > 0

    def get_tracks(self, playlist_id: int) -> list[dict[str, Any]]:
        """Retourne les pistes d'une playlist dans l'ordre de position."""
        return self._conn.execute(
            """
            SELECT t.*
            FROM tracks t
            JOIN playlist_tracks pt ON t.id = pt.track_id
            WHERE pt.playlist_id = ?
            ORDER BY pt.position
            """,
            (playlist_id,),
        ).fetchall()

    def contains_track(self, playlist_id: int, track_id: int) -> bool:
        """Indique si une piste est déjà présente dans la playlist."""
        row = self._conn.execute(
            "SELECT 1 FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, track_id),
        ).fetchone()
        return row is not None

    def add_track(self, playlist_id: int, track_id: int) -> bool:
        """Ajoute une piste en fin de playlist.

        Args:
            playlist_id: Id de la playlist.
            track_id: Id de la piste.

        Returns:
            True si la piste a été ajoutée, False si elle y était déjà.
        """
        if self.contains_track(playlist_id, track_id):
            return False
        pos_row = self._conn.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 AS next_pos "
            "FROM playlist_tracks WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()
        next_pos = pos_row["next_pos"] if pos_row else 1
        self._conn.execute(
            "INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (?, ?, ?)",
            (playlist_id, track_id, next_pos),
        )
        self._commit()
        return True


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
