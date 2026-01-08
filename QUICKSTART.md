# Jukebox - Quick Start avec UV

Ce guide vous permettra de démarrer rapidement avec Jukebox en utilisant **uv**, le gestionnaire de paquets Python ultra-rapide.

## 🚀 Installation rapide

### 1. Installer uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Installer VLC

```bash
# macOS
brew install vlc

# Ubuntu/Debian
sudo apt-get install vlc libvlc-dev

# Arch Linux
sudo pacman -S vlc

# Windows
# Télécharger depuis https://www.videolan.org/vlc/
```

### 3. Cloner et installer Jukebox

```bash
# Cloner le projet
git clone https://github.com/yourusername/jukebox.git
cd jukebox

# Installer les dépendances (uv crée automatiquement un venv)
uv sync --all-extras

# C'est tout ! 🎉
```

## 🎵 Utilisation

### Lancer l'application

```bash
# Méthode 1: Via uv run
uv run jukebox

# Méthode 2: Via make
make run

# Méthode 3: Directement
uv run python -m jukebox.main
```

### Utiliser l'application

1. **Ajouter des fichiers** : Cliquez sur "Add Files..."
2. **Jouer une piste** : Double-cliquez sur une piste dans la liste
3. **Contrôler la lecture** : Utilisez les boutons ▶ ⏸ ⏹
4. **Régler le volume** : Ajustez le slider de volume

## 🛠️ Développement

### Commandes utiles

```bash
# Voir toutes les commandes disponibles
make help

# Lancer les tests
make test

# Vérifier la qualité du code
make ci

# Formater le code
make format

# Linting
make lint

# Type checking
make type-check
```

### Ajouter une dépendance

```bash
# Dépendance de production
uv add nom-du-package

# Dépendance de développement
uv add --dev nom-du-package

# Synchroniser après modification manuelle de pyproject.toml
uv sync
```

### Structure du projet

```
jukebox/
├── jukebox/           # Code source
│   ├── core/          # Logique métier
│   ├── ui/            # Interface utilisateur
│   └── utils/         # Utilitaires
├── tests/             # Tests
├── config/            # Configuration
├── Roadmap/           # Roadmap détaillée
└── docs/              # Documentation
```

## 📖 Documentation

- [README.md](README.md) - Documentation générale
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) - Guide de développement détaillé
- [Roadmap/00-OVERVIEW.md](Roadmap/00-OVERVIEW.md) - Vue d'ensemble de la roadmap

## ⚡ Pourquoi uv ?

UV est **10-100x plus rapide** que pip et Poetry :

- ✅ **Installation instantanée** : Résolution des dépendances ultra-rapide
- ✅ **Simplicité** : Pas besoin de gérer manuellement les environnements virtuels
- ✅ **Compatible** : Utilise le format standard `pyproject.toml` (PEP 621)
- ✅ **Moderne** : Développé par Astral (créateurs de Ruff)
- ✅ **Drop-in replacement** : Remplace pip, pip-tools, pipx, poetry, et plus

## 🆘 Problèmes courants

### VLC non trouvé

**Erreur** : `ModuleNotFoundError: No module named 'vlc'`

**Solution** : Installer VLC sur votre système (voir section Installation)

### Qt Platform Plugin

**Erreur** : `qt.qpa.plugin: Could not load the Qt platform plugin`

**Solution** :
```bash
# Réinstaller les dépendances
uv sync --reinstall
```

### Permission denied

**Erreur** : `Permission denied: 'config/config.yaml'`

**Solution** : Vérifier les permissions du fichier ou créer une config utilisateur dans `~/.config/jukebox/`

## 🔄 Migration depuis Poetry

Si vous aviez Poetry installé :

```bash
# Supprimer les fichiers Poetry
rm poetry.lock

# Installer avec uv
uv sync --all-extras

# Tout fonctionne pareil !
```

## 📊 Statut du projet

- **Version actuelle** : v0.1.0-alpha
- **Phase** : MVP Foundation
- **Prochaine étape** : CI/CD Setup

Voir la [Roadmap](Roadmap/00-OVERVIEW.md) pour plus de détails.

---

**Besoin d'aide ?** Consultez la [documentation](README.md) ou ouvrez une issue sur GitHub.
