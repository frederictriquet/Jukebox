# Development Guide

## Setup Development Environment

### Prerequisites

- Python 3.11 or higher
- uv for dependency management
- VLC media player

### Initial Setup

```bash
# Clone repository
git clone https://github.com/yourusername/jukebox.git
cd jukebox

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync --all-extras

# Install pre-commit hooks (Phase 2)
# uv run pre-commit install
```

## Running the Application

```bash
# Run directly
uv run python -m jukebox.main

# Or use the configured script
uv run jukebox

# Or use make
make run
```

## Development Workflow

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=jukebox --cov-report=html

# Run specific test file
uv run pytest tests/core/test_config.py

# Run with verbose output
uv run pytest -v

# Or use make
make test
```

### Code Style

We use:
- **black** for code formatting
- **ruff** for linting
- **mypy** for type checking

```bash
# Format code
uv run black jukebox tests

# Lint code
uv run ruff check jukebox tests

# Fix linting issues automatically
uv run ruff check --fix jukebox tests

# Type check
uv run mypy jukebox
```

### Running All Checks

```bash
# Run all quality checks
make ci
```

## Project Structure

```
jukebox/
├── jukebox/           # Main package
│   ├── core/          # Core functionality
│   ├── ui/            # User interface
│   ├── utils/         # Utilities
│   └── main.py        # Entry point
├── tests/             # Test suite
├── config/            # Configuration
├── docs/              # Documentation
├── scripts/           # Helper scripts
└── Roadmap/           # Development roadmap
```

## Adding New Features

1. Check the [Roadmap](../Roadmap/00-OVERVIEW.md) for planned features
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Implement the feature with tests
4. Ensure all tests pass: `poetry run pytest`
5. Format and lint: `poetry run black . && poetry run ruff check .`
6. Commit with clear message
7. Push and create a Pull Request

## Commit Message Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat: add new feature`
- `fix: resolve bug`
- `docs: update documentation`
- `refactor: restructure code`
- `test: add tests`
- `ci: update CI configuration`
- `chore: update dependencies`

## Testing Guidelines

### Writing Tests

- Place tests in `tests/` directory mirroring source structure
- Use pytest fixtures for common setup
- Aim for >70% code coverage
- Test both happy path and error cases

### Example Test

```python
import pytest
from jukebox.core.config import AudioConfig

def test_audio_config_defaults():
    """Test AudioConfig default values."""
    config = AudioConfig()
    assert config.default_volume == 70
    assert "mp3" in config.supported_formats

def test_audio_config_validation():
    """Test AudioConfig validation."""
    with pytest.raises(ValueError):
        AudioConfig(default_volume=150)  # > 100
```

## Debugging

### Enable Debug Logging

Edit `config/config.yaml`:

```yaml
logging:
  level: "DEBUG"
  file: "jukebox.log"
```

### Using Python Debugger

```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use built-in breakpoint()
breakpoint()
```

### VSCode Launch Configuration

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Jukebox",
      "type": "python",
      "request": "launch",
      "module": "jukebox.main",
      "console": "integratedTerminal",
      "justMyCode": false
    }
  ]
}
```

## Common Issues

### VLC Not Found

**Error**: `ModuleNotFoundError: No module named 'vlc'`

**Solution**: Install VLC media player on your system (see README.md)

### Qt Platform Plugin Error

**Error**: `qt.qpa.plugin: Could not load the Qt platform plugin`

**Solution**: Ensure PySide6 is properly installed: `poetry install --sync`

### Permission Denied on Config

**Error**: `PermissionError: [Errno 13] Permission denied: 'config/config.yaml'`

**Solution**: Check file permissions or create user config in `~/.config/jukebox/`

## Getting Help

- Check the [Roadmap](../Roadmap/00-OVERVIEW.md) for project status
- Read the [README](../README.md) for basic usage
- Open an issue on GitHub for bugs or questions

## Phase-Specific Development

### Current Phase: MVP Foundation (Phase 1)

Focus areas:
- Core audio playback functionality
- Basic UI components
- Configuration management
- Initial testing

### Next Phase: CI/CD (Phase 2)

Will add:
- GitHub Actions workflows
- Automated testing pipeline
- Pre-commit hooks
- Build automation

See [Roadmap/02-CI-CD-SETUP.md](../Roadmap/02-CI-CD-SETUP.md) for details.
