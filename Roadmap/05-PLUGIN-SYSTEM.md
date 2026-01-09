# Phase 5: Plugin System Architecture

**Durée**: Semaines 4-5
**Objectif**: Architecture modulaire extensible
**Milestone**: `v0.4.0-beta` - Architecture modulaire opérationnelle

---

## Vue d'Ensemble

Cette phase transforme l'application en une architecture modulaire où les fonctionnalités sont des plugins indépendants.

**Objectif**: Permettre l'ajout de fonctionnalités sans modifier le core.

---

## 5.1 Plugin Manager (Jours 1-2)

### 5.1.1 Core Plugin Manager
Créer `jukebox/core/plugin_manager.py`:

```python
from typing import Protocol, Dict, Optional, List
from pathlib import Path
import importlib
import inspect
import logging


class JukeboxPlugin(Protocol):
    """Protocol that all plugins must implement."""

    name: str
    version: str
    description: str

    def initialize(self, context: 'PluginContext') -> None:
        """Called when plugin is loaded."""
        ...

    def register_ui(self, ui_builder: 'UIBuilder') -> None:
        """Register UI elements."""
        ...

    def register_shortcuts(self, shortcut_manager: 'ShortcutManager') -> None:
        """Register keyboard shortcuts."""
        ...

    def shutdown(self) -> None:
        """Called when plugin is unloaded."""
        ...


class PluginContext:
    """Context provided to each plugin."""

    def __init__(self, app):
        self.app = app
        self.database = app.database
        self.player = app.player
        self.config = app.config
        self.event_bus = app.event_bus

    def emit(self, event: str, **data):
        """Emit event to event bus."""
        self.event_bus.emit(event, **data)

    def subscribe(self, event: str, callback):
        """Subscribe to event."""
        self.event_bus.subscribe(event, callback)


class PluginManager:
    """Manage plugins lifecycle."""

    def __init__(self, plugins_dir: Path, context: PluginContext):
        self.plugins_dir = plugins_dir
        self.context = context
        self.plugins: Dict[str, JukeboxPlugin] = {}
        self.loaded_modules: Dict[str, any] = {}

    def discover_plugins(self) -> List[str]:
        """Discover available plugins."""
        if not self.plugins_dir.exists():
            return []

        plugin_files = []
        for file in self.plugins_dir.glob("*.py"):
            if not file.stem.startswith("_"):
                plugin_files.append(file.stem)

        return plugin_files

    def load_plugin(self, plugin_name: str) -> bool:
        """Load a single plugin."""
        try:
            module_name = f"plugins.{plugin_name}"
            module = importlib.import_module(module_name)
            self.loaded_modules[plugin_name] = module

            # Find plugin class
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (hasattr(obj, 'initialize') and
                    hasattr(obj, 'name') and
                    hasattr(obj, 'version')):

                    plugin_instance = obj()
                    plugin_instance.initialize(self.context)
                    self.plugins[plugin_instance.name] = plugin_instance

                    logging.info(
                        f"Loaded plugin: {plugin_instance.name} "
                        f"v{plugin_instance.version}"
                    )
                    return True

            logging.warning(f"No valid plugin class found in {module_name}")
            return False

        except Exception as e:
            logging.error(f"Failed to load plugin {plugin_name}: {e}")
            return False

    def load_all_plugins(self) -> int:
        """Load all available plugins."""
        plugins = self.discover_plugins()
        loaded = 0

        for plugin_name in plugins:
            if self.load_plugin(plugin_name):
                loaded += 1

        return loaded

    def unload_plugin(self, plugin_name: str) -> bool:
        """Unload a plugin."""
        if plugin_name not in self.plugins:
            return False

        try:
            plugin = self.plugins[plugin_name]
            plugin.shutdown()
            del self.plugins[plugin_name]
            logging.info(f"Unloaded plugin: {plugin_name}")
            return True

        except Exception as e:
            logging.error(f"Failed to unload plugin {plugin_name}: {e}")
            return False

    def get_plugin(self, plugin_name: str) -> Optional[JukeboxPlugin]:
        """Get plugin instance by name."""
        return self.plugins.get(plugin_name)

    def get_all_plugins(self) -> List[JukeboxPlugin]:
        """Get all loaded plugins."""
        return list(self.plugins.values())
```

---

## 5.2 Event Bus (Jour 2)

### 5.2.1 Event System
Créer `jukebox/core/event_bus.py`:

```python
from typing import Callable, Dict, List
import logging


class EventBus:
    """Event bus for inter-plugin communication."""

    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event: str, callback: Callable) -> None:
        """Subscribe to an event."""
        if event not in self.subscribers:
            self.subscribers[event] = []

        self.subscribers[event].append(callback)
        logging.debug(f"Subscribed to event: {event}")

    def unsubscribe(self, event: str, callback: Callable) -> bool:
        """Unsubscribe from an event."""
        if event not in self.subscribers:
            return False

        try:
            self.subscribers[event].remove(callback)
            logging.debug(f"Unsubscribed from event: {event}")
            return True
        except ValueError:
            return False

    def emit(self, event: str, **data) -> None:
        """Emit an event to all subscribers."""
        if event not in self.subscribers:
            return

        logging.debug(f"Emitting event: {event} with data: {data}")

        for callback in self.subscribers[event]:
            try:
                callback(**data)
            except Exception as e:
                logging.error(
                    f"Error in event handler for {event}: {e}"
                )


# Common events
class Events:
    """Standard event names."""

    # Player events
    TRACK_LOADED = "track_loaded"
    TRACK_PLAYING = "track_playing"
    TRACK_PAUSED = "track_paused"
    TRACK_STOPPED = "track_stopped"
    TRACK_FINISHED = "track_finished"

    # Library events
    TRACKS_ADDED = "tracks_added"
    TRACK_UPDATED = "track_updated"
    TRACK_DELETED = "track_deleted"

    # Search events
    SEARCH_PERFORMED = "search_performed"
    SEARCH_RESULTS = "search_results"

    # Playlist events
    PLAYLIST_CREATED = "playlist_created"
    PLAYLIST_UPDATED = "playlist_updated"
    PLAYLIST_DELETED = "playlist_deleted"
```

---

## 5.3 UI Builder API (Jours 3-4)

### 5.3.1 UIBuilder
Créer `jukebox/ui/ui_builder.py`:

```python
from PySide6.QtWidgets import QWidget, QToolBar, QMenu, QAction
from typing import Optional, Callable


class UIBuilder:
    """API for plugins to inject UI elements."""

    def __init__(self, main_window):
        self.main_window = main_window

    def add_menu(self, name: str) -> QMenu:
        """Add a new menu to menubar."""
        menu = self.main_window.menuBar().addMenu(name)
        return menu

    def add_menu_action(
        self,
        menu: QMenu,
        text: str,
        callback: Callable,
        shortcut: Optional[str] = None
    ) -> QAction:
        """Add action to menu."""
        action = QAction(text, self.main_window)
        action.triggered.connect(callback)

        if shortcut:
            action.setShortcut(shortcut)

        menu.addAction(action)
        return action

    def add_toolbar_widget(self, widget: QWidget) -> None:
        """Add widget to toolbar."""
        if not hasattr(self.main_window, '_plugin_toolbar'):
            self.main_window._plugin_toolbar = QToolBar("Plugins")
            self.main_window.addToolBar(self.main_window._plugin_toolbar)

        self.main_window._plugin_toolbar.addWidget(widget)

    def add_sidebar_widget(self, widget: QWidget, title: str) -> None:
        """Add widget to sidebar."""
        # Implement sidebar/dock widget logic
        pass

    def get_main_layout(self):
        """Get main layout for custom widgets."""
        return self.main_window.centralWidget().layout()
```

---

## 5.4 Example Plugins (Jours 4-5)

### 5.4.1 Search Plugin
Créer `plugins/search_plugin.py`:

```python
from PySide6.QtWidgets import QLineEdit
from jukebox.core.event_bus import Events


class SearchPlugin:
    """Full-text search plugin."""

    name = "search"
    version = "1.0.0"
    description = "FTS5 search for tracks"

    def __init__(self):
        self.context = None
        self.search_bar = None

    def initialize(self, context):
        """Initialize plugin."""
        self.context = context

    def register_ui(self, ui_builder):
        """Register search bar."""
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search...")
        self.search_bar.textChanged.connect(self._on_search)
        ui_builder.add_toolbar_widget(self.search_bar)

    def register_shortcuts(self, shortcut_manager):
        """Register Ctrl+F for focus."""
        shortcut_manager.register(
            "Ctrl+F",
            lambda: self.search_bar.setFocus()
        )

    def _on_search(self, query: str):
        """Perform search."""
        if len(query) < 2:
            results = self.context.database.get_all_tracks()
        else:
            results = self.context.database.search_tracks(query)

        self.context.emit(Events.SEARCH_RESULTS, results=results)

    def shutdown(self):
        """Cleanup."""
        pass
```

### 5.4.2 History Plugin
Créer `plugins/history_plugin.py`:

```python
from jukebox.core.event_bus import Events


class HistoryPlugin:
    """Track play history plugin."""

    name = "history"
    version = "1.0.0"
    description = "Record play history"

    def __init__(self):
        self.context = None
        self.current_track_id = None
        self.play_start_time = None

    def initialize(self, context):
        """Initialize plugin."""
        self.context = context

        # Subscribe to player events
        self.context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)
        self.context.subscribe(Events.TRACK_FINISHED, self._on_track_finished)
        self.context.subscribe(Events.TRACK_STOPPED, self._on_track_stopped)

    def _on_track_loaded(self, track_id: int):
        """Track loaded."""
        self.current_track_id = track_id
        import time
        self.play_start_time = time.time()

    def _on_track_finished(self):
        """Track finished playing."""
        if self.current_track_id:
            import time
            duration = time.time() - self.play_start_time
            self.context.database.record_play(
                self.current_track_id,
                duration,
                completed=True
            )

    def _on_track_stopped(self):
        """Track stopped before finish."""
        if self.current_track_id and self.play_start_time:
            import time
            duration = time.time() - self.play_start_time
            self.context.database.record_play(
                self.current_track_id,
                duration,
                completed=False
            )

    def register_ui(self, ui_builder):
        """No UI needed."""
        pass

    def register_shortcuts(self, shortcut_manager):
        """No shortcuts."""
        pass

    def shutdown(self):
        """Cleanup."""
        pass
```

### 5.4.3 Stats Plugin
Créer `plugins/stats_plugin.py`:

```python
from PySide6.QtWidgets import QPushButton, QMessageBox


class StatsPlugin:
    """Library statistics plugin."""

    name = "stats"
    version = "1.0.0"
    description = "Show library statistics"

    def initialize(self, context):
        """Initialize plugin."""
        self.context = context

    def register_ui(self, ui_builder):
        """Add stats button."""
        menu = ui_builder.add_menu("&Statistics")
        ui_builder.add_menu_action(
            menu,
            "Show Library Stats",
            self._show_stats
        )

    def _show_stats(self):
        """Show statistics dialog."""
        db = self.context.database

        # Get stats
        total_tracks = db.conn.execute(
            "SELECT COUNT(*) FROM tracks"
        ).fetchone()[0]

        total_duration = db.conn.execute(
            "SELECT SUM(duration_seconds) FROM tracks"
        ).fetchone()[0] or 0

        total_plays = db.conn.execute(
            "SELECT SUM(play_count) FROM tracks"
        ).fetchone()[0] or 0

        most_played = db.conn.execute("""
            SELECT title, artist, play_count
            FROM tracks
            ORDER BY play_count DESC
            LIMIT 5
        """).fetchall()

        # Format message
        hours = int(total_duration / 3600)
        minutes = int((total_duration % 3600) / 60)

        msg = f"""
Library Statistics:

Total Tracks: {total_tracks}
Total Duration: {hours}h {minutes}m
Total Plays: {total_plays}

Most Played:
"""
        for track in most_played:
            msg += f"\n  {track[0]} - {track[1]} ({track[2]} plays)"

        QMessageBox.information(
            None,
            "Library Statistics",
            msg
        )

    def register_shortcuts(self, shortcut_manager):
        """No shortcuts."""
        pass

    def shutdown(self):
        """Cleanup."""
        pass
```

---

## 5.5 Intégration MainWindow (Jour 5)

Modifier `main_window.py` pour intégrer le plugin system:

```python
def __init__(self, config: JukeboxConfig):
    super().__init__()
    self.config = config
    self.database = Database(Path.home() / ".jukebox" / "jukebox.db")
    self.database.connect()
    self.database.initialize_schema()

    self.player = AudioPlayer()
    self.event_bus = EventBus()

    # Initialize UI
    self._init_ui()

    # Plugin system
    self.plugin_context = PluginContext(self)
    self.plugin_manager = PluginManager(
        Path(__file__).parent.parent / "plugins",
        self.plugin_context
    )

    # UI Builder for plugins
    self.ui_builder = UIBuilder(self)

    # Load plugins
    loaded = self.plugin_manager.load_all_plugins()
    logging.info(f"Loaded {loaded} plugins")

    # Register plugin UIs
    for plugin in self.plugin_manager.get_all_plugins():
        plugin.register_ui(self.ui_builder)
```

---

## Checklist Phase 5

### Plugin Manager (Jours 1-2)
- [x] PluginManager créé
- [x] Découverte automatique plugins
- [x] Load plugins
- [x] PluginContext fourni

### Event Bus (Jour 2)
- [x] EventBus implémenté
- [x] Subscribe/emit fonctionnent
- [x] Events constants définis
- [x] Tests passent

### UI Builder (Jours 3-4)
- [x] UIBuilder API créée
- [x] Add menu/toolbar
- [x] Intégration MainWindow

### Example Plugins (Jours 4-5)
- [x] Stats plugin
- [x] Playlists plugin (moved from core)
- [x] Intégration automatique plugins

### Tests (Jour 5)
- [x] Tests existants passent
- [x] Tests plugin loading
- [x] Tests event bus
- [x] Tests UI builder

---

## Prochaine Phase

➡️ [Phase 6 - Essential Modules](06-ESSENTIAL-MODULES.md)

---

**Durée estimée**: 5-7 jours
**Effort**: ~35-40 heures
**Complexité**: Élevée
