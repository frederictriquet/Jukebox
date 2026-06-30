"""Tests de régression runtime des effets dont le typage a été corrigé.

Ces tests verrouillent le comportement des branches touchées par les corrections
de typage (suppression de `# type: ignore` masquants) : aucune correction ne doit
changer le rendu. Chaque test exerce explicitement la branche concernée :
- explosion : tuple couleur déballé dans `fill=(*color, alpha)` ;
- water / smoke : index de palette `colors[int(color_idx) % len]` ;
- hexgrid : position `cx` flottante incrémentée par colonne ;
- shockwave : coordonnées de vague lues depuis le dict ;
- nebula : (re)création paresseuse de la grille de coordonnées ;
- emission : LUT de palette construite puis réutilisée (cache).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from plugins.video_exporter.layers.vjing_layer import (
    VJingLayer,
    perlin2d,
    simplex2d,
)

EFFECTS = ["explosion", "water", "smoke", "shockwave", "hexgrid", "nebula", "emission"]


@pytest.fixture
def layer() -> VJingLayer:
    """Construit un layer 64×64 activant les effets dont le typage a été corrigé."""
    sr = 22050
    audio = np.zeros(sr, dtype=np.float32)
    return VJingLayer(
        width=64,
        height=64,
        fps=30,
        audio=audio,
        sr=sr,
        duration=1.0,
        preset="typing",
        presets={"typing": EFFECTS},
        use_gpu=False,
        rng_seed=42,
    )


def _ctx(**overrides: Any) -> dict[str, Any]:
    """Construit un contexte de rendu complet, surchargeable."""
    ctx: dict[str, Any] = {
        "energy": 0.8,
        "bass": 0.8,
        "mid": 0.5,
        "treble": 0.3,
        "fft": np.linspace(1.0, 0.0, 32, dtype=np.float32),
        "is_beat": False,
    }
    ctx.update(overrides)
    return ctx


def test_active_effects_contain_expected(layer: VJingLayer) -> None:
    """Le preset doit activer tous les effets ciblés (filtrés par AVAILABLE_EFFECTS)."""
    assert set(EFFECTS) <= set(layer.active_effects)


def test_explosion_draws_color_tuple(layer: VJingLayer) -> None:
    """Sur un beat fort, l'explosion dessine des particules (déballage tuple couleur)."""
    img = layer.create_transparent_image()
    layer._render_explosion(img, frame_idx=0, time_pos=0.0, ctx=_ctx(is_beat=True, energy=0.9))

    assert layer.explosion_active is True
    assert len(layer.explosion_particles) == 100
    # Les particules sont au centre : au moins un pixel a été peint.
    assert img.getbbox() is not None
    assert img.mode == "RGBA"


def test_water_ripple_palette_index(layer: VJingLayer) -> None:
    """Le ripple spawné sur un beat est ensuite dessiné via l'index de palette."""
    img = layer.create_transparent_image()
    # 1er appel : spawn d'un ripple (color_idx stocké comme float dans le dict).
    layer._render_water(img, frame_idx=0, time_pos=0.0, ctx=_ctx(is_beat=True))
    assert len(layer.ripples) == 1
    # 2e appel : le ripple grossit et est dessiné -> colors[int(color_idx) % len].
    layer._render_water(img, frame_idx=1, time_pos=0.05, ctx=_ctx(is_beat=False))
    assert img.getbbox() is not None


def test_smoke_palette_index(layer: VJingLayer) -> None:
    """Le rendu smoke spawne puis dessine des particules via l'index de palette."""
    img = layer.create_transparent_image()
    layer._render_smoke(img, frame_idx=0, time_pos=0.0, ctx=_ctx())
    assert len(layer.smoke_particles) > 0
    assert img.getbbox() is not None


def test_hexgrid_float_column_position(layer: VJingLayer) -> None:
    """Le rendu hexgrid parcourt les colonnes via une position flottante sans crash."""
    img = layer.create_transparent_image()
    layer._render_hexgrid(img, frame_idx=0, time_pos=0.0, ctx=_ctx())
    assert img.getbbox() is not None


def test_shockwave_uses_wave_center(layer: VJingLayer) -> None:
    """Le shockwave spawne sur un beat fort puis lit le centre de vague depuis le dict."""
    img = layer.create_transparent_image()
    layer._render_shockwave(img, frame_idx=0, time_pos=0.0, ctx=_ctx(is_beat=True, bass=0.9))
    assert len(layer.shockwaves) == 1
    assert img.mode == "RGBA"
    assert img.size == (64, 64)


def test_nebula_lazy_grid_creation_and_reuse(layer: VJingLayer) -> None:
    """La grille nebula est créée au 1er rendu puis réutilisée (garde hasattr/.shape)."""
    img = layer.create_transparent_image()
    assert not hasattr(layer, "_nebula_xs")
    layer._render_nebula(img, frame_idx=0, time_pos=0.0, ctx=_ctx())
    assert hasattr(layer, "_nebula_xs")
    grid_first = layer._nebula_xs
    # 2e rendu, même résolution : la grille est réutilisée (pas recréée).
    layer._render_nebula(img, frame_idx=1, time_pos=0.05, ctx=_ctx())
    assert layer._nebula_xs is grid_first
    assert img.getbbox() is not None


def test_emission_lut_built_then_cached(layer: VJingLayer) -> None:
    """La LUT emission est construite au 1er rendu (attribut absent) puis mise en cache."""
    img = layer.create_transparent_image()
    # _init_emission n'est jamais appelé : l'attribut n'existe pas avant le 1er rendu.
    assert not hasattr(layer, "_emission_lut")
    layer._render_emission(img, frame_idx=0, time_pos=0.0, ctx=_ctx())
    lut_first = layer._emission_lut
    assert lut_first is not None
    assert lut_first.shape == (512, 3)
    # 2e rendu, même palette : la LUT n'est pas reconstruite.
    layer._render_emission(img, frame_idx=1, time_pos=0.05, ctx=_ctx())
    assert layer._emission_lut is lut_first


def test_emission_lut_rebuilt_on_palette_change(layer: VJingLayer) -> None:
    """Changer de palette force la reconstruction de la LUT emission."""
    img = layer.create_transparent_image()
    layer._render_emission(img, frame_idx=0, time_pos=0.0, ctx=_ctx())
    lut_first = layer._emission_lut

    layer.color_palette_name = "fire"
    layer.color_palette = VJingLayer.COLOR_PALETTES["fire"]
    layer._render_emission(img, frame_idx=1, time_pos=0.05, ctx=_ctx())
    assert layer._emission_lut is not lut_first


@pytest.mark.parametrize("noise_fn", [perlin2d, simplex2d])
def test_noise_helpers_return_float(noise_fn: Any) -> None:
    """perlin2d/simplex2d renvoient un float Python (bibliothèque noise non typée)."""
    value = noise_fn(1.5, 2.5, octaves=2)
    assert isinstance(value, float)
    assert -2.0 <= value <= 2.0


def test_rms_energy_arrays_are_float(layer: VJingLayer) -> None:
    """L'analyse audio (RMS par frame) produit des tableaux flottants normalisés."""
    assert layer.energy.dtype.kind == "f"
    assert layer.bass_energy.dtype.kind == "f"
    assert len(layer.energy) == layer.total_frames
