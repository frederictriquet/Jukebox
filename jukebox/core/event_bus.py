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
    """Standard event names."""

    TRACK_LOADED = "track_loaded"
    TRACK_PLAYING = "track_playing"
    TRACK_STOPPED = "track_stopped"
    TRACKS_ADDED = "tracks_added"
    TRACK_DELETED = "track_deleted"
    SEARCH_PERFORMED = "search_performed"

    # Navigation events
    SELECT_NEXT_TRACK = "select_next_track"
    SELECT_PREVIOUS_TRACK = "select_previous_track"
    SELECT_RANDOM_TRACK = "select_random_track"

    # Track list manipulation events
    LOAD_TRACK_LIST = "load_track_list"  # Load specific tracks into the list

    # UI events
    WAVEFORM_CLEAR = "waveform_clear"  # Clear waveform display
    POSITION_UPDATE = "position_update"  # Playback position changed
    STATUS_MESSAGE = "status_message"  # Display status message

    # Plugin events
    PLUGIN_SETTINGS_CHANGED = "plugin_settings_changed"  # Plugin settings updated
    AUDIO_ANALYSIS_COMPLETE = "audio_analysis_complete"  # Track analysis finished
    TRACK_METADATA_UPDATED = "track_metadata_updated"  # Track metadata changed
