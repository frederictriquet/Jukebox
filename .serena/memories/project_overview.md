# Vue d'ensemble du projet Jukebox

## Objectif
Jukebox est une application audio modulaire pour Mac, Linux et Raspberry Pi. C'est un jukebox permettant de gérer et lire des fichiers audio avec un système de plugins extensible.

## Version actuelle
v0.1.0-alpha - En développement actif (phase alpha)

## Tech Stack

### Langage et version
- Python 3.11+ (requis)

### Frameworks et bibliothèques principales
- **PySide6** (>=6.6.0) - Interface graphique Qt
- **python-vlc** (>=3.0.0) - Backend de lecture audio via VLC
- **mutagen** (>=1.47.0) - Extraction de métadonnées audio
- **PyYAML** (>=6.0) - Configuration YAML
- **Pydantic** (>=2.5.0) - Validation de données
- **librosa** (>=0.10.0) - Analyse audio
- **numpy** (>=1.24.0) - Calculs numériques
- **pyqtgraph** (>=0.13.0) - Visualisation graphique

### Outils de développement
- **uv** - Gestionnaire de paquets Python rapide (https://astral.sh/uv)
- **pytest** - Framework de test avec pytest-qt et pytest-cov
- **black** - Formateur de code
- **ruff** - Linter moderne (remplace flake8, isort, etc.)
- **mypy** - Vérification de types statique
- **pre-commit** - Hooks Git pour la qualité du code

## Dépendances système
- **VLC media player** - Requis pour python-vlc
  - macOS: `brew install vlc`
  - Ubuntu/Debian: `sudo apt-get install vlc libvlc-dev`
  - Arch Linux: `sudo pacman -S vlc`

## Formats audio supportés
- MP3
- FLAC
- AIFF / AIF
- WAV

## Base de données
- SQLite avec support FTS5 (recherche full-text)
- Location: `~/.jukebox/jukebox.db`

## Configuration
- Format YAML avec validation Pydantic
- Fichier: `config/config.yaml`
- Configuration utilisateur: `~/.jukebox/config.yaml` (futur)

## Phases du projet

### Phase actuelle: MVP Foundation (v0.1.0-alpha)
- ✅ Lecture audio basique
- ✅ Interface simple avec liste de pistes
- ✅ Gestion de configuration
- ✅ Logging
- ✅ Système de plugins

### Prochaine phase: CI/CD Setup (v0.2.0-alpha)
- Workflows GitHub Actions
- Tests automatisés
- Vérifications de qualité de code
- Automatisation de build

## Licence
MIT License
