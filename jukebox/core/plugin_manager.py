"""Plugin management system."""

import importlib
import inspect
import logging
from pathlib import Path
from typing import Any, Protocol


class JukeboxPlugin(Protocol):
    """Protocol that all plugins must implement."""

    name: str
    version: str
    description: str

    def initialize(self, context: Any) -> None:
        """Called when plugin is loaded."""
        ...

    def register_ui(self, ui_builder: Any) -> None:
        """Register UI elements."""
        ...

    def shutdown(self) -> None:
        """Called when plugin is unloaded."""
        ...


class PluginContext:
    """Context provided to plugins."""

    def __init__(self, app: Any):
        """Initialize context."""
        self.app = app
        self.database = app.database
        self.player = app.player
        self.config = app.config
        self.event_bus = getattr(app, "event_bus", None)

    def emit(self, event: str, **data: Any) -> None:
        """Emit event."""
        if self.event_bus:
            self.event_bus.emit(event, **data)

    def subscribe(self, event: str, callback: Any) -> None:
        """Subscribe to event."""
        if self.event_bus:
            self.event_bus.subscribe(event, callback)


class PluginManager:
    """Manage plugins lifecycle."""

    def __init__(self, plugins_dir: Path, context: PluginContext):
        """Initialize plugin manager."""
        self.plugins_dir = plugins_dir
        self.context = context
        self.plugins: dict[str, Any] = {}

    def discover_plugins(self) -> list[str]:
        """Discover available plugins."""
        if not self.plugins_dir.exists():
            return []

        return [f.stem for f in self.plugins_dir.glob("*.py") if not f.stem.startswith("_")]

    def load_plugin(self, plugin_name: str) -> bool:
        """Load a plugin."""
        try:
            module = importlib.import_module(f"plugins.{plugin_name}")

            for _name, obj in inspect.getmembers(module, inspect.isclass):
                if hasattr(obj, "initialize") and hasattr(obj, "name"):
                    instance = obj()
                    instance.initialize(self.context)
                    self.plugins[instance.name] = instance
                    logging.info(f"Loaded plugin: {instance.name} v{instance.version}")
                    return True

            return False
        except Exception as e:
            logging.error(f"Failed to load plugin {plugin_name}: {e}")
            return False

    def load_all_plugins(self) -> int:
        """Load all plugins."""
        loaded = 0
        enabled_plugins = getattr(self.context.config, "plugins", None)
        enabled_list = enabled_plugins.enabled if enabled_plugins else None

        for plugin_name in self.discover_plugins():
            # Check if plugin is enabled in config
            if enabled_list and plugin_name not in enabled_list:
                logging.info(f"Plugin {plugin_name} disabled in config")
                continue

            if self.load_plugin(plugin_name):
                loaded += 1
        return loaded

    def get_all_plugins(self) -> list[Any]:
        """Get all loaded plugins."""
        return list(self.plugins.values())
