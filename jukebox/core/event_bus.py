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
