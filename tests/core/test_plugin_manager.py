"""Tests for plugin manager."""

from pathlib import Path

from jukebox.core.plugin_manager import PluginContext, PluginManager


class TestPluginManager:
    """Test PluginManager."""

    def test_discover_plugins(self, tmp_path: Path) -> None:
        """Test plugin discovery."""
        # Create fake plugins directory
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        (plugins_dir / "test_plugin.py").write_text("# test")
        (plugins_dir / "_hidden.py").write_text("# hidden")

        class MockContext:
            pass

        pm = PluginManager(plugins_dir, MockContext())  # type: ignore
        plugins = pm.discover_plugins()

        assert "test_plugin" in plugins
        assert "_hidden" not in plugins

    def test_plugin_context_has_attributes(self, qapp) -> None:  # type: ignore
        """Test PluginContext provides required attributes."""

        class MockApp:
            database = "db"
            player = "player"
            config = "config"
            event_bus = "bus"

        context = PluginContext(MockApp())  # type: ignore

        assert context.database == "db"
        assert context.player == "player"
        assert context.config == "config"
        assert context.event_bus == "bus"
