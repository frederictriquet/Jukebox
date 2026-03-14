"""DB config takes priority over config.yaml — unified tests for ALL plugins.

One principle: when a setting is saved in DB, the plugin MUST use the DB value.
This file tests that principle generically across all plugins, regardless of
whether they use ShortcutMixin (file_manager, genre_editor) or direct reload
(loop_player, playback_navigation, waveform_visualizer, video_exporter).

Sections:
  1. Scalar settings — parametrized (override, fallback, hot reload)
  2. Complex settings — JSON-serialized (destinations, genre_codes)
  3. Combined — all settings from DB at once
  4. Timing gap — ShortcutMixin plugins delay DB load until register_shortcuts()
  5. Behavioral — shortcuts/callbacks use DB values, not yaml
  6. Edge cases — FFmpeg not synced, waveform widget resize
"""

import json
from unittest.mock import MagicMock

import pytest

from jukebox.core.config import (
    FileManagerConfig,
    FileManagerDestinationConfig,
    GenreCodeConfig,
    GenreEditorConfig,
    LoopPlayerConfig,
    PlaybackNavigationConfig,
    VideoExporterConfig,
    WaveformConfig,
)

from .conftest import FakeSettingsStore, make_plugin, make_plugin_context, make_shortcut_manager

# ============================================================================
# Plugin specs (module, class, config_attr, config_class)
# ============================================================================

_FM = ("plugins.file_manager", "FileManagerPlugin", "file_manager", FileManagerConfig)
_GE = ("plugins.genre_editor", "GenreEditorPlugin", "genre_editor", GenreEditorConfig)
_LP = ("plugins.loop_player", "LoopPlayerPlugin", "loop_player", LoopPlayerConfig)
_PN = (
    "plugins.playback_navigation",
    "PlaybackNavigationPlugin",
    "playback_navigation",
    PlaybackNavigationConfig,
)
_WV = ("plugins.waveform_visualizer", "WaveformVisualizerPlugin", "waveform", WaveformConfig)
_VE = (
    "plugins.video_exporter.plugin",
    "VideoExporterPlugin",
    "video_exporter",
    VideoExporterConfig,
)


# ============================================================================
# 1. Scalar settings — parametrized
# ============================================================================

# (module, class, cfg_attr, cfg_cls, field, yaml_val, db_str, expected_db_val)
SETTINGS = [
    # --- file_manager (ShortcutMixin) ---
    (*_FM, "trash_directory", "~/yaml-trash", "/db-trash", "/db-trash"),
    (*_FM, "trash_key", "Delete", "Backspace", "Backspace"),
    # --- genre_editor (ShortcutMixin) ---
    (*_GE, "rating_key", "*", "!", "!"),
    # --- loop_player ---
    (*_LP, "duration", 30.0, "15.0", 15.0),
    (*_LP, "coarse_step", 1.0, "2.5", 2.5),
    (*_LP, "fine_step", 0.1, "0.05", 0.05),
    # --- playback_navigation ---
    (*_PN, "seek_amount", 10.0, "5", 5),
    (*_PN, "rapid_press_threshold", 0.5, "300", 0.3),  # ms in DB → seconds
    (*_PN, "max_seek_multiplier", 5, "8", 8),
    # --- waveform_visualizer ---
    (*_WV, "chunk_duration", 10.0, "20", 20),
    (*_WV, "height", 120, "80", 80),
    # --- video_exporter: strings ---
    (*_VE, "default_resolution", "1080p", "720p", "720p"),
    (*_VE, "output_directory", "~/Videos/Jukebox", "/data/exports", "/data/exports"),
    (*_VE, "video_clips_folder", "", "/data/clips", "/data/clips"),
    (*_VE, "waveform_bass_color", "#0066FF", "#FF0000", "#FF0000"),
    (*_VE, "waveform_mid_color", "#00FF00", "#AABBCC", "#AABBCC"),
    (*_VE, "waveform_treble_color", "#FFFFFF", "#112233", "#112233"),
    (*_VE, "waveform_cursor_color", "#FFFFFF", "#AAAAAA", "#AAAAAA"),
    # --- video_exporter: int ---
    (*_VE, "default_fps", 30, "60", 60),
    # --- video_exporter: float ---
    (*_VE, "waveform_height_ratio", 0.3, "0.5", 0.5),
    # --- video_exporter: booleans ---
    (*_VE, "waveform_enabled", True, "false", False),
    (*_VE, "text_enabled", True, "false", False),
    (*_VE, "dynamics_enabled", True, "false", False),
    (*_VE, "vjing_enabled", False, "true", True),
    (*_VE, "video_background_enabled", False, "true", True),
]


def _setting_id(case: tuple) -> str:
    return f"{case[1].replace('Plugin', '')}.{case[4]}"


@pytest.mark.parametrize(
    "module,cls_name,cfg_attr,cfg_cls,field,yaml_val,db_str,expected",
    SETTINGS,
    ids=[_setting_id(c) for c in SETTINGS],
)
class TestDbConfigPriority:
    """For each setting: DB overrides yaml, yaml is fallback, hot reload works."""

    def test_db_overrides_yaml(
        self, module, cls_name, cfg_attr, cfg_cls, field, yaml_val, db_str, expected,
    ) -> None:
        plugin, _ = make_plugin(
            module, cls_name, cfg_attr, cfg_cls,
            yaml_kwargs={field: yaml_val}, db_settings={field: db_str},
        )
        actual = getattr(getattr(plugin.context.config, cfg_attr), field)
        assert actual == expected

    def test_falls_back_to_yaml(
        self, module, cls_name, cfg_attr, cfg_cls, field, yaml_val, db_str, expected,
    ) -> None:
        plugin, _ = make_plugin(
            module, cls_name, cfg_attr, cfg_cls,
            yaml_kwargs={field: yaml_val},
        )
        actual = getattr(getattr(plugin.context.config, cfg_attr), field)
        assert actual == yaml_val

    def test_hot_reload(
        self, module, cls_name, cfg_attr, cfg_cls, field, yaml_val, db_str, expected,
    ) -> None:
        plugin, store = make_plugin(
            module, cls_name, cfg_attr, cfg_cls,
            yaml_kwargs={field: yaml_val},
        )
        actual = getattr(getattr(plugin.context.config, cfg_attr), field)
        assert actual == yaml_val

        store.save(plugin.name, field, db_str)
        plugin._on_settings_changed()

        actual = getattr(getattr(plugin.context.config, cfg_attr), field)
        assert actual == expected


# ============================================================================
# 2. Complex settings — JSON-serialized lists
# ============================================================================


def _yaml_dests(*dests: tuple[str, str, str]) -> dict:
    """Build yaml_kwargs for FileManagerConfig with destinations."""
    return {
        "destinations": [
            FileManagerDestinationConfig(name=n, path=p, key=k) for n, p, k in dests
        ],
    }


def _db_dests(*dests: tuple[str, str, str]) -> dict[str, str]:
    """Build db_settings with JSON-serialized destinations."""
    return {
        "destinations": json.dumps(
            [{"name": n, "path": p, "key": k} for n, p, k in dests]
        ),
    }


def _yaml_codes(*codes: tuple[str, str, str]) -> dict:
    """Build yaml_kwargs for GenreEditorConfig with codes."""
    return {"codes": [GenreCodeConfig(key=k, code=c, name=n) for k, c, n in codes]}


def _db_codes(*codes: tuple[str, str, str]) -> dict[str, str]:
    """Build db_settings with JSON-serialized genre_codes."""
    return {
        "genre_codes": json.dumps(
            [{"key": k, "code": c, "name": n} for k, c, n in codes]
        ),
    }


class TestFileManagerDestinationsFromDb:
    """Destinations (JSON-serialized list) from DB override config.yaml."""

    def test_db_overrides_yaml(self) -> None:
        plugin, _ = make_plugin(
            *_FM,
            yaml_kwargs=_yaml_dests(("Good", "~/yaml", "@")),
            db_settings=_db_dests(("Good", "/db", "@")),
        )
        assert plugin.context.config.file_manager.destinations[0].path == "/db"

    def test_falls_back_to_yaml(self) -> None:
        plugin, _ = make_plugin(*_FM, yaml_kwargs=_yaml_dests(("Good", "~/yaml", "@")))
        assert plugin.context.config.file_manager.destinations[0].path == "~/yaml"

    def test_hot_reload(self) -> None:
        plugin, store = make_plugin(
            *_FM, yaml_kwargs=_yaml_dests(("Good", "~/yaml", "@")),
        )
        assert plugin.context.config.file_manager.destinations[0].path == "~/yaml"

        store.save("file_manager", "destinations", _db_dests(("Good", "/hot", "@"))["destinations"])
        plugin._on_settings_changed()

        assert plugin.context.config.file_manager.destinations[0].path == "/hot"

    def test_db_can_add_destinations(self) -> None:
        plugin, _ = make_plugin(
            *_FM,
            yaml_kwargs=_yaml_dests(("A", "~/a", "@")),
            db_settings=_db_dests(("A", "~/a", "@"), ("B", "~/b", "#")),
        )
        assert len(plugin.context.config.file_manager.destinations) == 2

    def test_db_can_remove_destinations(self) -> None:
        plugin, _ = make_plugin(
            *_FM,
            yaml_kwargs=_yaml_dests(("A", "~/a", "@"), ("B", "~/b", "#")),
            db_settings=_db_dests(("A", "~/a", "@")),
        )
        assert len(plugin.context.config.file_manager.destinations) == 1


class TestGenreEditorCodesFromDb:
    """Genre codes (JSON-serialized list) from DB override config.yaml."""

    def test_db_overrides_yaml(self) -> None:
        plugin, _ = make_plugin(
            *_GE,
            yaml_kwargs=_yaml_codes(("D", "D", "Deep")),
            db_settings=_db_codes(("X", "X", "Experimental")),
        )
        codes = plugin.context.config.genre_editor.codes
        assert len(codes) == 1
        assert codes[0].code == "X"
        assert codes[0].name == "Experimental"

    def test_falls_back_to_yaml(self) -> None:
        plugin, _ = make_plugin(*_GE, yaml_kwargs=_yaml_codes(("D", "D", "Deep")))
        assert plugin.context.config.genre_editor.codes[0].code == "D"

    def test_hot_reload(self) -> None:
        plugin, store = make_plugin(*_GE, yaml_kwargs=_yaml_codes(("D", "D", "Deep")))
        assert plugin.context.config.genre_editor.codes[0].code == "D"

        store.save("genre_editor", "genre_codes", _db_codes(("W", "W", "World"))["genre_codes"])
        plugin._on_settings_changed()

        assert plugin.context.config.genre_editor.codes[0].code == "W"

    def test_db_can_add_codes(self) -> None:
        plugin, _ = make_plugin(
            *_GE,
            yaml_kwargs=_yaml_codes(("D", "D", "Deep")),
            db_settings=_db_codes(("D", "D", "Deep"), ("T", "T", "Techno"), ("H", "H", "House")),
        )
        assert len(plugin.context.config.genre_editor.codes) == 3

    def test_db_can_remove_codes(self) -> None:
        plugin, _ = make_plugin(
            *_GE,
            yaml_kwargs=_yaml_codes(("D", "D", "Deep"), ("C", "C", "Classic")),
            db_settings=_db_codes(("D", "D", "Deep")),
        )
        assert len(plugin.context.config.genre_editor.codes) == 1

    def test_db_can_change_name(self) -> None:
        plugin, _ = make_plugin(
            *_GE,
            yaml_kwargs=_yaml_codes(("D", "D", "Deep")),
            db_settings=_db_codes(("D", "D", "Dreamy")),
        )
        assert plugin.context.config.genre_editor.codes[0].name == "Dreamy"


# ============================================================================
# 3. Combined — all settings from DB at once
# ============================================================================

COMBINED_CASES = [
    (
        *_LP,
        {"duration": 30.0, "coarse_step": 1.0, "fine_step": 0.1},
        {"duration": "20.0", "coarse_step": "3.0", "fine_step": "0.25"},
        {"duration": 20.0, "coarse_step": 3.0, "fine_step": 0.25},
    ),
    (
        *_PN,
        {"seek_amount": 10.0, "rapid_press_threshold": 0.5, "max_seek_multiplier": 5},
        {"seek_amount": "3", "rapid_press_threshold": "200", "max_seek_multiplier": "10"},
        {"seek_amount": 3, "rapid_press_threshold": 0.2, "max_seek_multiplier": 10},
    ),
    (
        *_WV,
        {"chunk_duration": 10.0, "height": 120},
        {"chunk_duration": "30", "height": "60"},
        {"chunk_duration": 30, "height": 60},
    ),
    (
        *_VE,
        {},
        {
            "default_resolution": "vertical", "output_directory": "/tmp/out",
            "video_clips_folder": "/tmp/clips",
            "waveform_bass_color": "#111111", "waveform_mid_color": "#222222",
            "waveform_treble_color": "#333333", "waveform_cursor_color": "#444444",
            "default_fps": "24", "waveform_height_ratio": "0.6",
            "waveform_enabled": "false", "text_enabled": "false",
            "dynamics_enabled": "false", "vjing_enabled": "true",
            "video_background_enabled": "true",
        },
        {
            "default_resolution": "vertical", "output_directory": "/tmp/out",
            "video_clips_folder": "/tmp/clips",
            "waveform_bass_color": "#111111", "waveform_mid_color": "#222222",
            "waveform_treble_color": "#333333", "waveform_cursor_color": "#444444",
            "default_fps": 24, "waveform_height_ratio": 0.6,
            "waveform_enabled": False, "text_enabled": False,
            "dynamics_enabled": False, "vjing_enabled": True,
            "video_background_enabled": True,
        },
    ),
]


@pytest.mark.parametrize(
    "module,cls_name,cfg_attr,cfg_cls,yaml_kw,db_settings,expected",
    COMBINED_CASES,
    ids=["LoopPlayer", "PlaybackNavigation", "WaveformVisualizer", "VideoExporter"],
)
def test_all_settings_from_db(
    module, cls_name, cfg_attr, cfg_cls, yaml_kw, db_settings, expected,
) -> None:
    """When all settings are in DB, none come from config.yaml."""
    plugin, _ = make_plugin(
        module, cls_name, cfg_attr, cfg_cls,
        yaml_kwargs=yaml_kw, db_settings=db_settings,
    )
    section = getattr(plugin.context.config, cfg_attr)
    for field, value in expected.items():
        assert getattr(section, field) == value, (
            f"{field}: expected {value}, got {getattr(section, field)}"
        )


def test_file_manager_all_settings_from_db() -> None:
    """file_manager: destinations + trash_directory + trash_key all from DB."""
    plugin, _ = make_plugin(
        *_FM,
        yaml_kwargs={
            **_yaml_dests(("Yaml", "~/yaml", "Y")),
            "trash_directory": "~/yaml-trash",
            "trash_key": "Delete",
        },
        db_settings={
            **_db_dests(("Db", "/db-dest", "D")),
            "trash_directory": "/db-trash",
            "trash_key": "Backspace",
        },
    )
    fm = plugin.context.config.file_manager
    assert fm.destinations[0].path == "/db-dest"
    assert fm.trash_directory == "/db-trash"
    assert fm.trash_key == "Backspace"


def test_genre_editor_all_settings_from_db() -> None:
    """genre_editor: codes + rating_key all from DB."""
    plugin, _ = make_plugin(
        *_GE,
        yaml_kwargs={**_yaml_codes(("D", "D", "Deep")), "rating_key": "*"},
        db_settings={**_db_codes(("W", "W", "World"), ("B", "B", "Bass")), "rating_key": "!"},
    )
    ge = plugin.context.config.genre_editor
    assert len(ge.codes) == 2
    assert ge.codes[0].code == "W"
    assert ge.rating_key == "!"


# ============================================================================
# 4. Timing gap — ShortcutMixin plugins delay DB load
# ============================================================================

TIMING_GAP_CASES = [
    (*_FM, "trash_directory", "~/yaml", "/db", "/db"),
    (*_GE, "rating_key", "*", "!", "!"),
]


@pytest.mark.parametrize(
    "module,cls_name,cfg_attr,cfg_cls,field,yaml_val,db_str,expected",
    TIMING_GAP_CASES,
    ids=["FileManager.trash_directory", "GenreEditor.rating_key"],
)
def test_timing_gap_yaml_until_register_shortcuts(
    module, cls_name, cfg_attr, cfg_cls, field, yaml_val, db_str, expected,
) -> None:
    """ShortcutMixin plugins keep yaml values after initialize().
    DB values are only loaded when register_shortcuts() is called.
    """
    plugin, _ = make_plugin(
        module, cls_name, cfg_attr, cfg_cls,
        yaml_kwargs={field: yaml_val}, db_settings={field: db_str},
        register_shortcuts=False,
    )
    # After initialize(), still yaml
    assert getattr(getattr(plugin.context.config, cfg_attr), field) == yaml_val

    sm = make_shortcut_manager()
    plugin.register_shortcuts(sm)

    # After register_shortcuts(), DB value loaded
    assert getattr(getattr(plugin.context.config, cfg_attr), field) == expected


def test_timing_gap_destinations() -> None:
    """file_manager destinations stay yaml until register_shortcuts()."""
    plugin, _ = make_plugin(
        *_FM,
        yaml_kwargs=_yaml_dests(("Good", "~/yaml", "@")),
        db_settings=_db_dests(("Good", "/db", "@")),
        register_shortcuts=False,
    )
    assert plugin.context.config.file_manager.destinations[0].path == "~/yaml"

    sm = make_shortcut_manager()
    plugin.register_shortcuts(sm)

    assert plugin.context.config.file_manager.destinations[0].path == "/db"


def test_timing_gap_genre_codes() -> None:
    """genre_editor codes stay yaml until register_shortcuts()."""
    plugin, _ = make_plugin(
        *_GE,
        yaml_kwargs=_yaml_codes(("D", "D", "Deep")),
        db_settings=_db_codes(("X", "X", "Experimental")),
        register_shortcuts=False,
    )
    assert plugin.context.config.genre_editor.codes[0].code == "D"

    sm = make_shortcut_manager()
    plugin.register_shortcuts(sm)

    assert plugin.context.config.genre_editor.codes[0].code == "X"


# ============================================================================
# 5. Behavioral — shortcuts/callbacks use DB values
# ============================================================================


class TestShortcutCallbacksUseDbValues:
    """Shortcut callbacks capture the DB config, not the yaml config."""

    def test_file_manager_callback_uses_db_destination(self) -> None:
        plugin, _ = make_plugin(
            *_FM,
            yaml_kwargs=_yaml_dests(("Good", "~/yaml", "@")),
            db_settings=_db_dests(("Good", "/db", "@")),
            register_shortcuts=False,
        )
        sm = make_shortcut_manager()
        plugin.register_shortcuts(sm)

        callback = sm.register.call_args_list[0][0][1]
        plugin._move_to_destination = MagicMock()
        callback()
        assert plugin._move_to_destination.call_args[0][0].path == "/db"

    def test_file_manager_shortcut_uses_db_key(self) -> None:
        plugin, _ = make_plugin(
            *_FM,
            yaml_kwargs={
                **_yaml_dests(("Good", "~/p", "@")),
                "trash_directory": "~/trash",
                "trash_key": "Delete",
            },
            db_settings={
                **_db_dests(("Good", "~/p", "#")),
                "trash_directory": "/db-trash",
                "trash_key": "Backspace",
            },
            register_shortcuts=False,
        )
        sm = make_shortcut_manager()
        plugin.register_shortcuts(sm)

        registered_keys = [call[0][0] for call in sm.register.call_args_list]
        assert "#" in registered_keys
        assert "Backspace" in registered_keys

    def test_genre_editor_callback_uses_db_code(self) -> None:
        plugin, _ = make_plugin(
            *_GE,
            yaml_kwargs=_yaml_codes(("D", "D", "Deep")),
            db_settings=_db_codes(("X", "X", "Experimental")),
            register_shortcuts=False,
        )
        sm = make_shortcut_manager()
        plugin.register_shortcuts(sm)

        callback = sm.register.call_args_list[0][0][1]
        plugin._toggle_code = MagicMock()
        callback()
        plugin._toggle_code.assert_called_once_with("X")

    def test_genre_editor_shortcut_count_matches_db(self) -> None:
        plugin, _ = make_plugin(
            *_GE,
            yaml_kwargs={**_yaml_codes(("D", "D", "Deep")), "rating_key": "*"},
            db_settings={
                **_db_codes(("W", "W", "World"), ("B", "B", "Bass"), ("F", "F", "Funk")),
                "rating_key": "!",
            },
            register_shortcuts=False,
        )
        sm = make_shortcut_manager()
        plugin.register_shortcuts(sm)

        # 3 genre codes + 1 rating = 4 shortcuts
        assert sm.register.call_count == 4


# ============================================================================
# 6. Edge cases
# ============================================================================


def test_ffmpeg_settings_not_synced_to_db() -> None:
    """FFmpeg settings are never read from DB — only from config.yaml."""
    plugin, _ = make_plugin(
        *_VE,
        yaml_kwargs={"ffmpeg_video_codec": "libx265"},
        db_settings={"ffmpeg_video_codec": "h264_nvenc"},
    )
    assert plugin.context.config.video_exporter.ffmpeg_video_codec == "libx265"


def test_waveform_height_change_updates_widget() -> None:
    """When DB height changes, the waveform widget is resized."""
    plugin, store = make_plugin(
        *_WV, yaml_kwargs={"height": 120}, db_settings={"height": "80"},
    )
    mock_widget = MagicMock()
    plugin.waveform_widget = mock_widget

    store.save(plugin.name, "height", "150")
    plugin._on_settings_changed()

    assert plugin.context.config.waveform.height == 150
    mock_widget.setFixedHeight.assert_called_with(150)


# ============================================================================
# 7. Guard — synced_settings must match get_settings_schema()
# ============================================================================

DB_AWARE_PLUGINS = [
    ("plugins.loop_player", "LoopPlayerPlugin"),
    ("plugins.playback_navigation", "PlaybackNavigationPlugin"),
    ("plugins.waveform_visualizer", "WaveformVisualizerPlugin"),
    ("plugins.video_exporter.plugin", "VideoExporterPlugin"),
    ("plugins.file_manager", "FileManagerPlugin"),
    ("plugins.genre_editor", "GenreEditorPlugin"),
]


@pytest.mark.parametrize(
    "module,cls_name",
    DB_AWARE_PLUGINS,
    ids=[c[1].replace("Plugin", "") for c in DB_AWARE_PLUGINS],
)
def test_synced_settings_match_schema(module: str, cls_name: str) -> None:
    """Every key in get_settings_schema() must be in _synced_settings or _synced_json_lists,
    and vice versa. Prevents drift between the settings UI and the DB sync logic."""
    import importlib

    mod = importlib.import_module(module)
    cls = getattr(mod, cls_name)

    synced_keys = {s.db_key for s in cls._synced_settings}
    synced_keys |= {j.db_key for j in cls._synced_json_lists}

    plugin = cls()
    # get_settings_schema needs context — use a mock
    plugin.context = MagicMock()
    schema_keys = set(plugin.get_settings_schema().keys())

    assert synced_keys == schema_keys, (
        f"{cls_name}: synced keys {synced_keys} != schema keys {schema_keys}"
    )


# ============================================================================
# 8. SettingsSyncMixin — isolation tests
# ============================================================================


def test_invalid_json_in_db_does_not_crash() -> None:
    """Corrupted JSON in DB for a SyncedJsonList logs error, keeps yaml value."""
    plugin, _ = make_plugin(
        *_FM,
        yaml_kwargs={
            **_yaml_dests(("Good", "~/yaml", "@")),
            "trash_directory": "~/trash",
        },
        db_settings={"destinations": "NOT_VALID_JSON", "trash_directory": "/db-trash"},
    )
    # destinations should keep yaml value (invalid JSON ignored)
    assert len(plugin.context.config.file_manager.destinations) == 1
    assert plugin.context.config.file_manager.destinations[0].path == "~/yaml"
    # scalar setting should still work
    assert plugin.context.config.file_manager.trash_directory == "/db-trash"


def test_invalid_json_on_hot_reload_keeps_previous() -> None:
    """Hot reload with corrupted JSON keeps the previously loaded value."""
    plugin, store = make_plugin(
        *_FM,
        yaml_kwargs=_yaml_dests(("Good", "~/yaml", "@")),
        db_settings=_db_dests(("Good", "/db", "@")),
    )
    assert plugin.context.config.file_manager.destinations[0].path == "/db"

    store.save("file_manager", "destinations", "{broken")
    plugin._on_settings_changed()

    # Should keep previous /db value
    assert plugin.context.config.file_manager.destinations[0].path == "/db"


# ============================================================================
# 9. initialize() must call _on_settings_changed at startup
# ============================================================================

DIRECT_RELOAD_PLUGINS = [
    ("plugins.loop_player", "LoopPlayerPlugin", "loop_player", LoopPlayerConfig),
    ("plugins.playback_navigation", "PlaybackNavigationPlugin", "playback_navigation", PlaybackNavigationConfig),
    ("plugins.waveform_visualizer", "WaveformVisualizerPlugin", "waveform", WaveformConfig),
    ("plugins.video_exporter.plugin", "VideoExporterPlugin", "video_exporter", VideoExporterConfig),
]


@pytest.mark.parametrize(
    "module,cls_name,cfg_attr,cfg_cls",
    DIRECT_RELOAD_PLUGINS,
    ids=[c[1].replace("Plugin", "") for c in DIRECT_RELOAD_PLUGINS],
)
def test_initialize_loads_db_settings_at_startup(
    module: str, cls_name: str, cfg_attr: str, cfg_cls: type,
) -> None:
    """initialize() must call _on_settings_changed() so DB values are loaded at startup,
    not only when the event fires later."""
    import importlib

    mod = importlib.import_module(module)
    cls = getattr(mod, cls_name)
    plugin = cls()

    store = FakeSettingsStore()
    # Put a setting in DB before initialize()
    first_setting = cls._synced_settings[0]
    store.save(plugin.name, first_setting.db_key, "999")

    config = MagicMock()
    setattr(config, cfg_attr, cfg_cls())
    context = make_plugin_context(config, store)

    # Record the yaml default before initialize
    yaml_default = getattr(getattr(context.config, cfg_attr), first_setting.field_name)

    plugin.initialize(context)

    # The DB value should already be loaded — no manual _on_settings_changed() needed
    actual = getattr(getattr(plugin.context.config, cfg_attr), first_setting.field_name)
    if first_setting.transform:
        expected = first_setting.transform(999)
    else:
        expected = first_setting.value_type(999)
    assert actual == expected, (
        f"{cls_name}.{first_setting.field_name}: expected {expected} from DB, "
        f"got {actual} (yaml default was {yaml_default})"
    )


# ============================================================================
# 10. rapid_press_threshold default_fn produces correct ms value
# ============================================================================


def test_rapid_press_threshold_default_fn_converts_to_ms() -> None:
    """When no DB value, get_setting receives the yaml value converted to ms as default."""
    from plugins.playback_navigation import PlaybackNavigationPlugin

    threshold_setting = next(
        s for s in PlaybackNavigationPlugin._synced_settings
        if s.db_key == "rapid_press_threshold"
    )

    # Simulate a config with 0.5s threshold
    config = MagicMock()
    config.rapid_press_threshold = 0.5

    default = threshold_setting.default_fn(config)
    assert default == 500  # 0.5s * 1000 = 500ms
