# Phase 2: CI/CD & Quality Infrastructure

**Durée**: Semaine 2 (parallèle à fin Phase 1)
**Objectif**: Pipeline CI/CD automatisé avec contrôles qualité
**Milestone**: `v0.2.0-alpha`

---

## Vue d'Ensemble

Cette phase établit l'infrastructure de qualité et de déploiement automatisé. **Cette phase doit être implémentée tôt** pour garantir la qualité du code dès le début du projet.

À la fin de cette phase :
- Chaque commit déclenche des tests automatiques
- Le code est vérifié automatiquement (linting, type checking)
- Des packages distribuables sont générés automatiquement
- Pre-commit hooks préviennent les commits de mauvaise qualité

**Philosophie**: "Automatiser tout ce qui peut l'être, échouer rapidement"

---

## Tâches Détaillées

### 2.1 GitHub Actions Setup (Jour 1)

#### 2.1.1 Workflow CI Principal
Créer `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    name: Test Python ${{ matrix.python-version }} on ${{ matrix.os }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: ["3.11", "3.12"]

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install Poetry
        uses: snok/install-poetry@v1
        with:
          version: 1.7.1
          virtualenvs-create: true
          virtualenvs-in-project: true

      - name: Load cached venv
        id: cached-poetry-dependencies
        uses: actions/cache@v3
        with:
          path: .venv
          key: venv-${{ runner.os }}-${{ matrix.python-version }}-${{ hashFiles('**/poetry.lock') }}

      - name: Install dependencies
        if: steps.cached-poetry-dependencies.outputs.cache-hit != 'true'
        run: poetry install --no-interaction --no-root

      - name: Install project
        run: poetry install --no-interaction

      - name: Run tests
        run: |
          poetry run pytest --cov=jukebox --cov-report=xml --cov-report=term

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          fail_ci_if_error: false

  lint:
    name: Lint and Type Check
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install Poetry
        uses: snok/install-poetry@v1

      - name: Install dependencies
        run: poetry install --no-interaction

      - name: Run Black
        run: poetry run black --check jukebox tests

      - name: Run Ruff
        run: poetry run ruff check jukebox tests

      - name: Run MyPy
        run: poetry run mypy jukebox

  security:
    name: Security Scan
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install Poetry
        uses: snok/install-poetry@v1

      - name: Install dependencies
        run: poetry install --no-interaction

      - name: Run Bandit security scan
        run: |
          poetry add --group dev bandit
          poetry run bandit -r jukebox -f json -o bandit-report.json || true

      - name: Upload security report
        uses: actions/upload-artifact@v3
        with:
          name: bandit-report
          path: bandit-report.json
```

**Critères d'acceptation**:
- ✅ Workflow créé et activé
- ✅ Tests s'exécutent sur 3 OS
- ✅ Tests s'exécutent sur Python 3.11 et 3.12
- ✅ Cache Poetry fonctionne

---

#### 2.1.2 Workflow Build Packages
Créer `.github/workflows/build.yml`:

```yaml
name: Build Packages

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:

jobs:
  build-pyinstaller:
    name: Build with PyInstaller on ${{ matrix.os }}
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        include:
          - os: ubuntu-latest
            artifact_name: jukebox-linux
            asset_name: jukebox-linux.tar.gz
          - os: macos-latest
            artifact_name: jukebox-macos
            asset_name: jukebox-macos.dmg
          - os: windows-latest
            artifact_name: jukebox-windows
            asset_name: jukebox-windows.exe

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install Poetry
        uses: snok/install-poetry@v1

      - name: Install dependencies
        run: poetry install --no-interaction

      - name: Install PyInstaller
        run: poetry add --group dev pyinstaller

      - name: Build with PyInstaller (Unix)
        if: runner.os != 'Windows'
        run: |
          poetry run pyinstaller \
            --name=jukebox \
            --windowed \
            --add-data="config:config" \
            --hidden-import=PySide6 \
            jukebox/main.py

      - name: Build with PyInstaller (Windows)
        if: runner.os == 'Windows'
        run: |
          poetry run pyinstaller `
            --name=jukebox `
            --windowed `
            --add-data="config;config" `
            --hidden-import=PySide6 `
            jukebox/main.py

      - name: Create tarball (Unix)
        if: runner.os != 'Windows'
        run: |
          cd dist
          tar -czf ${{ matrix.artifact_name }}.tar.gz jukebox/

      - name: Create zip (Windows)
        if: runner.os == 'Windows'
        run: |
          cd dist
          Compress-Archive -Path jukebox -DestinationPath ${{ matrix.artifact_name }}.zip

      - name: Upload artifact
        uses: actions/upload-artifact@v3
        with:
          name: ${{ matrix.artifact_name }}
          path: dist/${{ matrix.artifact_name }}.*

  build-wheel:
    name: Build Python Wheel
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install Poetry
        uses: snok/install-poetry@v1

      - name: Build wheel
        run: poetry build

      - name: Upload wheel
        uses: actions/upload-artifact@v3
        with:
          name: python-wheel
          path: dist/*.whl

  create-release:
    name: Create GitHub Release
    needs: [build-pyinstaller, build-wheel]
    runs-on: ubuntu-latest
    if: startsWith(github.ref, 'refs/tags/')

    steps:
      - name: Download all artifacts
        uses: actions/download-artifact@v3

      - name: Create Release
        uses: softprops/action-gh-release@v1
        with:
          files: |
            jukebox-linux/*
            jukebox-macos/*
            jukebox-windows/*
            python-wheel/*
          draft: false
          prerelease: ${{ contains(github.ref, 'alpha') || contains(github.ref, 'beta') }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Critères d'acceptation**:
- ✅ Build fonctionne sur 3 OS
- ✅ Packages créés automatiquement
- ✅ Release GitHub créée pour les tags

---

### 2.2 Pre-commit Hooks (Jour 1)

#### 2.2.1 Configuration .pre-commit-config.yaml
Créer `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: ['--maxkb=500']
      - id: check-merge-conflict
      - id: check-json
      - id: check-toml
      - id: detect-private-key

  - repo: https://github.com/psf/black
    rev: 23.12.1
    hooks:
      - id: black
        language_version: python3.11

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.9
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.1
    hooks:
      - id: mypy
        additional_dependencies:
          - types-PyYAML
          - pydantic
        args: [--strict]

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.6
    hooks:
      - id: bandit
        args: [-r, jukebox, -f, screen]
        exclude: tests/

  - repo: local
    hooks:
      - id: pytest-check
        name: pytest-check
        entry: poetry run pytest
        language: system
        pass_filenames: false
        always_run: true
```

#### 2.2.2 Installation des hooks
```bash
# Installer pre-commit
poetry add --group dev pre-commit

# Installer les hooks
poetry run pre-commit install

# Tester tous les fichiers
poetry run pre-commit run --all-files
```

**Critères d'acceptation**:
- ✅ Pre-commit hooks installés
- ✅ Hooks s'exécutent avant chaque commit
- ✅ Tous les checks passent

---

### 2.3 Outils de Qualité (Jour 2)

#### 2.3.1 Configuration Ruff avancée
Ajouter dans `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

# Enable specific rule sets
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "N",    # pep8-naming
    "B",    # flake8-bugbear
    "SIM",  # flake8-simplify
    "UP",   # pyupgrade
    "ANN",  # flake8-annotations
    "S",    # flake8-bandit
    "C4",   # flake8-comprehensions
    "DTZ",  # flake8-datetimez
    "PIE",  # flake8-pie
    "PT",   # flake8-pytest-style
    "RET",  # flake8-return
    "RSE",  # flake8-raise
]

# Ignore specific rules
ignore = [
    "ANN101",  # Missing type annotation for self
    "ANN102",  # Missing type annotation for cls
]

# Exclude directories
exclude = [
    ".git",
    "__pycache__",
    ".venv",
    "build",
    "dist",
]

[tool.ruff.per-file-ignores]
"tests/*" = ["S101"]  # Allow assert in tests
```

#### 2.3.2 Configuration MyPy avancée
Ajouter dans `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_any_unimported = false
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
check_untyped_defs = true
strict_equality = true

# Per-module options
[[tool.mypy.overrides]]
module = "vlc.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

#### 2.3.3 Configuration Coverage
Ajouter dans `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["jukebox"]
omit = [
    "*/tests/*",
    "*/__init__.py",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]
precision = 2
show_missing = true
skip_covered = false

[tool.coverage.html]
directory = "htmlcov"
```

**Critères d'acceptation**:
- ✅ Ruff configuré avec règles strictes
- ✅ MyPy en mode strict
- ✅ Coverage configuré avec exclusions

---

### 2.4 Scripts de Développement (Jour 2)

#### 2.4.1 Makefile pour commandes courantes
Créer `Makefile`:

```makefile
.PHONY: help install test lint format type-check security clean build run

help:
	@echo "Available commands:"
	@echo "  make install      Install dependencies"
	@echo "  make test         Run tests with coverage"
	@echo "  make lint         Run linting checks"
	@echo "  make format       Format code"
	@echo "  make type-check   Run type checking"
	@echo "  make security     Run security scan"
	@echo "  make clean        Clean build artifacts"
	@echo "  make build        Build distribution packages"
	@echo "  make run          Run application"
	@echo "  make ci           Run all CI checks"

install:
	poetry install

test:
	poetry run pytest --cov=jukebox --cov-report=html --cov-report=term -v

lint:
	poetry run ruff check jukebox tests

format:
	poetry run black jukebox tests
	poetry run ruff check --fix jukebox tests

type-check:
	poetry run mypy jukebox

security:
	poetry run bandit -r jukebox

clean:
	rm -rf dist build *.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build:
	poetry build

run:
	poetry run python -m jukebox.main

# Run all CI checks locally
ci: format lint type-check test security
	@echo "All CI checks passed!"
```

#### 2.4.2 Script de développement
Créer `scripts/dev.sh`:

```bash
#!/bin/bash
# Development helper script

set -e

function setup() {
    echo "Setting up development environment..."
    poetry install
    poetry run pre-commit install
    echo "Setup complete!"
}

function check() {
    echo "Running all checks..."
    make format
    make lint
    make type-check
    make test
    make security
    echo "All checks passed!"
}

function watch() {
    echo "Watching for changes and running tests..."
    poetry run ptw -- --testmon
}

case "$1" in
    setup)
        setup
        ;;
    check)
        check
        ;;
    watch)
        watch
        ;;
    *)
        echo "Usage: $0 {setup|check|watch}"
        exit 1
        ;;
esac
```

```bash
chmod +x scripts/dev.sh
```

**Critères d'acceptation**:
- ✅ Makefile avec commandes utiles
- ✅ Script dev.sh fonctionnel
- ✅ `make ci` exécute tous les checks

---

### 2.5 Badges et Documentation CI (Jour 3)

#### 2.5.1 Ajouter badges au README
Modifier `README.md`:

```markdown
# Jukebox

[![CI](https://github.com/yourusername/jukebox/workflows/CI/badge.svg)](https://github.com/yourusername/jukebox/actions)
[![codecov](https://codecov.io/gh/yourusername/jukebox/branch/main/graph/badge.svg)](https://codecov.io/gh/yourusername/jukebox)
[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A modular audio jukebox application for Mac, Linux, and Raspberry Pi.

[Rest of README...]
```

#### 2.5.2 Créer CONTRIBUTING.md
Créer `CONTRIBUTING.md`:

```markdown
# Contributing to Jukebox

Thank you for your interest in contributing!

## Development Setup

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/yourusername/jukebox.git
   cd jukebox
   ```
3. Set up development environment:
   ```bash
   ./scripts/dev.sh setup
   # or
   make install
   poetry run pre-commit install
   ```

## Development Workflow

### Before committing

Run all checks:
```bash
make ci
# or
./scripts/dev.sh check
```

Pre-commit hooks will automatically run on `git commit`.

### Running tests

```bash
make test
# or
poetry run pytest
```

### Code style

We use:
- **black** for formatting
- **ruff** for linting
- **mypy** for type checking

Format code:
```bash
make format
```

### Pull Request Process

1. Create a feature branch: `git checkout -b feature/amazing-feature`
2. Make your changes
3. Ensure all tests pass: `make ci`
4. Commit with clear message
5. Push to your fork
6. Open a Pull Request

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat: add new feature`
- `fix: resolve bug`
- `docs: update documentation`
- `refactor: restructure code`
- `test: add tests`
- `ci: update CI configuration`

### Code Review

All submissions require review. We'll review your PR and may suggest changes.

## Questions?

Open an issue for discussion!
```

**Critères d'acceptation**:
- ✅ Badges ajoutés au README
- ✅ CONTRIBUTING.md créé
- ✅ Documentation CI à jour

---

### 2.6 Dependabot Configuration (Jour 3)

Créer `.github/dependabot.yml`:

```yaml
version: 2
updates:
  # Python dependencies
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10
    reviewers:
      - "yourusername"
    labels:
      - "dependencies"
      - "python"

  # GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    reviewers:
      - "yourusername"
    labels:
      - "dependencies"
      - "github-actions"
```

**Critères d'acceptation**:
- ✅ Dependabot configuré
- ✅ Updates hebdomadaires automatiques
- ✅ PRs automatiques créées

---

## Checklist Phase 2

### GitHub Actions (Jour 1)
- [x] Workflow CI créé et fonctionnel
- [x] Tests s'exécutent sur 3 OS
- [x] Workflow Build créé
- [x] Packages générés automatiquement
- [x] Cache uv fonctionne

### Pre-commit (Jour 1)
- [x] .pre-commit-config.yaml créé
- [x] Hooks installés localement
- [x] Tous les hooks passent

### Outils Qualité (Jour 2)
- [x] Ruff configuré (mode strict)
- [x] MyPy configuré (strict mode)
- [x] Coverage configuré
- [x] Bandit ajouté pour sécurité

### Scripts (Jour 2)
- [x] Makefile créé
- [x] Scripts utilitaires créés
- [x] `make ci` fonctionne

### Documentation (Jour 3)
- [x] Badges ajoutés au README
- [x] CONTRIBUTING.md créé
- [x] Dependabot configuré

### Validation
- [x] Commits passent tous les checks
- [x] Pre-commit configuré
- [x] CI s'exécute automatiquement sur push
- [x] Build packages fonctionne

---

## Livrables Phase 2

### Infrastructure CI/CD
- ✅ GitHub Actions workflows (CI + Build)
- ✅ Pre-commit hooks
- ✅ Scripts de développement
- ✅ Dependabot

### Outils Qualité
- ✅ Ruff (linting)
- ✅ Black (formatting)
- ✅ MyPy (type checking)
- ✅ Pytest + Coverage
- ✅ Bandit (security)

### Documentation
- ✅ CONTRIBUTING.md
- ✅ Badges CI
- ✅ Documentation workflows

---

## Critères de Succès

1. **Automatisation**
   - ✅ Chaque push déclenche CI
   - ✅ Tests s'exécutent sur 3 OS
   - ✅ Packages générés automatiquement

2. **Qualité**
   - ✅ Coverage > 70%
   - ✅ Tous les checks passent
   - ✅ Pre-commit prévient mauvais commits

3. **Developer Experience**
   - ✅ Setup simple (`make install`)
   - ✅ Checks locaux (`make ci`)
   - ✅ Documentation claire

---

## Maintenance Continue

### Hebdomadaire
- Vérifier Dependabot PRs
- Merger updates de dépendances

### Par Commit
- Pre-commit hooks s'exécutent
- CI valide le code

### Par Release
- Build packages automatique
- Tests sur toutes plateformes

---

## Prochaine Phase

Une fois Phase 2 complète :
➡️ [Phase 3 - Testing & Quality](03-TESTING-QUALITY.md)

---

**Durée estimée**: 3-4 jours
**Effort**: ~20-25 heures
**Complexité**: Moyenne
**Impact**: 🔥 Critique - Foundation pour tout le projet
