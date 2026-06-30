"""Tests for VideoExportWorker GPU/GL context teardown.

GPU pre-rendering allocates a native OpenGL context stored in a
``threading.local`` on the worker thread. The worker must release it
deterministically at the end of ``run()`` (success and failure paths alike)
instead of leaving it until interpreter finalization, where it can segfault.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from plugins.video_exporter.export_worker import VideoExportWorker


def _make_worker() -> VideoExportWorker:
    """Build a worker with a minimal config (no milkdrop, no real export)."""
    return VideoExportWorker(config={}, context=MagicMock())


def test_run_releases_gl_context_on_success(qapp: object) -> None:
    """A successful export releases the thread-local GL context in teardown."""
    worker = _make_worker()

    with (
        patch.object(worker, "_export_parallel") as mock_export,
        patch(
            "plugins.video_exporter.layers.gpu_shaders.release_shared_gl_context"
        ) as mock_release,
    ):
        worker.run()

    mock_export.assert_called_once()
    mock_release.assert_called_once()


def test_run_releases_gl_context_on_failure(qapp: object) -> None:
    """An export that raises still releases the GL context and emits an error."""
    worker = _make_worker()
    errors: list[str] = []
    worker.error.connect(errors.append)

    with (
        patch.object(worker, "_export_parallel", side_effect=RuntimeError("boom")),
        patch(
            "plugins.video_exporter.layers.gpu_shaders.release_shared_gl_context"
        ) as mock_release,
    ):
        worker.run()

    # The exception is reported (no silent failure) and the context is freed.
    assert errors == ["boom"]
    mock_release.assert_called_once()


def test_release_swallows_release_error(qapp: object) -> None:
    """A failure inside release_shared_gl_context is logged, never propagated."""
    worker = _make_worker()

    with (
        patch.object(worker, "_export_parallel"),
        patch(
            "plugins.video_exporter.layers.gpu_shaders.release_shared_gl_context",
            side_effect=RuntimeError("ctx already gone"),
        ) as mock_release,
    ):
        # Must not raise even though the release helper explodes.
        worker.run()

    mock_release.assert_called_once()
