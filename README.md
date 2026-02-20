# Jukebox

[![CI](https://github.com/yourusername/jukebox/workflows/CI/badge.svg)](https://github.com/yourusername/jukebox/actions)
[![codecov](https://codecov.io/gh/yourusername/jukebox/branch/main/graph/badge.svg)](https://codecov.io/gh/yourusername/jukebox)
[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A modular audio jukebox application for Mac, Linux, and Raspberry Pi.

## Features (v0.1.0-alpha)

- 🎵 Audio playback (MP3, FLAC, AIFF, WAV)
- 📋 Simple track list
- ⏯️ Playback controls (play, pause, stop)
- 🔊 Volume control
- 📍 Position seeking
- ⚙️ YAML configuration with Pydantic validation

## Requirements

- Python 3.11+
- VLC media player (for python-vlc backend)

## Installation

### Install VLC

#### macOS
```bash
brew install vlc
```

#### Ubuntu/Debian
```bash
sudo apt-get install vlc libvlc-dev
```

#### Arch Linux
```bash
sudo pacman -S vlc
```

### Install Jukebox

```bash
# Clone repository
git clone https://github.com/yourusername/jukebox.git
cd jukebox

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync --all-extras

# Run application
uv run jukebox
```

## Configuration

Edit `config/config.yaml` to customize settings:

```yaml
audio:
  default_volume: 70
  supported_formats:
    - mp3
    - flac
    - aiff
    - wav
  music_directory: ~/Music

ui:
  window_title: "Jukebox"
  window_width: 1024
  window_height: 768
  theme: "dark"

logging:
  level: "INFO"
  file: "jukebox.log"
```

## Usage

1. Launch Jukebox
2. Click "Add Files..." to select audio files
3. Double-click a track to play
4. Use controls to manage playback

### Keyboard Shortcuts (Coming Soon)

| Shortcut | Action |
|----------|--------|
| Space | Play/Pause |
| Ctrl+P | Pause |
| Ctrl+S | Stop |

## Plugins

Jukebox features an extensible plugin system. Plugins can add UI elements, respond to events, and extend functionality without modifying core code.

### Available Plugins

#### Directory Navigator
Navigate and filter tracks by directory structure in jukebox mode.

- **Status**: ✅ Stable
- **Mode**: Jukebox
- **Description**: Adds a tree view in the left sidebar showing the hierarchical structure of your music directories with track counts. Click on directories, playlists, or "All Tracks" to filter the track list.
- **Features**:
  - Hierarchical directory tree with automatic common prefix detection
  - Recursive filtering (shows all tracks in subdirectories)
  - Playlist integration
  - Real-time track count updates
- **Documentation**: See [plugins/README_directory_navigator.md](plugins/README_directory_navigator.md)

Enable in `config/config.yaml`:
```yaml
plugins:
  enabled:
    - directory_navigator
```

#### Genre Filter
Filter tracks by genre in jukebox mode with interactive toggle buttons.

- **Status**: ✅ Stable
- **Mode**: Jukebox
- **Description**: Adds toolbar buttons for each genre code (H, T, W, etc.). Each button has 3 states:
  - Gray (indifferent): Genre not considered
  - Green (ON): Track must have this genre
  - Red (OFF): Track must NOT have this genre
- **Documentation**: See [plugins/README_genre_filter.md](plugins/README_genre_filter.md)

Enable in `config/config.yaml`:
```yaml
plugins:
  enabled:
    - genre_filter
```

#### Cue Maker
Create cue sheets for DJ mixes with automatic track recognition in cue_maker mode.

- **Status**: ✅ Stable
- **Mode**: Cue Maker
- **Description**: Dedicated mode for analyzing DJ mixes and generating standard .cue files. Uses audio fingerprinting (shazamix) to automatically identify tracks in a mix, with manual editing capabilities.
- **Features**:
  - Automatic track identification via audio fingerprinting
  - Manual timestamp and metadata editing
  - Waveform visualization with cue point markers
  - Import metadata from Jukebox library
  - Import existing .cue files for editing
  - Export to standard CUE format (compatible with CDJs, Rekordbox, VirtualDJ)
  - Intelligent caching of fingerprints and waveforms
- **Documentation**: See [plugins/cue_maker/README.md](plugins/cue_maker/README.md)

Enable in `config/config.yaml`:
```yaml
plugins:
  enabled:
    - cue_maker
```

Switch to Cue Maker mode: **Mode** → **Cue Maker Mode**

### Plugin Development

See [CLAUDE.md](CLAUDE.md#plugin-development) for plugin development guide and architecture details.

## Development

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for development setup and guidelines.

### Running Tests

```bash
uv run pytest
# Or use make
make test
```

### Code Quality

```bash
# Format code
uv run black jukebox tests

# Lint
uv run ruff check jukebox tests

# Type check
uv run mypy jukebox

# Or run all checks
make ci
```

## Project Structure

```
jukebox/
├── jukebox/
│   ├── core/           # Core functionality
│   │   ├── audio_player.py
│   │   └── config.py
│   ├── ui/             # User interface
│   │   ├── main_window.py
│   │   └── components/
│   │       ├── player_controls.py
│   │       └── track_list.py
│   ├── utils/          # Utilities
│   │   └── logger.py
│   └── main.py         # Entry point
├── tests/              # Test suite
├── config/             # Configuration files
└── docs/               # Documentation
```

## Roadmap

See [Roadmap/00-OVERVIEW.md](Roadmap/00-OVERVIEW.md) for detailed roadmap.

### Current Phase: MVP Foundation (v0.1.0-alpha)
- ✅ Basic audio playback
- ✅ Simple UI with track list
- ✅ Configuration management
- ✅ Logging

### Next Phase: CI/CD Setup (v0.2.0-alpha)
- GitHub Actions workflows
- Automated testing
- Code quality checks
- Build automation

### Future Phases
- Core features (database, search)
- Plugin system
- Advanced features
- Distribution packages

## Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

Built with:
- [PySide6](https://doc.qt.io/qtforpython-6/) - Qt bindings for Python
- [python-vlc](https://github.com/oaubert/python-vlc) - VLC media player bindings
- [mutagen](https://github.com/quodlibet/mutagen) - Audio metadata library
- [Pydantic](https://docs.pydantic.dev/) - Data validation
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer

## Status

🚧 **Alpha** - Under active development

Current version: **v0.1.0-alpha**
