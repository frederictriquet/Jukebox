"""Tests for event bus."""

from jukebox.core.event_bus import EventBus


class TestEventBus:
    """Test EventBus."""

    def test_subscribe_and_emit(self) -> None:
        """Test basic subscribe and emit."""
        bus = EventBus()
        result = []

        def callback(**data):  # type: ignore
            result.append(data)

        bus.subscribe("test_event", callback)
        bus.emit("test_event", value=42)

        assert len(result) == 1
        assert result[0]["value"] == 42

    def test_multiple_subscribers(self) -> None:
        """Test multiple subscribers to same event."""
        bus = EventBus()
        results = []

        bus.subscribe("event", lambda **d: results.append("a"))
        bus.subscribe("event", lambda **d: results.append("b"))

        bus.emit("event")

        assert len(results) == 2
        assert "a" in results
        assert "b" in results

    def test_emit_nonexistent_event(self) -> None:
        """Test emitting event with no subscribers."""
        bus = EventBus()
        bus.emit("nonexistent")  # Should not crash
