# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup
```bash
# Install dependencies (requires uv: https://astral.sh/uv)
uv sync --all-extras
```
VLC is a required runtime dependency; see [README.md](README.md#installation) for per-OS install.

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

**Duplicate Detection** (curating mode only): `DuplicateChecker` scans curating tracks against the jukebox library using a three-pass strategy: (1) exact artist+title match → RED, (2) filename-parsed artist/title match → RED or ORANGE, (3) fuzzy filename match via token-accelerated SequenceMatcher ≥ 0.8 → ORANGE. Results appear as a colored dot column (`●`) at the far right of the track list. The check runs in a `BackgroundCheckWorker` (QThread) so the UI stays responsive; results are keyed by filepath to survive concurrent list modifications.

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

Plugins implement the `JukeboxPlugin` protocol (`initialize`, `register_ui`, `shutdown`), live in
`plugins/`, and are enabled in `config/config.yaml` under `plugins.enabled`. See
[README.md](README.md#plugin-development) for the full protocol example, the PluginContext /
UIBuilder APIs, and the list of standard events (also defined in `jukebox/core/event_bus.py`).

### Key Files

- `jukebox/main.py` - Application entry point
- `jukebox/ui/main_window.py` - Main window with application state
- `jukebox/core/audio_player.py` - VLC wrapper with Qt signals
- `jukebox/core/database.py` - SQLite database with FTS5 search
- `jukebox/core/event_bus.py` - Event pub/sub system
- `jukebox/core/plugin_manager.py` - Plugin lifecycle management
- `jukebox/core/duplicate_checker.py` - Three-pass duplicate detection engine (curating mode)
- `jukebox/ui/ui_builder.py` - Plugin UI injection API
- `jukebox/ui/components/track_list.py` - Track table model + BackgroundCheckWorker
- `jukebox/ui/components/track_cell_renderer.py` - Per-column cell stylers (incl. DuplicateStatusStyler)
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

## grepai - Semantic Code Search

Use `grepai search` as the PRIMARY tool for code exploration — finding code by intent ("where/how
does X work"). Use plain Grep/Glob only for exact text (symbol names, imports) or path patterns. If
grepai is unavailable or errors, fall back to Grep/Glob.

```bash
# Search by intent — query in English; --compact saves ~80% tokens
grepai search "inline comment edit persistence" --json --compact

# Trace a symbol before modifying it (callers / callees / full graph)
grepai trace callers "save_audio_tags" --json
grepai trace graph "AudioPlayer" --depth 3 --json
```

Query in English, describe intent rather than implementation, and be specific. Results give file
paths + line numbers — open them with `Read`.

## Engineering rules

- Les I/O bloquantes (écriture de tags audio, accès disque) ne s'exécutent jamais sur le thread UI ; les déporter sur un worker QThread.
- Après toute édition de métadonnées d'un morceau, émettre TRACK_METADATA_UPDATED pour rafraîchir les vues abonnées.
- make type-check (mypy) doit couvrir plugins/ et tests/, pas uniquement jukebox/.
- Toute nouvelle branche conditionnelle ou comportement limite (fallback, valeur vide/blanche, ordre de tri, chemin d'erreur) DOIT être couvert par un test ; pas de branche non testée.
- Interdire les # type: ignore et suppressions mypy/pyright génériques (module-wide, follow_imports=silent) qui masquent de vraies erreurs ; cibler chaque ignore sur un code d'erreur précis et justifié en commentaire.
