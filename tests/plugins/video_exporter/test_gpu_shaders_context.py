"""Tests for releasing the shared GL context (without depending on moderngl).

Covers ``release_shared_gl_context`` independently of the presence of the
OpenGL runtime: we inject doubles into the module's ``threading.local`` to
verify that the release is properly triggered and that the shared state is
reset (isolation between tests / processes).
"""

from __future__ import annotations

from typing import Any

import pytest

from plugins.video_exporter.layers import gpu_shaders


@pytest.fixture(autouse=True)
def _reset_thread_locals() -> Any:
    """Guarantee clean thread-locals before and after each test."""
    gpu_shaders._thread_local_gl.ctx = None
    gpu_shaders._gpu_renderer_local.renderers = {}
    yield
    gpu_shaders._thread_local_gl.ctx = None
    gpu_shaders._gpu_renderer_local.renderers = {}


def test_release_is_noop_without_context() -> None:
    """No context and no renderer: the call does not raise and stays idempotent."""
    gpu_shaders._thread_local_gl.ctx = None
    gpu_shaders._gpu_renderer_local.renderers = {}

    # Two successive calls: no exception, state still empty (idempotent).
    gpu_shaders.release_shared_gl_context()
    gpu_shaders.release_shared_gl_context()

    assert gpu_shaders._thread_local_gl.ctx is None
    assert gpu_shaders._gpu_renderer_local.renderers == {}


def test_release_cleans_renderers_and_context() -> None:
    """Renderers cleaned up, context released and thread-locals reset."""
    cleaned: list[str] = []

    class FakeRenderer:
        def cleanup(self) -> None:
            cleaned.append("cleanup")

    class FakeCtx:
        def __init__(self) -> None:
            self.released = False

        def release(self) -> None:
            self.released = True

    ctx = FakeCtx()
    gpu_shaders._thread_local_gl.ctx = ctx
    gpu_shaders._gpu_renderer_local.renderers = {(64, 64): FakeRenderer()}

    gpu_shaders.release_shared_gl_context()

    assert cleaned == ["cleanup"]
    assert ctx.released is True
    assert gpu_shaders._thread_local_gl.ctx is None
    assert gpu_shaders._gpu_renderer_local.renderers == {}


def test_release_swallows_context_release_error() -> None:
    """An error from ctx.release() is logged but does not propagate; state cleaned up."""

    class ExplodingCtx:
        def release(self) -> None:
            raise RuntimeError("contexte déjà libéré")

    gpu_shaders._thread_local_gl.ctx = ExplodingCtx()
    gpu_shaders._gpu_renderer_local.renderers = {}

    gpu_shaders.release_shared_gl_context()

    assert gpu_shaders._thread_local_gl.ctx is None
