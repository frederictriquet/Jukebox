"""Recommendations plugin."""

from __future__ import annotations

import random
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jukebox.core.event_bus import Events

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol, UIBuilderProtocol


class RecommendationsPlugin:
    """Recommend tracks based on history."""

    name = "recommendations"
    version = "1.0.0"
    description = "Get track recommendations"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: PluginContextProtocol = None  # type: ignore[assignment]

    def initialize(self, context: PluginContextProtocol) -> None:
        """Initialize plugin."""
        self.context = context

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register UI."""
        menu = ui_builder.get_or_create_menu("&Library")
        ui_builder.add_menu_action(menu, "Recommendations...", self._show_recommendations)

    def _show_recommendations(self) -> None:
        """Show recommended tracks."""
        recommendations = self._get_recommendations(limit=20)

        # Update UI with recommendations
        self.context.emit(Events.SEARCH_PERFORMED, results=recommendations)

        # Emit event to load recommendations into track list
        track_filepaths = [Path(track["filepath"]) for track in recommendations]
        self.context.emit(Events.LOAD_TRACK_LIST, filepaths=track_filepaths)

    def _get_recommendations(self, limit: int = 10) -> list[Any]:
        """Get track recommendations."""
        tracks_repo = self.context.database.tracks

        # (artist, genre) pairs from recently finished tracks.
        recent = tracks_repo.get_recently_played_artists_genres(limit=20)

        if not recent:
            # No history: random recommendations.
            return tracks_repo.get_random(limit)

        # Favorite artists and genres inferred from the history.
        artists = [r["artist"] for r in recent if r["artist"]]
        genres = [r["genre"] for r in recent if r["genre"]]

        recommendations = []

        # Tracks from similar artists not played recently.
        if artists:
            artist_sample = random.sample(artists, min(3, len(artists)))
            for artist in artist_sample:
                recommendations.extend(
                    tracks_repo.get_random_by_artist_unplayed(artist, limit // 3)
                )

        # Tracks from similar genres.
        if genres and len(recommendations) < limit:
            genre_sample = random.sample(genres, min(2, len(genres)))
            for genre in genre_sample:
                recommendations.extend(
                    tracks_repo.get_random_by_genre(genre, (limit - len(recommendations)) // 2)
                )

        random.shuffle(recommendations)
        return recommendations[:limit]

    def shutdown(self) -> None:
        """Cleanup on application exit. No cleanup needed for this plugin."""
        ...
