# Commandes importantes pour le développement

## Installation et setup

### Installer uv (si pas déjà installé)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Installer les dépendances
```bash
# Avec toutes les dépendances de développement
uv sync --all-extras

# Ou via make
make install
```

### Sync des dépendances (après modification de pyproject.toml)
```bash
uv sync
# ou
make sync
```

## Exécution de l'application

```bash
# Via uv
uv run jukebox

# Via make
make run

# Directement avec Python
uv run python -m jukebox.main
```

## Tests

```bash
# Exécuter tous les tests avec couverture
uv run pytest
# ou
make test

# Test d'un fichier spécifique
uv run pytest tests/core/test_audio_player.py

# Test d'une fonction spécifique
uv run pytest tests/core/test_audio_player.py::test_load_file

# Avec options personnalisées
uv run pytest -v --cov=jukebox --cov-report=html
```

## Qualité de code

### Formatage
```bash
# Formatter le code avec black
uv run black jukebox tests

# Formatter et auto-fix avec ruff
uv run ruff check --fix jukebox tests

# Ou via make (fait les deux)
make format
```

### Linting
```bash
# Vérifier le code avec ruff
uv run ruff check jukebox tests

# Ou via make
make lint
```

### Type checking
```bash
# Vérifier les types avec mypy
uv run mypy jukebox

# Ou via make
make type-check
```

### Toutes les vérifications CI
```bash
# Exécute: format + lint + type-check + test
make ci
```

## Nettoyage

```bash
# Nettoyer les artefacts de build et cache
make clean
```

Cela supprime:
- `dist`, `build`, `*.egg-info`
- `.pytest_cache`, `.mypy_cache`, `.ruff_cache`
- `htmlcov`, `.coverage`, `coverage.xml`
- `__pycache__` directories
- `*.pyc` files
- `jukebox.log`
- `uv.lock`

## Git workflow

```bash
# Status
git status

# Ajouter des modifications
git add <files>

# Commit (pre-commit hooks s'exécutent automatiquement)
git commit -m "message"

# Push
git push
```

## Développement de plugins

Les plugins sont dans `plugins/` et doivent être activés dans `config/config.yaml`:

```yaml
plugins:
  enabled:
    - my_plugin
```

## Base de données

La base de données SQLite est située à:
- `~/.jukebox/jukebox.db` (production)
- `jukebox.db` (développement local)

## Logs

Les logs sont écrits dans:
- `jukebox.log` (racine du projet)
- Niveau configurable dans `config/config.yaml` (logging.level)

## Système (Darwin/macOS)

Commandes système utiles:
- `ls`, `cd`, `pwd` - Navigation
- `grep`, `find` - Recherche
- `cat`, `less` - Lecture de fichiers
- `rm`, `mv`, `cp` - Manipulation de fichiers

Note: Sur macOS (Darwin), certaines commandes peuvent différer légèrement de Linux.
