"""Tests for the GPU shader "Octagrams".

GPU rendering creates a native OpenGL context (CGL/NSOpenGL on macOS) via
``moderngl.create_standalone_context()``, stored in a ``threading.local``
shared between layers. Left alive until interpreter finalization, this context
can segfault in the middle of the native finalizers, which run in a
non-deterministic order (moderngl / numpy / scipy).

The ``gl_context_cleanup`` fixture therefore explicitly releases the context
(and the thread's renderers) at teardown via ``release_shared_gl_context``: the
native resource is destroyed deterministically, while the Python state is still
consistent, rather than at process shutdown. No test is masked.

Note: isolation via ``pytest-forked`` was ruled out — ``fork()`` after
Qt/CoreFoundation initialization aborts on macOS (signal 5).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PIL import Image

from plugins.video_exporter.layers.gpu_shaders import (
    MODERNGL_AVAILABLE,
    GPUShaderRenderer,
    release_shared_gl_context,
)


@pytest.fixture
def gl_context_cleanup() -> Iterator[None]:
    """Release the thread's shared GL context after the test."""
    yield
    release_shared_gl_context()


@pytest.mark.skipif(not MODERNGL_AVAILABLE, reason="ModernGL absent")
def test_octagrams_shader_renders_rgba(gl_context_cleanup: None) -> None:
    """Verify that the octagrams shader is compiled and renders an RGBA image."""
    renderer = GPUShaderRenderer(64, 64)
    if not renderer.available:
        pytest.skip("Contexte GPU indisponible dans cet environnement")

    # The shader must be compiled and registered
    assert renderer.has_shader("octagrams")

    img = renderer.render("octagrams", time_pos=1.0)
    assert img is not None
    assert isinstance(img, Image.Image)
    assert img.mode == "RGBA"
    assert img.size == (64, 64)

    renderer.cleanup()
