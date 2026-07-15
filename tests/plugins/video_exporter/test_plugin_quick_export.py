"""Tests for the Quick Export button of the video_exporter plugin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from jukebox.core.constants import StatusColors
from jukebox.core.event_bus import Events
from jukebox.ui.components.player_controls import PlayerControls
from plugins.video_exporter.plugin import VideoExporterPlugin

_TRACK_PATH = Path("/music/track.mp3")


class _FakeUIBuilder:
    """Minimal UIBuilder: actually inserts into the layout, mocks the rest.

    Mirrors the pattern used in tests/plugins/test_loop_player.py: the quick
    export button is placed via insert_widget_in_layout (real Qt layout, like
    loop_player's own button), while menu/toolbar plumbing is mocked out.
    """

    def insert_widget_in_layout(self, layout, index, widget) -> None:  # type: ignore[no-untyped-def]
        layout.insertWidget(index, widget)

    def add_toolbar_widget(self, widget) -> None:  # type: ignore[no-untyped-def]
        ...

    def get_or_create_menu(self, name):  # type: ignore[no-untyped-def]
        return Mock()

    def add_menu_action(self, *args, **kwargs) -> None: ...  # type: ignore[no-untyped-def]


def _make_plugin(qapp) -> tuple[VideoExporterPlugin, Mock]:  # type: ignore[no-untyped-def]
    """Build and register a VideoExporterPlugin on a real PlayerControls bar.

    Returns the plugin together with the raw context mock so tests can assert
    on it directly (going through `plugin.context`, typed as
    `PluginContextProtocol`, would hide the Mock's assertion helpers from mypy).
    """
    controls = PlayerControls()
    main_window = Mock()
    main_window.controls = controls

    context = Mock()
    context.app = main_window

    plugin = VideoExporterPlugin()
    plugin.context = context
    # _FakeUIBuilder only implements the subset of UIBuilderProtocol this
    # plugin actually calls, not the full surface (add_menu, add_sidebar_widget, ...).
    plugin.register_ui(_FakeUIBuilder())  # type: ignore[arg-type]
    return plugin, context


def test_buttons_hidden_by_default(qapp) -> None:  # type: ignore[no-untyped-def]
    """Both export buttons are hidden until a loop is active."""
    plugin, _context = _make_plugin(qapp)

    assert plugin.export_button is not None
    assert plugin.quick_export_button is not None
    assert plugin.export_button.isHidden() is True
    assert plugin.quick_export_button.isHidden() is True


def test_quick_export_button_placed_in_player_controls(qapp) -> None:  # type: ignore[no-untyped-def]
    """The quick export button lives in the controls bar, next to the loop button.

    Regression test: it must NOT rely on the toolbar (add_toolbar_widget),
    which turned out to render invisibly in the real app.
    """
    plugin, context = _make_plugin(qapp)

    controls_layout = context.app.controls.layout()
    found = any(
        controls_layout.itemAt(i)
        and controls_layout.itemAt(i).widget() is plugin.quick_export_button
        for i in range(controls_layout.count())
    )
    assert found


def test_buttons_shown_on_loop_activated(qapp) -> None:  # type: ignore[no-untyped-def]
    """Both export buttons appear together when the loop activates."""
    plugin, _context = _make_plugin(qapp)

    plugin._on_loop_activated(loop_start=10.0, loop_end=40.0, filepath=_TRACK_PATH)

    assert plugin.quick_export_button is not None
    assert plugin.export_button is not None
    assert plugin.quick_export_button.isHidden() is False
    assert plugin.export_button.isHidden() is False


def test_buttons_hidden_on_loop_deactivated(qapp) -> None:  # type: ignore[no-untyped-def]
    """Both export buttons hide together when the loop deactivates."""
    plugin, _context = _make_plugin(qapp)
    plugin._on_loop_activated(loop_start=10.0, loop_end=40.0, filepath=_TRACK_PATH)

    plugin._on_loop_deactivated()

    assert plugin.quick_export_button is not None
    assert plugin.export_button is not None
    assert plugin.quick_export_button.isHidden() is True
    assert plugin.export_button.isHidden() is True


def test_buttons_hidden_on_track_loaded(qapp) -> None:  # type: ignore[no-untyped-def]
    """A new track resets the loop state and hides both buttons."""
    plugin, _context = _make_plugin(qapp)
    plugin._on_loop_activated(loop_start=10.0, loop_end=40.0, filepath=_TRACK_PATH)

    plugin._on_track_loaded(track_id=7)

    assert plugin.quick_export_button is not None
    assert plugin.export_button is not None
    assert plugin.quick_export_button.isHidden() is True
    assert plugin.export_button.isHidden() is True


def test_quick_export_without_active_loop_warns_and_skips(qapp) -> None:  # type: ignore[no-untyped-def]
    """Clicking Quick Export with no active loop emits a warning, no worker is started."""
    plugin, context = _make_plugin(qapp)

    with patch("plugins.video_exporter.plugin.QuickExportWorker") as mock_worker_cls:
        plugin._quick_export()

    mock_worker_cls.assert_not_called()
    context.emit.assert_called_once_with(
        Events.STATUS_MESSAGE,
        message="No active loop to export",
        color=StatusColors.WARNING_ALT,
    )


def test_quick_export_track_not_found_skips_silently(qapp) -> None:  # type: ignore[no-untyped-def]
    """A track missing from the DB skips the export without a status message."""
    plugin, context = _make_plugin(qapp)
    plugin._on_loop_activated(loop_start=10.0, loop_end=40.0, filepath=_TRACK_PATH)
    context.database.tracks.get_by_filepath.return_value = None
    context.reset_mock()

    with patch("plugins.video_exporter.plugin.QuickExportWorker") as mock_worker_cls:
        plugin._quick_export()

    mock_worker_cls.assert_not_called()
    context.emit.assert_not_called()


def test_quick_export_starts_worker_with_expected_record(qapp) -> None:  # type: ignore[no-untyped-def]
    """The happy path builds the minimal record and starts the worker."""
    plugin, context = _make_plugin(qapp)
    plugin._on_loop_activated(loop_start=10.0, loop_end=40.0, filepath=_TRACK_PATH)
    context.database.tracks.get_by_filepath.return_value = {"id": 42}
    context.config.video_exporter.output_directory = "/videos"

    with patch("plugins.video_exporter.plugin.QuickExportWorker") as mock_worker_cls:
        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        plugin._quick_export()

        args, _kwargs = mock_worker_cls.call_args
        jsonl_path, record = args
        assert str(jsonl_path) == "/videos/quick_exports.jsonl"
        assert record.track_id == 42
        assert record.filepath == "/music/track.mp3"
        assert record.loop_start == 10.0
        assert record.loop_end == 40.0
        assert record.exported_at
        mock_worker.start.assert_called_once()


def test_on_quick_export_finished_emits_success(qapp) -> None:  # type: ignore[no-untyped-def]
    """The finished handler reports success and keeps the worker reference alive.

    The reference must NOT be dropped here: this slot runs on the custom
    ``finished`` signal emitted from inside ``run()``, before the QThread has
    actually terminated. Releasing it here destroys a still-running QThread.
    """
    plugin, context = _make_plugin(qapp)
    worker = Mock()
    plugin._quick_export_worker = worker

    plugin._on_quick_export_finished()

    context.emit.assert_called_once_with(
        Events.STATUS_MESSAGE,
        message="Loop info saved for video export",
        color=StatusColors.SUCCESS,
    )
    assert plugin._quick_export_worker is worker


def test_on_quick_export_error_emits_failure(qapp) -> None:  # type: ignore[no-untyped-def]
    """The error handler reports the failure and keeps the worker reference alive."""
    plugin, context = _make_plugin(qapp)
    worker = Mock()
    plugin._quick_export_worker = worker

    plugin._on_quick_export_error("disk full")

    context.emit.assert_called_once_with(
        Events.STATUS_MESSAGE,
        message="Quick export failed: disk full",
        color=StatusColors.ERROR,
    )
    assert plugin._quick_export_worker is worker


def test_quick_export_waits_for_in_flight_worker_before_relaunch(qapp) -> None:  # type: ignore[no-untyped-def]
    """Relaunching while a worker is still running waits before dropping it."""
    plugin, context = _make_plugin(qapp)
    plugin._on_loop_activated(loop_start=10.0, loop_end=40.0, filepath=_TRACK_PATH)
    context.database.tracks.get_by_filepath.return_value = {"id": 42}
    context.config.video_exporter.output_directory = "/videos"

    running_worker = Mock()
    running_worker.isRunning.return_value = True
    plugin._quick_export_worker = running_worker

    with patch("plugins.video_exporter.plugin.QuickExportWorker"):
        plugin._quick_export()

    running_worker.wait.assert_called_once()


def test_shutdown_waits_for_running_worker(qapp) -> None:  # type: ignore[no-untyped-def]
    """Shutdown waits for a running worker and releases the reference."""
    plugin, _context = _make_plugin(qapp)
    worker = Mock()
    worker.isRunning.return_value = True
    plugin._quick_export_worker = worker

    plugin.shutdown()

    worker.wait.assert_called_once()
    assert plugin._quick_export_worker is None


def test_shutdown_skips_wait_for_finished_worker(qapp) -> None:  # type: ignore[no-untyped-def]
    """Shutdown does not wait on an already-finished worker but still releases it."""
    plugin, _context = _make_plugin(qapp)
    worker = Mock()
    worker.isRunning.return_value = False
    plugin._quick_export_worker = worker

    plugin.shutdown()

    worker.wait.assert_not_called()
    assert plugin._quick_export_worker is None
