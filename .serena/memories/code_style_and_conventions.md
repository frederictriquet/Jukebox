# Style de code et conventions

## Standards généraux

### Version Python
- Python 3.11+ minimum requis
- Utilisation des fonctionnalités modernes de Python

### Longueur de ligne
- **100 caractères maximum** (géré par black)

### Formatage
- Utilise **black** pour le formatage automatique
- Configuration: ligne 100 caractères, target Python 3.11

## Type hints
- **Obligatoires** pour toutes les fonctions et méthodes
- mypy en mode strict activé:
  - `warn_return_any = true`
  - `disallow_untyped_defs = true`
  - `no_implicit_optional = true`
  - `warn_redundant_casts = true`
  - `warn_unused_ignores = true`

### Exceptions mypy
- `vlc.*` - ignore_missing_imports
- `mutagen.*` - ignore_missing_imports

## Linting (Ruff)

### Règles activées
- **E** - Erreurs pycodestyle
- **W** - Avertissements pycodestyle
- **F** - pyflakes
- **I** - isort (tri des imports)
- **N** - pep8-naming (conventions de nommage)
- **B** - flake8-bugbear (bugs communs)
- **SIM** - flake8-simplify (simplifications)
- **UP** - pyupgrade (modernisation Python)

### Règles ignorées
- **E501** - Ligne trop longue (géré par black)
- **SIM105** - contextlib.suppress (préférence pour try-except explicite)

## Conventions de nommage

### Classes
- PascalCase: `AudioPlayer`, `MainWindow`, `EventBus`

### Fonctions et méthodes
- snake_case: `load_file`, `get_tracks`, `on_track_loaded`

### Constantes
- UPPER_SNAKE_CASE: `DEFAULT_VOLUME`, `MAX_TRACKS`

### Variables privées
- Préfixe underscore: `_internal_state`, `_cache`

## Docstrings
- Style requis pour les fonctions publiques
- Format recommandé: Google style ou NumPy style
- Inclure les descriptions de paramètres et retours

## Imports
- Organisés par ruff/isort
- Ordre standard:
  1. Standard library
  2. Third-party packages
  3. Local imports
- Imports absolus préférés

## Tests

### Structure
- Tests miroirs de la structure source
- Nommage: `test_*.py` pour les fichiers
- Classes: `Test*`
- Fonctions: `test_*`

### Couverture
- Minimum requis: **70%**
- Exclusions:
  - `*/tests/*`
  - `*/__init__.py`
  - Lignes avec `pragma: no cover`
  - `if __name__ == .__main__.:`
  - `if TYPE_CHECKING:`
  - `@abstractmethod`
  - `def __repr__`, `def __str__`
  - `raise AssertionError`, `raise NotImplementedError`

### Framework
- pytest avec:
  - pytest-qt pour tester les composants Qt
  - pytest-cov pour la couverture
  - Mocks VLC dans `tests/pytest_vlc_mock.py`

## Fichiers exclus du formatage/lint
- `.eggs`
- `.git`, `.hg`
- `.mypy_cache`, `.tox`, `.venv`
- `_build`, `buck-out`, `build`, `dist`
- `__pycache__`

## Pre-commit hooks
- Configuré via `.pre-commit-config.yaml`
- Exécute automatiquement:
  - black (formatage)
  - ruff (linting)
  - mypy (type checking)
