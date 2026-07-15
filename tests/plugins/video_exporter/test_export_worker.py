"""Tests for VideoExportWorker GPU/GL context teardown and warmup dispatch.

GPU pre-rendering allocates a native OpenGL context stored in a
``threading.local`` on the worker thread. The worker must release it
deterministically at the end of ``run()`` (success and failure paths alike)
instead of leaving it until interpreter finalization, where it can segfault.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from plugins.video_exporter.export_worker import VideoExportWorker


def _make_worker() -> VideoExportWorker:
    """Build a worker with a minimal config (no milkdrop, no real export)."""
    return VideoExportWorker(config={}, context=MagicMock())


def _make_zero_length_config(*, milkdrop_enabled: bool) -> dict:
    """A config with loop_start == loop_end: total_frames == 0, so the actual
    ThreadPoolExecutor frame-rendering loop is a no-op and only the
    warmup/prerender dispatch logic under test runs.
    """
    return {
        "filepath": "/music/track.mp3",
        "loop_start": 0.0,
        "loop_end": 0.0,
        "width": 100,
        "height": 100,
        "fps": 30,
        "output_path": "/tmp/out.mp4",
        "layers": {"milkdrop_enabled": milkdrop_enabled},
        "track_metadata": {},
    }


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


def test_milkdrop_export_warms_up_instead_of_prerendering(qapp: object) -> None:
    """MilkDrop forces num_workers=1: render() is on-demand, so it must be warmed
    up first (regression test — this warmup call was previously missing
    entirely, leaving MilkDrop's very first exported frame rendered cold).
    """
    worker = VideoExportWorker(_make_zero_length_config(milkdrop_enabled=True), context=MagicMock())
    assert worker._num_workers == 1

    with (
        patch("librosa.load", return_value=(np.zeros(10), 44100)),
        patch("plugins.video_exporter.renderers.frame_renderer.FrameRenderer") as mock_renderer_cls,
        patch("plugins.video_exporter.renderers.ffmpeg_encoder.FFmpegEncoder"),
    ):
        mock_renderer = MagicMock()
        mock_renderer_cls.return_value = mock_renderer

        worker._export_parallel()

    mock_renderer.warmup_gpu.assert_called_once()
    mock_renderer.prerender_gpu.assert_not_called()


def test_non_milkdrop_export_prerenders_instead_of_warming_up(qapp: object) -> None:
    """Without MilkDrop, num_workers > 1: the existing prerender_gpu() path is unchanged."""
    worker = VideoExportWorker(
        _make_zero_length_config(milkdrop_enabled=False), context=MagicMock()
    )
    assert worker._num_workers > 1

    with (
        patch("librosa.load", return_value=(np.zeros(10), 44100)),
        patch("plugins.video_exporter.renderers.frame_renderer.FrameRenderer") as mock_renderer_cls,
        patch("plugins.video_exporter.renderers.ffmpeg_encoder.FFmpegEncoder"),
    ):
        mock_renderer = MagicMock()
        mock_renderer.prerender_gpu.return_value = 0
        mock_renderer_cls.return_value = mock_renderer

        worker._export_parallel()

    mock_renderer.prerender_gpu.assert_called_once()
    mock_renderer.warmup_gpu.assert_not_called()
