"""Tests documenting that some plugins ONLY read from config.yaml.

These plugins have no get_settings_schema(), no _reload_plugin_config(),
and never access the plugin_settings DB table. Their configuration is
exclusively driven by config.yaml -> Pydantic model.

This is not necessarily a bug — these plugins simply don't have a GUI
for editing their settings. These tests document and lock that behavior
so that any future change (e.g., adding DB support) is intentional.
"""

import importlib

import pytest
from unittest.mock import MagicMock

from jukebox.core.config import (
    DirectoryNavigatorConfig,
    MetadataEditorConfig,
    MetadataFieldConfig,
    UIConfig,
)

# ============================================================================
# Parametrized: all yaml-only plugins have no DB support
# ============================================================================

YAML_ONLY_PLUGINS = [
    ("plugins.metadata_editor", "MetadataEditorPlugin"),
    ("plugins.directory_navigator", "DirectoryNavigatorPlugin"),
    ("plugins.cue_maker.plugin", "CueMakerPlugin"),
    ("plugins.mode_switcher", "ModeSwitcherPlugin"),
    ("plugins.theme_switcher", "ThemeSwitcherPlugin"),
]


def _load_plugin(module_path: str, class_name: str):  # type: ignore[return]
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)()


@pytest.mark.parametrize(
    "module,cls_name",
    YAML_ONLY_PLUGINS,
    ids=[c[1].replace("Plugin", "") for c in YAML_ONLY_PLUGINS],
)
class TestYamlOnlyPluginsHaveNoDbSupport:
    """These plugins have no DB-backed settings mechanism."""

    def test_has_no_settings_schema(self, module: str, cls_name: str) -> None:
        plugin = _load_plugin(module, cls_name)
        assert not hasattr(plugin, "get_settings_schema")

    def test_has_no_reload_plugin_config(self, module: str, cls_name: str) -> None:
        plugin = _load_plugin(module, cls_name)
        assert not hasattr(plugin, "_reload_plugin_config")


# ============================================================================
# Plugin-specific: config values are read correctly from yaml
# ============================================================================


class TestMetadataEditorReadsFromConfig:
    def test_plugin_reads_fields_from_config(self) -> None:
        from plugins.metadata_editor import MetadataEditorPlugin

        plugin = MetadataEditorPlugin()
        config = MagicMock()
        config.metadata_editor = MetadataEditorConfig(
            fields=[
                MetadataFieldConfig(tag="artist", label="Artist"),
                MetadataFieldConfig(tag="title", label="Title"),
            ]
        )
        context = MagicMock()
        context.config = config
        plugin.initialize(context)

        fields = plugin.context.config.metadata_editor.fields
        assert len(fields) == 2
        assert fields[0].tag == "artist"


class TestDirectoryNavigatorReadsFromConfig:
    def test_plugin_reads_config_from_yaml(self) -> None:
        from plugins.directory_navigator import DirectoryNavigatorPlugin

        plugin = DirectoryNavigatorPlugin()
        config = MagicMock()
        config.directory_navigator = DirectoryNavigatorConfig(
            default_directory="CUSTOM_DIR"
        )
        context = MagicMock()
        context.config = config
        plugin.initialize(context)

        assert (
            plugin.context.config.directory_navigator.default_directory == "CUSTOM_DIR"
        )


class TestModeSwitcherReadsFromConfig:
    def test_plugin_reads_mode_from_config(self) -> None:
        from plugins.mode_switcher import ModeSwitcherPlugin

        plugin = ModeSwitcherPlugin()
        config = MagicMock()
        config.ui = UIConfig(mode="curating")
        context = MagicMock()
        context.config = config
        plugin.initialize(context)

        assert plugin.context.config.ui.mode == "curating"


class TestThemeSwitcherReadsFromConfig:
    def test_plugin_reads_theme_from_config(self) -> None:
        from plugins.theme_switcher import ThemeSwitcherPlugin

        plugin = ThemeSwitcherPlugin()
        config = MagicMock()
        config.ui = UIConfig(theme="light")
        context = MagicMock()
        context.config = config
        plugin.initialize(context)

        assert plugin.context.config.ui.theme == "light"
