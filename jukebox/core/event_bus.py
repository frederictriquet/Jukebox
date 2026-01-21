"""Event bus for inter-plugin communication."""

import logging
from collections.abc import Callable
from typing import Any


class EventBus:
    """Event bus for pub/sub."""

    def __init__(self) -> None:
        """Initialize event bus."""
        self.subscribers: dict[str, list[Callable[..., None]]] = {}

    def subscribe(self, event: str, callback: Callable[..., None]) -> None:
        """Subscribe to event."""
        if event not in self.subscribers:
            self.subscribers[event] = []
        self.subscribers[event].append(callback)
        logging.debug(f"Subscribed to event: {event}")

    def unsubscribe(self, event: str, callback: Callable[..., None]) -> bool:
        """Unsubscribe from event.

        Args:
            event: Event name
            callback: Callback to remove

        Returns:
            True if unsubscribed, False if not found
        """
        if event not in self.subscribers:
            return False

        try:
            self.subscribers[event].remove(callback)
            logging.debug(f"Unsubscribed from event: {event}")
            return True
        except ValueError:
            return False

    def clear_all_subscribers(self) -> None:
        """Clear all subscribers from all events."""
        self.subscribers.clear()
        logging.debug("Cleared all event subscribers")

    def emit(self, event: str, **data: Any) -> None:
        """Emit event."""
        if event not in self.subscribers:
            return

        logging.debug(f"Emitting event: {event}")
        for callback in self.subscribers[event]:
            try:
                callback(**data)
            except Exception as e:
                logging.error(f"Error in event handler for {event}: {e}")


class Events:
    """Standard event names.

    Each event is documented with its expected kwargs.

    Track Events:
        TRACK_LOADED: Track loaded in player
            kwargs: track_id (int) - Database ID of the loaded track
        TRACK_PLAYING: Playback started
            kwargs: None
        TRACK_STOPPED: Playback stopped
            kwargs: None
        TRACKS_ADDED: Tracks added to library (triggers list refresh)
            kwargs: None
        TRACK_DELETED: Track removed from library
            kwargs: filepath (Path) - Path of the deleted track
        TRACK_METADATA_UPDATED: Track metadata changed (genre, rating, etc.)
            kwargs: filepath (Path) - Path of the updated track

    Navigation Events:
        SELECT_NEXT_TRACK: Request to select next track in list
            kwargs: None
        SELECT_PREVIOUS_TRACK: Request to select previous track in list
            kwargs: None
        SELECT_RANDOM_TRACK: Request to select random track from list
            kwargs: None

    Track List Events:
        LOAD_TRACK_LIST: Load specific tracks into the list
            kwargs: filepaths (list[Path]) - List of track filepaths to load
        SEARCH_PERFORMED: Search executed with results
            kwargs: results (list) - Search results

    UI Events:
        WAVEFORM_CLEAR: Clear waveform display
            kwargs: None
        POSITION_UPDATE: Playback position changed
            kwargs: position (float) - Position as ratio 0.0-1.0
        STATUS_MESSAGE: Display status message in status bar
            kwargs: message (str) - Message text
                    color (str, optional) - Hex color code (e.g., "#00FF00")

    Plugin Events:
        PLUGIN_SETTINGS_CHANGED: Plugin settings updated via conf_manager
            kwargs: None
        WAVEFORM_COMPLETE: Waveform generation finished for a track
            kwargs: track_id (int) - Database ID of the track
        AUDIO_ANALYSIS_COMPLETE: Audio analysis finished for a track
            kwargs: track_id (int) - Database ID of the track
    """

    # Track events
    TRACK_LOADED = "track_loaded"  # kwargs: track_id (int)
    TRACK_PLAYING = "track_playing"  # kwargs: None
    TRACK_STOPPED = "track_stopped"  # kwargs: None
    TRACKS_ADDED = "tracks_added"  # kwargs: None
    TRACK_DELETED = "track_deleted"  # kwargs: filepath (Path)
    TRACK_METADATA_UPDATED = "track_metadata_updated"  # kwargs: filepath (Path)

    # Navigation events
    SELECT_NEXT_TRACK = "select_next_track"  # kwargs: None
    SELECT_PREVIOUS_TRACK = "select_previous_track"  # kwargs: None
    SELECT_RANDOM_TRACK = "select_random_track"  # kwargs: None

    # Track list events
    LOAD_TRACK_LIST = "load_track_list"  # kwargs: filepaths (list[Path])
    SEARCH_PERFORMED = "search_performed"  # kwargs: results (list)

    # UI events
    WAVEFORM_CLEAR = "waveform_clear"  # kwargs: None
    POSITION_UPDATE = "position_update"  # kwargs: position (float)
    STATUS_MESSAGE = "status_message"  # kwargs: message (str), color (str, optional)

    # Plugin events
    PLUGIN_SETTINGS_CHANGED = "plugin_settings_changed"  # kwargs: None
    WAVEFORM_COMPLETE = "waveform_complete"  # kwargs: track_id (int)
    AUDIO_ANALYSIS_COMPLETE = "audio_analysis_complete"  # kwargs: track_id (int)
