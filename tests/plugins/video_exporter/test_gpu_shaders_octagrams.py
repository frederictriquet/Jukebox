"""Tests du shader GPU « Octagrams ».

Le rendu GPU crée un contexte OpenGL natif (CGL/NSOpenGL sur macOS) via
``moderngl.create_standalone_context()``, mémorisé dans un ``threading.local``
partagé entre layers. Laissé vivant jusqu'à la finalisation de l'interpréteur,
ce contexte peut segfaulter au milieu des finaliseurs natifs exécutés dans un
ordre non déterministe (moderngl / numpy / scipy).

La fixture ``gl_context_cleanup`` libère donc explicitement le contexte (et les
renderers du thread) en teardown via ``release_shared_gl_context`` : la
ressource native est détruite de façon déterministe, pendant que l'état Python
est encore cohérent, plutôt qu'à l'arrêt du process. Aucun test n'est masqué.

Note : l'isolation par ``pytest-forked`` a été écartée — ``fork()`` après
initialisation de Qt/CoreFoundation abort sur macOS (signal 5).
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
    """Libère le contexte GL partagé du thread après le test."""
    yield
    release_shared_gl_context()


@pytest.mark.skipif(not MODERNGL_AVAILABLE, reason="ModernGL absent")
def test_octagrams_shader_renders_rgba(gl_context_cleanup: None) -> None:
    """Vérifie que le shader octagrams est compilé et rend une image RGBA."""
    renderer = GPUShaderRenderer(64, 64)
    if not renderer.available:
        pytest.skip("Contexte GPU indisponible dans cet environnement")

    # Le shader doit être compilé et enregistré
    assert renderer.has_shader("octagrams")

    img = renderer.render("octagrams", time_pos=1.0)
    assert img is not None
    assert isinstance(img, Image.Image)
    assert img.mode == "RGBA"
    assert img.size == (64, 64)

    renderer.cleanup()
