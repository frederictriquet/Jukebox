"""Tests du shader GPU « Octagrams »."""

from __future__ import annotations

import pytest
from PIL import Image  # type: ignore[import-untyped]

from plugins.video_exporter.layers.gpu_shaders import (
    MODERNGL_AVAILABLE,
    GPUShaderRenderer,
)


@pytest.mark.skipif(not MODERNGL_AVAILABLE, reason="ModernGL absent")
def test_octagrams_shader_renders_rgba() -> None:
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
