"""Tests de libération du contexte GL partagé (sans dépendance à moderngl).

Couvre ``release_shared_gl_context`` indépendamment de la présence du runtime
OpenGL : on injecte des doubles dans les ``threading.local`` du module pour
vérifier que la libération est bien déclenchée et que l'état partagé est remis
à zéro (isolation entre tests / process).
"""

from __future__ import annotations

from typing import Any

import pytest

from plugins.video_exporter.layers import gpu_shaders


@pytest.fixture(autouse=True)
def _reset_thread_locals() -> Any:
    """Garantit des thread-locals propres avant et après chaque test."""
    gpu_shaders._thread_local_gl.ctx = None
    gpu_shaders._gpu_renderer_local.renderers = {}
    yield
    gpu_shaders._thread_local_gl.ctx = None
    gpu_shaders._gpu_renderer_local.renderers = {}


def test_release_is_noop_without_context() -> None:
    """Aucun contexte ni renderer : l'appel ne lève pas et reste idempotent."""
    gpu_shaders._thread_local_gl.ctx = None
    gpu_shaders._gpu_renderer_local.renderers = {}

    # Deux appels successifs : aucune exception, état toujours vide (idempotent).
    gpu_shaders.release_shared_gl_context()
    gpu_shaders.release_shared_gl_context()

    assert gpu_shaders._thread_local_gl.ctx is None
    assert gpu_shaders._gpu_renderer_local.renderers == {}


def test_release_cleans_renderers_and_context() -> None:
    """Renderers nettoyés, contexte libéré et thread-locals remis à zéro."""
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
    """Une erreur de ctx.release() est logguée mais ne propage pas; état nettoyé."""

    class ExplodingCtx:
        def release(self) -> None:
            raise RuntimeError("contexte déjà libéré")

    gpu_shaders._thread_local_gl.ctx = ExplodingCtx()
    gpu_shaders._gpu_renderer_local.renderers = {}

    gpu_shaders.release_shared_gl_context()

    assert gpu_shaders._thread_local_gl.ctx is None
