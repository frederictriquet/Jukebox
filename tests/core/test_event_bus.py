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


class TestEventBusAdditional:
    """Additional tests for EventBus covering unsubscribe, clear, error handling, and re-entrancy."""

    def test_unsubscribe_existing_callback_returns_true(self) -> None:
        """Test that unsubscribing an existing callback returns True."""
        bus = EventBus()
        callback = lambda **d: None  # noqa: E731

        bus.subscribe("event", callback)
        result = bus.unsubscribe("event", callback)

        assert result is True

    def test_unsubscribe_removes_callback(self) -> None:
        """Test that unsubscribed callback is no longer called on emit."""
        bus = EventBus()
        calls: list[int] = []
        callback = lambda **d: calls.append(1)  # noqa: E731

        bus.subscribe("event", callback)
        bus.unsubscribe("event", callback)
        bus.emit("event")

        assert len(calls) == 0

    def test_unsubscribe_nonexistent_event_returns_false(self) -> None:
        """Test that unsubscribing from an event that was never subscribed returns False."""
        bus = EventBus()
        callback = lambda **d: None  # noqa: E731

        result = bus.unsubscribe("no_such_event", callback)

        assert result is False

    def test_unsubscribe_callback_not_in_list_returns_false(self) -> None:
        """Test that unsubscribing a callback that was never registered returns False."""
        bus = EventBus()
        registered = lambda **d: None  # noqa: E731
        unregistered = lambda **d: None  # noqa: E731

        bus.subscribe("event", registered)
        result = bus.unsubscribe("event", unregistered)

        assert result is False

    def test_clear_all_subscribers_removes_all(self) -> None:
        """Test that clear_all_subscribers empties all subscriptions."""
        bus = EventBus()
        calls: list[str] = []

        bus.subscribe("event_a", lambda **d: calls.append("a"))
        bus.subscribe("event_b", lambda **d: calls.append("b"))

        bus.clear_all_subscribers()

        bus.emit("event_a")
        bus.emit("event_b")

        assert len(calls) == 0
        assert bus.subscribers == {}

    def test_emit_continues_after_callback_raises(self) -> None:
        """Test that emit calls remaining callbacks even when one raises an exception."""
        bus = EventBus()
        calls: list[str] = []

        def bad_callback(**data: object) -> None:
            raise RuntimeError("intentional error")

        def good_callback(**data: object) -> None:
            calls.append("good")

        bus.subscribe("event", bad_callback)
        bus.subscribe("event", good_callback)

        # Should not propagate the exception
        bus.emit("event")

        assert calls == ["good"]

    def test_emit_error_does_not_propagate(self) -> None:
        """Test that exceptions raised inside callbacks do not propagate to caller."""
        bus = EventBus()

        def raising_callback(**data: object) -> None:
            raise ValueError("should be caught")

        bus.subscribe("event", raising_callback)

        # Must not raise
        try:
            bus.emit("event")
        except ValueError:
            assert False, "Exception should not propagate out of emit"

    def test_reentrant_subscribe_during_emit(self) -> None:
        """Test that a callback can subscribe to a new event during emit without error."""
        bus = EventBus()
        second_calls: list[int] = []

        def first_callback(**data: object) -> None:
            # Subscribe to a different event from within an emit callback
            bus.subscribe("second_event", lambda **d: second_calls.append(1))

        bus.subscribe("first_event", first_callback)
        bus.emit("first_event")

        # Now emit second_event — the callback registered during first emit must fire
        bus.emit("second_event")

        assert second_calls == [1]

    def test_reentrant_emit_same_event_uses_snapshot(self) -> None:
        """Test that callbacks added to the same event mid-emit are not called in that emit."""
        bus = EventBus()
        calls: list[str] = []

        def callback_a(**data: object) -> None:
            calls.append("a")
            # Register callback_b on the same event during the current emit
            bus.subscribe("event", lambda **d: calls.append("b"))

        bus.subscribe("event", callback_a)
        bus.emit("event")

        # Only "a" should have been called; "b" was added after the snapshot was taken
        assert calls == ["a"]

        # A second emit should now call both
        calls.clear()
        bus.emit("event")
        assert "a" in calls
        assert "b" in calls
