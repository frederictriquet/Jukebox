# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Position slider now updates automatically during playback (100ms refresh rate)
- QTimer-based position tracking
- Tests for position slider auto-update functionality
- CHANGELOG.md file
- QUICKSTART.md with uv installation guide
- Setup script for automated installation
- `.python-version` file for uv

### Changed
- Migrated from Poetry to uv for dependency management
- Updated all documentation to use uv commands
- Play/Pause/Stop controls now properly manage position timer

### Fixed
- **Bug**: Position slider not advancing during playback
  - Added QTimer to update position every 100ms
  - Timer starts on play, stops on pause/stop
  - Stop button now resets position to 0

## [0.1.0-alpha] - 2026-01-08

### Added
- Initial MVP release
- Basic audio playback with python-vlc
- PySide6-based user interface
- Track list widget
- Player controls (play, pause, stop)
- Volume control slider
- Position seeking slider (manual)
- YAML configuration with Pydantic validation
- Logging system
- Test suite with pytest
- Development tools (black, ruff, mypy)
- Makefile with common commands
- Project documentation
- MIT License

### Core Features
- Support for MP3, FLAC, AIFF, WAV formats
- File selection dialog
- Double-click to play tracks
- Window title updates with current track

### Development
- Project structure with modular architecture
- Type hints throughout codebase
- Comprehensive test coverage
- Documentation in docs/DEVELOPMENT.md
- Detailed roadmap in Roadmap/ directory

[unreleased]: https://github.com/yourusername/jukebox/compare/v0.1.0-alpha...HEAD
[0.1.0-alpha]: https://github.com/yourusername/jukebox/releases/tag/v0.1.0-alpha
