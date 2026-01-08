# Contributing to Jukebox

Thank you for your interest in contributing to Jukebox! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Commit Message Guidelines](#commit-message-guidelines)

## Code of Conduct

This project follows a Code of Conduct that all contributors are expected to adhere to:

- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on what is best for the community
- Show empathy towards other community members

## Getting Started

### Prerequisites

- Python 3.11 or higher
- VLC media player
- uv (will be installed automatically)
- Git

### Setup Development Environment

1. **Fork the repository** on GitHub

2. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/jukebox.git
   cd jukebox
   ```

3. **Add upstream remote**:
   ```bash
   git remote add upstream https://github.com/yourusername/jukebox.git
   ```

4. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

5. **Install dependencies**:
   ```bash
   uv sync --all-extras
   ```

6. **Install pre-commit hooks**:
   ```bash
   uv run pre-commit install
   ```

7. **Verify setup**:
   ```bash
   make ci
   ```

## Development Workflow

### Before Starting Work

1. **Sync with upstream**:
   ```bash
   git fetch upstream
   git checkout main
   git merge upstream/main
   ```

2. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

### During Development

1. **Make your changes** following the coding standards

2. **Run tests frequently**:
   ```bash
   make test
   ```

3. **Check code quality**:
   ```bash
   make format  # Format code
   make lint    # Check linting
   make type-check  # Type checking
   ```

4. **Run all checks**:
   ```bash
   make ci
   ```

### Committing Changes

Pre-commit hooks will automatically run on `git commit`. They will:
- Format code with Black
- Lint with Ruff
- Check types with MyPy
- Run security checks with Bandit
- Check YAML, JSON, TOML files

If hooks fail, fix the issues and commit again.

## Pull Request Process

### 1. Prepare Your PR

- Ensure all tests pass: `make ci`
- Update documentation if needed
- Add tests for new features
- Update CHANGELOG.md

### 2. Submit Your PR

1. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create Pull Request** on GitHub

3. **Fill out the PR template**:
   - Clear description of changes
   - Link to related issues
   - Screenshots if UI changes
   - Checklist completed

### 3. PR Review Process

- Maintainers will review your PR
- Address any requested changes
- Once approved, your PR will be merged

### 4. After Merge

- Delete your feature branch
- Sync your fork with upstream

## Coding Standards

### Python Style Guide

We follow PEP 8 with these tools:

- **Black** (line length: 100)
- **Ruff** for linting
- **MyPy** for type checking (strict mode)

### Code Quality Rules

1. **Type Hints**: All functions must have type hints
   ```python
   def example_function(param: str) -> bool:
       """Docstring here."""
       return True
   ```

2. **Docstrings**: All public functions need docstrings
   ```python
   def function(param: str) -> bool:
       """Short description.

       Args:
           param: Description

       Returns:
           Description

       Raises:
           ValueError: When...
       """
   ```

3. **No unused imports**: Remove all unused code

4. **Error handling**: Handle errors gracefully
   ```python
   try:
       result = risky_operation()
   except SpecificError as e:
       logger.error(f"Operation failed: {e}")
       return None
   ```

### File Organization

- One class per file (with exceptions for small helper classes)
- Group imports: stdlib, third-party, local
- Maximum line length: 100 characters

## Testing Guidelines

### Writing Tests

1. **Test files**: Mirror source structure in `tests/`
   ```
   jukebox/core/config.py  →  tests/core/test_config.py
   ```

2. **Test naming**: `test_<what_it_tests>`
   ```python
   def test_config_loads_successfully():
       """Test configuration loads from YAML."""
       ...
   ```

3. **Use fixtures**: Share setup between tests
   ```python
   @pytest.fixture
   def sample_config():
       return JukeboxConfig(...)
   ```

4. **Coverage**: Aim for >70% coverage
   ```bash
   make test
   # View report: open htmlcov/index.html
   ```

### Test Types

- **Unit tests**: Test individual functions/classes
- **Integration tests**: Test component interaction
- **UI tests**: Use pytest-qt for Qt widgets

### Running Tests

```bash
# All tests
make test

# Specific file
uv run pytest tests/core/test_config.py

# With verbose output
uv run pytest -v

# Stop on first failure
uv run pytest -x

# Run only failed tests
uv run pytest --lf
```

## Commit Message Guidelines

We follow [Conventional Commits](https://www.conventionalcommits.org/).

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting, missing semicolons, etc
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `perf`: Performance improvement
- `test`: Adding missing tests
- `chore`: Maintenance tasks
- `ci`: CI/CD changes

### Examples

```bash
# Feature
git commit -m "feat(player): add position slider auto-update"

# Bug fix
git commit -m "fix(ui): resolve position slider not advancing"

# Documentation
git commit -m "docs: update README with uv installation"

# Multiple paragraphs
git commit -m "feat(search): add FTS5 full-text search

Implements SQLite FTS5 for fast track searching.
Includes fuzzy matching and ranking.

Closes #123"
```

### Commit Message Rules

- Use present tense ("add" not "added")
- Use imperative mood ("move cursor" not "moves cursor")
- Capitalize first letter
- No period at the end
- Reference issues: "Closes #123" or "Fixes #456"
- Keep subject line under 50 characters
- Wrap body at 72 characters

## Additional Resources

### Project Structure

```
jukebox/
├── jukebox/           # Source code
│   ├── core/          # Core functionality
│   ├── ui/            # User interface
│   └── utils/         # Utilities
├── tests/             # Test suite
├── docs/              # Documentation
├── Roadmap/           # Development roadmap
└── .github/           # GitHub workflows
```

### Useful Commands

```bash
make help          # Show all available commands
make install       # Install dependencies
make run           # Run application
make test          # Run tests with coverage
make ci            # Run all checks
make format        # Format code
make lint          # Check linting
make type-check    # Type checking
make clean         # Clean build artifacts
```

### Documentation

- [Development Guide](docs/DEVELOPMENT.md)
- [Roadmap](Roadmap/00-OVERVIEW.md)
- [Quick Start](QUICKSTART.md)

### Communication

- **Issues**: Report bugs or request features
- **Discussions**: Ask questions or discuss ideas
- **Pull Requests**: Submit code contributions

## Questions?

If you have questions:

1. Check the [documentation](docs/)
2. Search [existing issues](https://github.com/yourusername/jukebox/issues)
3. Open a new issue with the question label

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for contributing to Jukebox! 🎵**
