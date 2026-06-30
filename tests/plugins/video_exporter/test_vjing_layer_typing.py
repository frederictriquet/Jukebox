"""Runtime regression tests for the effects whose typing was fixed.

These tests lock down the behavior of the branches touched by the typing fixes
(removal of masking `# type: ignore`): no fix should change the rendering. Each
test explicitly exercises the branch concerned:
- explosion: color tuple unpacked in `fill=(*color, alpha)`;
- water / smoke: palette index `colors[int(color_idx) % len]`;
- hexgrid: floating `cx` position incremented per column;
- shockwave: wave coordinates read from the dict;
- nebula: lazy (re)creation of the coordinate grid;
- emission: palette LUT built then reused (cache).
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
    """Build a 64×64 layer enabling the effects whose typing was fixed."""
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
    """Build a complete render context, overridable."""
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
    """The preset must enable all the targeted effects (filtered by AVAILABLE_EFFECTS)."""
    assert set(EFFECTS) <= set(layer.active_effects)


def test_explosion_draws_color_tuple(layer: VJingLayer) -> None:
    """On a strong beat, the explosion draws particles (color tuple unpacking)."""
    img = layer.create_transparent_image()
    layer._render_explosion(img, frame_idx=0, time_pos=0.0, ctx=_ctx(is_beat=True, energy=0.9))

    assert layer.explosion_active is True
    assert len(layer.explosion_particles) == 100
    # The particles are at the center: at least one pixel was painted.
    assert img.getbbox() is not None
    assert img.mode == "RGBA"


def test_water_ripple_palette_index(layer: VJingLayer) -> None:
    """The ripple spawned on a beat is then drawn via the palette index."""
    img = layer.create_transparent_image()
    # 1st call: spawn a ripple (color_idx stored as float in the dict).
    layer._render_water(img, frame_idx=0, time_pos=0.0, ctx=_ctx(is_beat=True))
    assert len(layer.ripples) == 1
    # 2nd call: the ripple grows and is drawn -> colors[int(color_idx) % len].
    layer._render_water(img, frame_idx=1, time_pos=0.05, ctx=_ctx(is_beat=False))
    assert img.getbbox() is not None


def test_smoke_palette_index(layer: VJingLayer) -> None:
    """The smoke render spawns then draws particles via the palette index."""
    img = layer.create_transparent_image()
    layer._render_smoke(img, frame_idx=0, time_pos=0.0, ctx=_ctx())
    assert len(layer.smoke_particles) > 0
    assert img.getbbox() is not None


def test_hexgrid_float_column_position(layer: VJingLayer) -> None:
    """The hexgrid render iterates over columns via a floating position without crashing."""
    img = layer.create_transparent_image()
    layer._render_hexgrid(img, frame_idx=0, time_pos=0.0, ctx=_ctx())
    assert img.getbbox() is not None


def test_shockwave_uses_wave_center(layer: VJingLayer) -> None:
    """The shockwave spawns on a strong beat then reads the wave center from the dict."""
    img = layer.create_transparent_image()
    layer._render_shockwave(img, frame_idx=0, time_pos=0.0, ctx=_ctx(is_beat=True, bass=0.9))
    assert len(layer.shockwaves) == 1
    assert img.mode == "RGBA"
    assert img.size == (64, 64)


def test_nebula_lazy_grid_creation_and_reuse(layer: VJingLayer) -> None:
    """The nebula grid is created on the 1st render then reused (hasattr/.shape guard)."""
    img = layer.create_transparent_image()
    assert not hasattr(layer, "_nebula_xs")
    layer._render_nebula(img, frame_idx=0, time_pos=0.0, ctx=_ctx())
    assert hasattr(layer, "_nebula_xs")
    grid_first = layer._nebula_xs
    # 2nd render, same resolution: the grid is reused (not recreated).
    layer._render_nebula(img, frame_idx=1, time_pos=0.05, ctx=_ctx())
    assert layer._nebula_xs is grid_first
    assert img.getbbox() is not None


def test_emission_lut_built_then_cached(layer: VJingLayer) -> None:
    """The emission LUT is built on the 1st render (attribute absent) then cached."""
    img = layer.create_transparent_image()
    # _init_emission is never called: the attribute does not exist before the 1st render.
    assert not hasattr(layer, "_emission_lut")
    layer._render_emission(img, frame_idx=0, time_pos=0.0, ctx=_ctx())
    lut_first = layer._emission_lut
    assert lut_first is not None
    assert lut_first.shape == (512, 3)
    # 2nd render, same palette: the LUT is not rebuilt.
    layer._render_emission(img, frame_idx=1, time_pos=0.05, ctx=_ctx())
    assert layer._emission_lut is lut_first


def test_emission_lut_rebuilt_on_palette_change(layer: VJingLayer) -> None:
    """Changing palette forces the emission LUT to be rebuilt."""
    img = layer.create_transparent_image()
    layer._render_emission(img, frame_idx=0, time_pos=0.0, ctx=_ctx())
    lut_first = layer._emission_lut

    layer.color_palette_name = "fire"
    layer.color_palette = VJingLayer.COLOR_PALETTES["fire"]
    layer._render_emission(img, frame_idx=1, time_pos=0.05, ctx=_ctx())
    assert layer._emission_lut is not lut_first


@pytest.mark.parametrize("noise_fn", [perlin2d, simplex2d])
def test_noise_helpers_return_float(noise_fn: Any) -> None:
    """perlin2d/simplex2d return a Python float (untyped noise library)."""
    value = noise_fn(1.5, 2.5, octaves=2)
    assert isinstance(value, float)
    assert -2.0 <= value <= 2.0


def test_rms_energy_arrays_are_float(layer: VJingLayer) -> None:
    """The audio analysis (per-frame RMS) produces normalized float arrays."""
    assert layer.energy.dtype.kind == "f"
    assert layer.bass_energy.dtype.kind == "f"
    assert len(layer.energy) == layer.total_frames
