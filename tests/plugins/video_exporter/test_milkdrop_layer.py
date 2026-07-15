"""Tests for MilkDropLayer's texture search paths and dark-streak detection.

Only members with no dependency on the native libprojectM library are tested
here (__init__ loads libprojectM and can't be unit-tested without the real
shared library present). For the dark-streak logic, a bare instance is built
via object.__new__() to bypass __init__ entirely.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from plugins.video_exporter.layers.milkdrop_layer import MilkDropLayer


def _make_layer_stub(fps: int = 30) -> MilkDropLayer:
    """Build a MilkDropLayer without running __init__ (which loads libprojectM)."""
    layer = object.__new__(MilkDropLayer)
    layer.fps = fps
    layer._dark_frame_streak = 0
    return layer


def test_empty_preset_path_returns_no_search_paths() -> None:
    assert MilkDropLayer._texture_search_paths("") == []


def test_nonexistent_preset_path_returns_no_search_paths(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    assert MilkDropLayer._texture_search_paths(str(missing)) == []


def test_directory_without_textures_subfolder_returns_only_base_dir(tmp_path: Path) -> None:
    (tmp_path / "preset.milk").write_text("")

    assert MilkDropLayer._texture_search_paths(str(tmp_path)) == [str(tmp_path)]


def test_directory_with_textures_subfolder_includes_it(tmp_path: Path) -> None:
    textures_dir = tmp_path / "textures"
    textures_dir.mkdir()

    result = MilkDropLayer._texture_search_paths(str(tmp_path))

    assert result == [str(tmp_path), str(textures_dir)]


def test_directory_with_capitalized_textures_subfolder_includes_it(tmp_path: Path) -> None:
    textures_dir = tmp_path / "Textures"
    textures_dir.mkdir()

    result = MilkDropLayer._texture_search_paths(str(tmp_path))

    assert result == [str(tmp_path), str(textures_dir)]


def test_single_milk_file_resolves_to_its_parent_directory(tmp_path: Path) -> None:
    preset_file = tmp_path / "preset.milk"
    preset_file.write_text("")
    (tmp_path / "textures").mkdir()

    result = MilkDropLayer._texture_search_paths(str(preset_file))

    assert result == [str(tmp_path), str(tmp_path / "textures")]


def test_texture_path_is_searched_in_addition_to_preset_path(tmp_path: Path) -> None:
    """A separate texture pack (e.g. presets-milkdrop-texture-pack) adds its own paths."""
    preset_dir = tmp_path / "presets"
    preset_dir.mkdir()
    texture_pack_dir = tmp_path / "texture-pack"
    (texture_pack_dir / "textures").mkdir(parents=True)

    result = MilkDropLayer._texture_search_paths(str(preset_dir), str(texture_pack_dir))

    assert result == [str(preset_dir), str(texture_pack_dir), str(texture_pack_dir / "textures")]


def test_texture_path_defaults_to_empty_and_is_ignored(tmp_path: Path) -> None:
    """Omitting texture_path behaves exactly like passing an empty string."""
    preset_dir = tmp_path / "presets"
    preset_dir.mkdir()

    assert MilkDropLayer._texture_search_paths(
        str(preset_dir)
    ) == MilkDropLayer._texture_search_paths(str(preset_dir), "")


def test_texture_path_alone_without_preset_path(tmp_path: Path) -> None:
    """A texture pack can be configured even without (or independently of) preset_path."""
    texture_pack_dir = tmp_path / "texture-pack"
    texture_pack_dir.mkdir()

    result = MilkDropLayer._texture_search_paths("", str(texture_pack_dir))

    assert result == [str(texture_pack_dir)]


def test_same_directory_in_both_paths_is_not_duplicated(tmp_path: Path) -> None:
    """preset_path and texture_path pointing at the same folder don't produce duplicates."""
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()

    result = MilkDropLayer._texture_search_paths(str(shared_dir), str(shared_dir))

    assert result == [str(shared_dir)]


def test_mean_brightness_solid_black_is_zero() -> None:
    img = Image.new("RGB", (4, 4), (0, 0, 0))

    assert MilkDropLayer._mean_brightness(img) == 0.0


def test_mean_brightness_solid_white_is_255() -> None:
    img = Image.new("RGB", (4, 4), (255, 255, 255))

    assert MilkDropLayer._mean_brightness(img) == 255.0


def test_mean_brightness_ignores_alpha_channel() -> None:
    """RGBA input is fine: brightness is computed on RGB only, alpha is dropped."""
    img = Image.new("RGBA", (4, 4), (255, 255, 255, 0))

    assert MilkDropLayer._mean_brightness(img) == 255.0


def _dark_image() -> Image.Image:
    return Image.new("RGB", (4, 4), (0, 0, 0))


def _bright_image() -> Image.Image:
    return Image.new("RGB", (4, 4), (200, 200, 200))


def test_register_frame_brightness_increments_streak_on_dark_frame() -> None:
    layer = _make_layer_stub()

    layer._register_frame_brightness(MilkDropLayer._mean_brightness(_dark_image()))
    layer._register_frame_brightness(MilkDropLayer._mean_brightness(_dark_image()))

    assert layer._dark_frame_streak == 2


def test_register_frame_brightness_resets_streak_on_bright_frame() -> None:
    layer = _make_layer_stub()
    layer._dark_frame_streak = 5

    layer._register_frame_brightness(MilkDropLayer._mean_brightness(_bright_image()))

    assert layer._dark_frame_streak == 0


def test_dark_streak_not_exceeded_before_grace_period() -> None:
    """Even with a huge dark streak, frames_since_cut < fps blocks an early cut."""
    layer = _make_layer_stub(fps=30)
    layer._dark_frame_streak = 1000

    assert layer._dark_streak_exceeded(frames_since_cut=10) is False


def test_dark_streak_not_exceeded_before_streak_limit() -> None:
    """Past the grace period, but not dark long enough yet."""
    layer = _make_layer_stub(fps=30)
    layer._dark_frame_streak = 10  # well under 1.5s * 30fps = 45

    assert layer._dark_streak_exceeded(frames_since_cut=100) is False


def test_dark_streak_exceeded_once_both_conditions_met() -> None:
    layer = _make_layer_stub(fps=30)
    layer._dark_frame_streak = int(MilkDropLayer._DARK_STREAK_SECONDS * 30)

    assert layer._dark_streak_exceeded(frames_since_cut=100) is True
