# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup
```bash
# Install dependencies (requires uv: https://astral.sh/uv)
uv sync --all-extras

# Install VLC (required dependency)
# macOS: brew install vlc
# Ubuntu: sudo apt-get install vlc libvlc-dev
```

### Running the Application
```bash
# Run the application
uv run jukebox
# or
make run
```

### Testing
```bash
# Run all tests with coverage
uv run pytest
# or
make test

# Run specific test file
uv run pytest tests/core/test_audio_player.py

# Run specific test function
uv run pytest tests/core/test_audio_player.py::test_load_file
```

### Code Quality
```bash
# Format code (black + ruff)
make format

# Lint
make lint

# Type check
make type-check

# Run all CI checks (format, lint, type-check, test)
make ci
```

## Architecture Overview

### Core Components

**Event-Driven Architecture**: The application uses an EventBus for decoupled communication between components and plugins. Key events are defined in `jukebox/core/event_bus.py` (Events class).

**Plugin System**: Extensible plugin architecture where plugins can:
- Add UI elements (menus, toolbars, sidebars, bottom widgets) via UIBuilder API
- Subscribe to events via PluginContext
- Access core services (database, player, config, event_bus)
- Be enabled/disabled in `config/config.yaml` under `plugins.enabled`

**Database**: SQLite with FTS5 (full-text search) support. Schema includes tracks table with comprehensive metadata and search indices. Located at `~/.jukebox/jukebox.db`.

**Audio Playback**: Wraps python-vlc library. The AudioPlayer class (QObject) emits Qt signals for state changes, position updates, and volume changes.

**Configuration**: YAML-based configuration with Pydantic validation. Located at `config/config.yaml`.

### Application Flow

1. **Startup** (`jukebox/main.py`):
   - Load config from `config/config.yaml`
   - Setup logging
   - Create QApplication
   - Initialize MainWindow

2. **MainWindow Initialization** (`jukebox/ui/main_window.py`):
   - Connect to database (`~/.jukebox/jukebox.db`)
   - Initialize AudioPlayer
   - Create EventBus
   - Build UI (track list, player controls, search bar)
   - Load plugins from `plugins/` directory
   - Load tracks from database

3. **Plugin Loading** (`jukebox/core/plugin_manager.py`):
   - Discover `.py` files in `plugins/` directory
   - Check if enabled in config (`plugins.enabled`)
   - Instantiate plugin classes
   - Call `initialize(context)` with PluginContext
   - Call `register_ui(ui_builder)` with UIBuilder

### Plugin Development

Plugins must implement the JukeboxPlugin protocol:

```python
class MyPlugin:
    name = "my_plugin"
    version = "1.0.0"
    description = "Description"

    def initialize(self, context: PluginContext) -> None:
        """Called when plugin loads. Access app services via context."""
        self.context = context
        # Subscribe to events
        context.subscribe("track_loaded", self.on_track_loaded)

    def register_ui(self, ui_builder: UIBuilder) -> None:
        """Add UI elements."""
        menu = ui_builder.add_menu("&MyMenu")
        ui_builder.add_menu_action(menu, "Action", self.my_action)

    def shutdown(self) -> None:
        """Cleanup when plugin unloads."""
        pass
```

**PluginContext API**:
- `context.database` - Database instance
- `context.player` - AudioPlayer instance
- `context.config` - JukeboxConfig instance
- `context.event_bus` - EventBus instance
- `context.emit(event, **data)` - Emit event
- `context.subscribe(event, callback)` - Subscribe to event

**UIBuilder API** (`jukebox/ui/ui_builder.py`):
- `add_menu(name)` - Add menu to menubar
- `add_menu_action(menu, text, callback, shortcut=None)` - Add action to menu
- `add_toolbar_widget(widget)` - Add widget to plugin toolbar
- `add_sidebar_widget(widget, title)` - Add dock widget to right sidebar
- `add_bottom_widget(widget)` - Add widget at bottom of main layout

**Standard Events** (in `jukebox/core/event_bus.py`):
- `TRACK_LOADED` - Track loaded in player
- `TRACK_PLAYING` - Playback started
- `TRACK_STOPPED` - Playback stopped
- `TRACKS_ADDED` - Tracks added to library
- `SEARCH_PERFORMED` - Search executed

### Key Files

- `jukebox/main.py` - Application entry point
- `jukebox/ui/main_window.py` - Main window with application state
- `jukebox/core/audio_player.py` - VLC wrapper with Qt signals
- `jukebox/core/database.py` - SQLite database with FTS5 search
- `jukebox/core/event_bus.py` - Event pub/sub system
- `jukebox/core/plugin_manager.py` - Plugin lifecycle management
- `jukebox/ui/ui_builder.py` - Plugin UI injection API
- `jukebox/utils/metadata.py` - Audio file metadata extraction (mutagen)
- `jukebox/utils/scanner.py` - Filesystem scanning for audio files

### Testing

Tests use pytest with pytest-qt for Qt testing and pytest-cov for coverage. VLC is mocked via `tests/pytest_vlc_mock.py` to enable testing without VLC installation. Mocks are in `tests/mocks/`.

Test structure mirrors source:
- `tests/core/` - Core functionality tests
- `tests/ui/` - UI component tests
- `tests/utils/` - Utility tests
- `tests/integration/` - Integration tests
- `tests/performance/` - Performance tests

### Code Style

- Line length: 100 characters
- Python version: 3.11+
- Type hints required (mypy strict mode)
- Format with black
- Lint with ruff (pycodestyle, pyflakes, isort, pep8-naming, flake8-bugbear, flake8-simplify, pyupgrade)

### Project Status

Currently in alpha (v0.1.0). Active development focusing on MVP features and plugin system. See README.md roadmap for upcoming phases.
