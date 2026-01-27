"""Plugin management system."""

from __future__ import annotations

import importlib
import inspect
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from jukebox.core.protocols import (
        AudioPlayerProtocol,
        DatabaseProtocol,
        EventBusProtocol,
        JukeboxConfigProtocol,
        PluginContextProtocol,
        UIBuilderProtocol,
    )


class JukeboxPlugin(Protocol):
    """Protocol that all plugins must implement."""

    name: str
    version: str
    description: str
    modes: list[str]  # Modes where this plugin is active (default: all modes)

    def initialize(self, context: PluginContextProtocol) -> None:
        """Called when plugin is loaded (once at startup)."""
        ...

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
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


class BasePlugin:
    """Base class for plugins with default implementations.

    Plugins can inherit from this class to avoid implementing empty methods.
    All lifecycle methods have no-op defaults.

    Attributes:
        name: Plugin identifier (must be overridden).
        version: Plugin version string (must be overridden).
        description: Human-readable description (must be overridden).
        modes: List of modes where plugin is active. Defaults to all modes.
        context: Plugin context, set during initialize().
    """

    name: str = "base_plugin"
    version: str = "0.0.0"
    description: str = "Base plugin class"
    modes: list[str] = ["jukebox", "curating"]

    def __init__(self) -> None:
        """Initialize plugin instance."""
        self.context: PluginContextProtocol | None = None

    def initialize(self, context: PluginContextProtocol) -> None:
        """Called when plugin is loaded. Override to add initialization logic."""
        self.context = context

    def register_ui(self, ui_builder: UIBuilderProtocol) -> None:
        """Register UI elements. Override to add UI components."""
        pass

    def activate(self, mode: str) -> None:
        """Called when entering a mode where this plugin is active."""
        pass

    def deactivate(self, mode: str) -> None:
        """Called when leaving a mode where this plugin is active."""
        pass

    def shutdown(self) -> None:
        """Called when application closes. Override for cleanup."""
        pass


class PluginContext:
    """Context provided to plugins.

    Provides typed access to application services:
        - database: Database operations (tracks, waveforms, analysis, settings)
        - player: Audio playback control
        - config: Application configuration
        - event_bus: Event pub/sub system
    """

    def __init__(self, app: Any) -> None:
        """Initialize context.

        Args:
            app: Application instance (MainWindow)
        """
        self.app = app
        self.database: DatabaseProtocol = app.database
        self.player: AudioPlayerProtocol = app.player
        self.config: JukeboxConfigProtocol = app.config
        self.event_bus: EventBusProtocol | None = getattr(app, "event_bus", None)

    def emit(self, event: str, **data: Any) -> None:
        """Emit an event to all subscribers."""
        if self.event_bus:
            self.event_bus.emit(event, **data)

    def subscribe(self, event: str, callback: Callable[..., None]) -> None:
        """Subscribe to an event."""
        if self.event_bus:
            self.event_bus.subscribe(event, callback)

    def get_setting(
        self,
        plugin_name: str,
        key: str,
        value_type: type,
        default: Any = None,
    ) -> Any:
        """Get a plugin setting with automatic type conversion.

        Retrieves a setting from the database and converts it to the specified type.
        Handles errors gracefully by returning the default value.

        Args:
            plugin_name: Name of the plugin.
            key: Setting key.
            value_type: Target type (int, float, bool, str).
            default: Default value if setting not found or conversion fails.

        Returns:
            The setting value converted to value_type, or default on failure.
        """
        value = self.database.settings.get(plugin_name, key)

        if value is None:
            return default

        try:
            if value_type is bool:
                return value.lower() in ("true", "1", "yes")
            return value_type(value)
        except (ValueError, AttributeError):
            logging.warning(f"[{plugin_name}] Invalid {key} value: {value}, using default")
            return default

    def get_current_track_duration(self) -> float | None:
        """Get the duration of the currently loaded track.

        Convenience method that retrieves the current track from database
        and returns its duration.

        Returns:
            Duration in seconds, or None if no track loaded or duration unavailable.
        """
        if not self.player.current_file:
            return None
        track = self.database.tracks.get_by_filepath(self.player.current_file)
        if not track or not track["duration_seconds"]:
            return None
        duration: float = track["duration_seconds"]
        return duration


class PluginManager:
    """Manage plugins lifecycle."""

    def __init__(self, plugins_dir: Path, context: PluginContext):
        """Initialize plugin manager."""
        self.plugins_dir = plugins_dir
        self.context = context
        self.plugins: dict[str, Any] = {}
        self.current_mode: str | None = None

    def discover_plugins(self) -> list[str]:
        """Discover available plugins.

        Supports both single-file plugins (*.py) and package plugins (directories with __init__.py).
        """
        if not self.plugins_dir.exists():
            return []

        plugins = []

        # Find single-file plugins (*.py)
        for f in self.plugins_dir.glob("*.py"):
            if not f.stem.startswith("_"):
                plugins.append(f.stem)

        # Find package plugins (directories with __init__.py)
        for d in self.plugins_dir.iterdir():
            if d.is_dir() and not d.name.startswith("_") and (d / "__init__.py").exists():
                if d.name not in plugins:  # Avoid duplicates
                    plugins.append(d.name)

        return plugins

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
                if old_mode in plugin_modes and hasattr(plugin, "deactivate"):
                    try:
                        plugin.deactivate(old_mode)
                        logging.debug(f"Deactivated plugin: {plugin.name}")
                    except Exception as e:
                        logging.error(f"Error deactivating plugin {plugin.name}: {e}")

        # Activate plugins for new mode
        for plugin in self.plugins.values():
            plugin_modes = getattr(plugin, "modes", ["jukebox", "curating"])
            if new_mode in plugin_modes and hasattr(plugin, "activate"):
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
