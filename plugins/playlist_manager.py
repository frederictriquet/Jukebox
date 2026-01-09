"""Playlist management."""

from typing import Any

from jukebox.core.database import Database


class PlaylistManager:
    """Manage playlists."""

    def __init__(self, database: Database):
        """Initialize playlist manager."""
        self.database = database

    def create_playlist(self, name: str, description: str = "") -> int:
        """Create a new playlist."""
        if self.database.conn is None:
            raise RuntimeError("Database not connected")

        cursor = self.database.conn.execute(
            "INSERT INTO playlists (name, description) VALUES (?, ?)", (name, description)
        )
        self.database.conn.commit()
        return int(cursor.lastrowid) if cursor.lastrowid is not None else 0

    def add_track_to_playlist(self, playlist_id: int, track_id: int) -> None:
        """Add track to playlist."""
        if self.database.conn is None:
            raise RuntimeError("Database not connected")

        # Get max position
        cursor = self.database.conn.execute(
            "SELECT COALESCE(MAX(position), 0) FROM playlist_tracks WHERE playlist_id = ?",
            (playlist_id,),
        )
        max_pos = cursor.fetchone()[0]

        self.database.conn.execute(
            "INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (?, ?, ?)",
            (playlist_id, track_id, max_pos + 1),
        )
        self.database.conn.commit()

    def get_playlist_tracks(self, playlist_id: int) -> list[Any]:
        """Get all tracks in playlist."""
        if self.database.conn is None:
            raise RuntimeError("Database not connected")

        return self.database.conn.execute(
            """
            SELECT t.*
            FROM tracks t
            JOIN playlist_tracks pt ON t.id = pt.track_id
            WHERE pt.playlist_id = ?
            ORDER BY pt.position
        """,
            (playlist_id,),
        ).fetchall()

    def get_all_playlists(self) -> list[Any]:
        """Get all playlists."""
        if self.database.conn is None:
            raise RuntimeError("Database not connected")

        return self.database.conn.execute("SELECT * FROM playlists ORDER BY name").fetchall()

    def delete_playlist(self, playlist_id: int) -> None:
        """Delete a playlist."""
        if self.database.conn is None:
            raise RuntimeError("Database not connected")

        self.database.conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        self.database.conn.commit()
