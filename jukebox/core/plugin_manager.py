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
    modes: list[str]  # Modes where this plugin is active (default: all modes)

    def initialize(self, context: Any) -> None:
        """Called when plugin is loaded (once at startup)."""
        ...

    def register_ui(self, ui_builder: Any) -> None:
        """Register UI elements (once at startup)."""
        ...

    def activate(self, mode: str) -> None:
        """Called when entering a mode where this plugin is active."""
        ...

    def deactivate(self, mode: str) -> None:
        """Called when leaving a mode where this plugin is active."""
        ...

    def shutdown(self) -> None:
        """Called when application closes (once at exit)."""
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
        self.current_mode: str | None = None

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

    def load_all_plugins(self, mode: str | None = None) -> int:
        """Load all plugins (called once at startup).

        Args:
            mode: Initial mode ("jukebox" or "curating")

        Returns:
            Number of plugins loaded
        """
        loaded = 0
        enabled_plugins = getattr(self.context.config, "plugins", None)
        enabled_list = enabled_plugins.enabled if enabled_plugins else None

        # Load ALL enabled plugins regardless of mode
        for plugin_name in self.discover_plugins():
            if enabled_list and plugin_name not in enabled_list:
                logging.info(f"Plugin {plugin_name} disabled")
                continue

            if self.load_plugin(plugin_name):
                loaded += 1

        # Set initial mode and activate appropriate plugins
        if mode:
            self.current_mode = mode
            for plugin in self.plugins.values():
                plugin_modes = getattr(plugin, "modes", ["jukebox", "curating"])
                if mode in plugin_modes:
                    if hasattr(plugin, "activate"):
                        try:
                            plugin.activate(mode)
                            logging.debug(f"Initially activated plugin: {plugin.name} for {mode}")
                        except Exception as e:
                            logging.error(f"Error initially activating plugin {plugin.name}: {e}")
                else:
                    # Plugin not active in this mode, deactivate it
                    if hasattr(plugin, "deactivate"):
                        try:
                            plugin.deactivate(mode)
                            logging.debug(f"Initially deactivated plugin: {plugin.name}")
                        except Exception as e:
                            logging.error(f"Error initially deactivating plugin {plugin.name}: {e}")

        return loaded

    def get_all_plugins(self) -> list[Any]:
        """Get all loaded plugins."""
        return list(self.plugins.values())

    def unload_all_plugins(self) -> None:
        """Unload all plugins and call their shutdown methods."""
        for plugin in list(self.plugins.values()):
            try:
                plugin.shutdown()
                logging.info(f"Unloaded plugin: {plugin.name}")
            except Exception as e:
                logging.error(f"Error shutting down plugin {plugin.name}: {e}")

        self.plugins.clear()

    def switch_mode(self, new_mode: str) -> None:
        """Switch to a different mode without reloading plugins.

        Args:
            new_mode: Mode to switch to ("jukebox" or "curating")
        """
        if self.current_mode == new_mode:
            logging.debug(f"Already in {new_mode} mode")
            return

        old_mode = self.current_mode

        # Deactivate plugins that were active in old mode
        if old_mode:
            for plugin in self.plugins.values():
                plugin_modes = getattr(plugin, "modes", ["jukebox", "curating"])
                if old_mode in plugin_modes:
                    if hasattr(plugin, "deactivate"):
                        try:
                            plugin.deactivate(old_mode)
                            logging.debug(f"Deactivated plugin: {plugin.name}")
                        except Exception as e:
                            logging.error(f"Error deactivating plugin {plugin.name}: {e}")

        # Activate plugins for new mode
        for plugin in self.plugins.values():
            plugin_modes = getattr(plugin, "modes", ["jukebox", "curating"])
            if new_mode in plugin_modes:
                if hasattr(plugin, "activate"):
                    try:
                        plugin.activate(new_mode)
                        logging.debug(f"Activated plugin: {plugin.name}")
                    except Exception as e:
                        logging.error(f"Error activating plugin {plugin.name}: {e}")

        self.current_mode = new_mode
        logging.info(f"Switched to {new_mode} mode")

    def reload_plugins_for_mode(self, mode: str, ui_builder: Any) -> int:
        """DEPRECATED: Use switch_mode() instead.

        Kept for backwards compatibility during transition.
        """
        logging.warning("reload_plugins_for_mode is deprecated, use switch_mode instead")

        # Unload all current plugins
        self.unload_all_plugins()

        # Load plugins for new mode
        loaded = self.load_all_plugins(mode=mode)

        # Register plugin UIs
        for plugin in self.get_all_plugins():
            plugin.register_ui(ui_builder)

        return loaded
