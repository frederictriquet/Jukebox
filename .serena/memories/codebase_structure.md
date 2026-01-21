# Structure du codebase

## Vue d'ensemble de la structure

```
jukebox/
├── jukebox/              # Code source principal
│   ├── core/            # Fonctionnalités core
│   ├── ui/              # Interface utilisateur
│   ├── utils/           # Utilitaires
│   └── main.py          # Point d'entrée
├── plugins/             # Système de plugins extensibles
├── tests/               # Suite de tests
├── config/              # Fichiers de configuration
├── docs/                # Documentation
├── scripts/             # Scripts utilitaires
├── Roadmap/             # Roadmap du projet
└── tools/               # Outils de développement
```

## jukebox/ - Code source principal

### jukebox/main.py
- Point d'entrée de l'application
- Fonction `main()` appelée via `uv run jukebox`
- Charge la config, setup logging, crée QApplication, initialise MainWindow

### jukebox/core/ - Fonctionnalités core

**Fichiers principaux:**
- `audio_player.py` - Wrapper python-vlc, émission de signaux Qt
- `database.py` - SQLite avec FTS5 pour recherche full-text
- `event_bus.py` - Système pub/sub d'événements, classe Events avec constantes
- `plugin_manager.py` - Gestion du cycle de vie des plugins
- `config.py` - Configuration YAML avec validation Pydantic
- `mode_manager.py` - Gestion des modes (curating/jukebox)
- `shortcut_manager.py` - Gestion des raccourcis clavier
- `shortcut_mixin.py` - Mixin pour raccourcis
- `batch_processor.py` - Traitement par lots

### jukebox/ui/ - Interface utilisateur

**Fichiers principaux:**
- `main_window.py` - Fenêtre principale avec état de l'application
- `ui_builder.py` - API d'injection UI pour plugins
- `theme_manager.py` - Gestion des thèmes (dark/light)

**Sous-répertoire: jukebox/ui/components/**
- Composants UI réutilisables
- Liste des pistes, contrôles de lecture, barre de recherche

### jukebox/utils/ - Utilitaires

Fonctions utilitaires:
- `metadata.py` - Extraction de métadonnées audio (mutagen)
- `scanner.py` - Scan du système de fichiers pour fichiers audio
- `logger.py` - Configuration du logging

## plugins/ - Système de plugins

**Architecture de plugins:**
- Découverte automatique des fichiers `.py` dans `plugins/`
- Activation/désactivation via `config/config.yaml` (`plugins.enabled`)
- Chaque plugin implémente le protocole JukeboxPlugin

**Plugins actuellement activés:**
- `mode_switcher.py` - Basculer entre modes curating/jukebox
- `theme_switcher.py` - Basculer entre thèmes dark/light
- `playback_navigation.py` - Navigation avancée dans la lecture
- `loop_player.py` - Lecteur en boucle
- `track_info.py` - Affichage d'infos sur la piste
- `stats_plugin.py` - Statistiques
- `playlists_plugin.py` - Gestion de playlists
- `duplicate_finder.py` - Détection de doublons
- `recommendations.py` - Recommandations
- `file_curator.py` - Curation de fichiers
- `waveform_visualizer.py` - Visualisation de forme d'onde
- `audio_analyzer.py` - Analyse audio
- `metadata_editor.py` - Édition de métadonnées
- `genre_editor.py` - Éditeur de genres
- `file_manager.py` - Gestion de fichiers
- `conf_manager.py` - Gestion de configuration
- `status_bar.py` - Barre de statut

**API de plugin:**
```python
class Plugin:
    name: str
    version: str
    description: str
    
    def initialize(self, context: PluginContext) -> None
    def register_ui(self, ui_builder: UIBuilder) -> None
    def shutdown(self) -> None
```

## tests/ - Suite de tests

**Structure miroir du code source:**
- `tests/core/` - Tests des fonctionnalités core
- `tests/ui/` - Tests des composants UI
- `tests/utils/` - Tests des utilitaires
- `tests/integration/` - Tests d'intégration
- `tests/performance/` - Tests de performance
- `tests/mocks/` - Objets mock pour les tests
- `tests/pytest_vlc_mock.py` - Mock VLC pour tests sans VLC

**Framework:** pytest avec pytest-qt et pytest-cov

## config/ - Configuration

- `config.yaml` - Configuration principale de l'application
  - Settings audio (volume, formats, répertoire)
  - Settings UI (titre, dimensions, thème, mode)
  - Raccourcis clavier
  - Configuration des plugins
  - Niveau de logging

## docs/ - Documentation

Documentation du projet:
- `DEVELOPMENT.md` - Guide de développement
- Autres guides et documentation

## Roadmap/ - Roadmap du projet

Plans de développement:
- `00-OVERVIEW.md` - Vue d'ensemble de la roadmap
- Phases détaillées du projet

## Fichiers de configuration racine

- `pyproject.toml` - Configuration du projet Python (dépendances, outils)
- `Makefile` - Commandes de développement communes
- `.pre-commit-config.yaml` - Configuration des hooks pre-commit
- `.gitignore` - Fichiers exclus de Git
- `README.md` - Documentation principale
- `CLAUDE.md` - Instructions pour Claude Code
- `CONTRIBUTING.md` - Guide de contribution
- `LICENSE` - Licence MIT
- `CHANGELOG.md` - Journal des changements

## Fichiers de données et caches

- `jukebox.db` - Base de données SQLite (dev local)
- `jukebox.log` - Fichier de logs
- `uv.lock` - Lock file des dépendances uv
- `.venv/` - Environnement virtuel Python
- `htmlcov/` - Rapport de couverture HTML
- `.coverage` - Données de couverture
- `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` - Caches d'outils
