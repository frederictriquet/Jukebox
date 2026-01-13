"""Recommendations plugin."""

import random
from typing import Any


class RecommendationsPlugin:
    """Recommend tracks based on history."""

    name = "recommendations"
    version = "1.0.0"
    description = "Get track recommendations"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

    def register_ui(self, ui_builder: Any) -> None:
        """Register UI."""
        menu = ui_builder.add_menu("&Discover")
        ui_builder.add_menu_action(menu, "Get Recommendations", self._show_recommendations)

    def _show_recommendations(self) -> None:
        """Show recommended tracks."""
        recommendations = self._get_recommendations(limit=20)

        # Update UI with recommendations
        from jukebox.core.event_bus import Events

        self.context.emit(Events.SEARCH_PERFORMED, results=recommendations)

        # Emit event to load recommendations into track list
        from pathlib import Path

        from jukebox.core.event_bus import Events

        # Convert to list of filepaths
        track_filepaths = [Path(track["filepath"]) for track in recommendations]
        self.context.emit(Events.LOAD_TRACK_LIST, filepaths=track_filepaths)

    def _get_recommendations(self, limit: int = 10) -> list[Any]:
        """Get track recommendations."""
        db = self.context.database

        # Get recently played tracks
        recent = db.conn.execute(
            """
            SELECT DISTINCT t.artist, t.genre
            FROM tracks t
            JOIN play_history ph ON t.id = ph.track_id
            WHERE ph.completed = 1
            ORDER BY ph.played_at DESC
            LIMIT 20
        """
        ).fetchall()

        if not recent:
            # No history, return random
            return db.conn.execute(
                f"SELECT * FROM tracks ORDER BY RANDOM() LIMIT {limit}"
            ).fetchall()

        # Get favorite artists and genres
        artists = [r["artist"] for r in recent if r["artist"]]
        genres = [r["genre"] for r in recent if r["genre"]]

        recommendations = []

        # Similar artists
        if artists:
            artist_sample = random.sample(artists, min(3, len(artists)))
            for artist in artist_sample:
                tracks = db.conn.execute(
                    """
                    SELECT * FROM tracks
                    WHERE artist = ?
                    AND id NOT IN (
                        SELECT track_id FROM play_history
                        WHERE played_at > datetime('now', '-7 days')
                    )
                    ORDER BY RANDOM()
                    LIMIT ?
                """,
                    (artist, limit // 3),
                ).fetchall()
                recommendations.extend(tracks)

        # Similar genres
        if genres and len(recommendations) < limit:
            genre_sample = random.sample(genres, min(2, len(genres)))
            for genre in genre_sample:
                tracks = db.conn.execute(
                    """
                    SELECT * FROM tracks
                    WHERE genre = ?
                    ORDER BY RANDOM()
                    LIMIT ?
                """,
                    (genre, (limit - len(recommendations)) // 2),
                ).fetchall()
                recommendations.extend(tracks)

        random.shuffle(recommendations)
        return recommendations[:limit]

    def shutdown(self) -> None:
        """Cleanup."""
        pass
