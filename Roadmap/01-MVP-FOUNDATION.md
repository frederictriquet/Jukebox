# Phase 1: MVP Foundation

**Durée**: Semaines 1-2
**Objectif**: Application minimale fonctionnelle avec lecture audio
**Milestone**: `v0.1.0-alpha`

---

## Vue d'Ensemble

Cette phase établit les fondations du projet avec une application minimale mais fonctionnelle. À la fin de cette phase, l'application doit pouvoir :
- Lire des fichiers audio (MP3, FLAC)
- Afficher une liste de pistes
- Contrôles de lecture basiques (play, pause, stop, volume)
- Configuration simple via YAML

**Philosophie**: Commencer simple, avoir quelque chose qui fonctionne rapidement.

---

## Tâches Détaillées

### 1.1 Setup Projet (Jour 1)

#### 1.1.1 Initialisation Repository
```bash
# Créer repository
mkdir jukebox
cd jukebox
git init
git branch -M main

# Créer .gitignore
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
venv/
ENV/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Testing
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.ruff_cache/

# Distribution
dist/
build/
*.spec

# Configuration
*.log
.env
config.local.yaml

# Database
*.db
*.sqlite
*.sqlite3

# OS
.DS_Store
Thumbs.db
EOF
```

**Critères d'acceptation**:
- ✅ Repository Git initialisé
- ✅ .gitignore complet
- ✅ Repository poussé sur GitHub

---

#### 1.1.2 Setup Poetry
```bash
# Installer Poetry si nécessaire
curl -sSL https://install.python-poetry.org | python3 -

# Initialiser projet
poetry init --name=jukebox \
            --description="Modular audio jukebox application" \
            --author="Your Name <you@example.com>" \
            --python="^3.11" \
            --no-interaction

# Ajouter dépendances principales
poetry add PySide6
poetry add python-vlc
poetry add mutagen
poetry add PyYAML
poetry add pydantic

# Ajouter dépendances de développement
poetry add --group dev pytest
poetry add --group dev black
poetry add --group dev ruff
poetry add --group dev mypy
poetry add --group dev pre-commit
```

**Fichier pyproject.toml résultant**:
```toml
[tool.poetry]
name = "jukebox"
version = "0.1.0"
description = "Modular audio jukebox application"
authors = ["Your Name <you@example.com>"]
readme = "README.md"
python = "^3.11"

[tool.poetry.dependencies]
python = "^3.11"
PySide6 = "^6.6.0"
python-vlc = "^3.0.0"
mutagen = "^1.47.0"
PyYAML = "^6.0"
pydantic = "^2.5.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.0"
black = "^23.0.0"
ruff = "^0.1.0"
mypy = "^1.7.0"
pre-commit = "^3.5.0"

[tool.poetry.scripts]
jukebox = "jukebox.main:main"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.black]
line-length = 100
target-version = ['py311']

[tool.ruff]
line-length = 100
target-version = "py311"
select = ["E", "F", "I", "N", "W", "B", "SIM"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --cov=jukebox --cov-report=html --cov-report=term"
```

**Critères d'acceptation**:
- ✅ Poetry installé et configuré
- ✅ Dépendances installées
- ✅ pyproject.toml complet avec outils configurés

---

#### 1.1.3 Structure de Dossiers
```bash
# Créer structure
mkdir -p jukebox/core
mkdir -p jukebox/ui
mkdir -p jukebox/ui/components
mkdir -p jukebox/utils
mkdir -p tests
mkdir -p tests/core
mkdir -p tests/ui
mkdir -p config
mkdir -p docs

# Créer __init__.py
touch jukebox/__init__.py
touch jukebox/core/__init__.py
touch jukebox/ui/__init__.py
touch jukebox/ui/components/__init__.py
touch jukebox/utils/__init__.py
touch tests/__init__.py
```

**Structure finale**:
```
jukebox/
├── jukebox/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── core/
│   │   ├── __init__.py
│   │   ├── audio_player.py  # Wrapper python-vlc
│   │   └── config.py        # Configuration YAML
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py   # Fenêtre principale
│   │   └── components/
│   │       ├── __init__.py
│   │       ├── track_list.py    # Liste de pistes
│   │       └── player_controls.py  # Contrôles lecture
│   └── utils/
│       ├── __init__.py
│       └── logger.py        # Logging
├── tests/
│   ├── __init__.py
│   ├── core/
│   │   └── test_audio_player.py
│   └── ui/
│       └── test_main_window.py
├── config/
│   ├── config.yaml          # Config par défaut
│   └── config.example.yaml  # Exemple pour users
├── docs/
│   └── DEVELOPMENT.md
├── pyproject.toml
├── README.md
└── .gitignore
```

**Critères d'acceptation**:
- ✅ Structure de dossiers créée
- ✅ Fichiers __init__.py présents
- ✅ Organisation logique et claire

---

### 1.2 Configuration YAML (Jour 1)

#### 1.2.1 Créer config.yaml
```yaml
# config/config.yaml
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

#### 1.2.2 Implémenter config.py
```python
# jukebox/core/config.py
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field
import yaml


class AudioConfig(BaseModel):
    default_volume: int = Field(ge=0, le=100, default=70)
    supported_formats: List[str] = ["mp3", "flac", "aiff", "wav"]
    music_directory: Path = Field(default_factory=lambda: Path.home() / "Music")


class UIConfig(BaseModel):
    window_title: str = "Jukebox"
    window_width: int = Field(ge=640, default=1024)
    window_height: int = Field(ge=480, default=768)
    theme: str = "dark"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "jukebox.log"


class JukeboxConfig(BaseModel):
    audio: AudioConfig
    ui: UIConfig
    logging: LoggingConfig


def load_config(config_path: Path | None = None) -> JukeboxConfig:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"

    with open(config_path) as f:
        data = yaml.safe_load(f)

    return JukeboxConfig(**data)
```

**Test**:
```python
# tests/core/test_config.py
import pytest
from pathlib import Path
from jukebox.core.config import load_config, JukeboxConfig


def test_load_config():
    """Test loading configuration from YAML."""
    config = load_config()

    assert isinstance(config, JukeboxConfig)
    assert config.audio.default_volume == 70
    assert "mp3" in config.audio.supported_formats
    assert config.ui.window_title == "Jukebox"


def test_config_validation():
    """Test Pydantic validation."""
    with pytest.raises(ValueError):
        AudioConfig(default_volume=150)  # > 100
```

**Critères d'acceptation**:
- ✅ Fichier config.yaml créé
- ✅ Module config.py implémenté avec Pydantic
- ✅ Tests passent
- ✅ Validation des valeurs fonctionne

---

### 1.3 Audio Player (Jours 2-3)

#### 1.3.1 Implémenter audio_player.py
```python
# jukebox/core/audio_player.py
from pathlib import Path
from typing import Optional
import vlc
from PySide6.QtCore import QObject, Signal


class AudioPlayer(QObject):
    """Wrapper around python-vlc for audio playback."""

    # Signals
    state_changed = Signal(str)  # "playing", "paused", "stopped"
    position_changed = Signal(float)  # 0.0 to 1.0
    volume_changed = Signal(int)  # 0 to 100
    track_finished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._instance = vlc.Instance()
        self._player = self._instance.media_player_new()
        self._current_file: Optional[Path] = None

    def load(self, filepath: Path) -> bool:
        """Load an audio file."""
        if not filepath.exists():
            return False

        media = self._instance.media_new(str(filepath))
        self._player.set_media(media)
        self._current_file = filepath
        return True

    def play(self) -> None:
        """Start playback."""
        self._player.play()
        self.state_changed.emit("playing")

    def pause(self) -> None:
        """Pause playback."""
        self._player.pause()
        self.state_changed.emit("paused")

    def stop(self) -> None:
        """Stop playback."""
        self._player.stop()
        self.state_changed.emit("stopped")

    def set_volume(self, volume: int) -> None:
        """Set volume (0-100)."""
        volume = max(0, min(100, volume))
        self._player.audio_set_volume(volume)
        self.volume_changed.emit(volume)

    def get_volume(self) -> int:
        """Get current volume (0-100)."""
        return self._player.audio_get_volume()

    def set_position(self, position: float) -> None:
        """Set playback position (0.0-1.0)."""
        position = max(0.0, min(1.0, position))
        self._player.set_position(position)
        self.position_changed.emit(position)

    def get_position(self) -> float:
        """Get playback position (0.0-1.0)."""
        return self._player.get_position()

    def is_playing(self) -> bool:
        """Check if currently playing."""
        return self._player.is_playing()

    @property
    def current_file(self) -> Optional[Path]:
        """Get currently loaded file."""
        return self._current_file
```

**Test**:
```python
# tests/core/test_audio_player.py
import pytest
from pathlib import Path
from jukebox.core.audio_player import AudioPlayer


@pytest.fixture
def player():
    """Create audio player instance."""
    return AudioPlayer()


def test_player_initialization(player):
    """Test player initializes correctly."""
    assert player is not None
    assert player.current_file is None
    assert not player.is_playing()


def test_volume_control(player):
    """Test volume control."""
    player.set_volume(50)
    assert player.get_volume() == 50

    player.set_volume(150)  # Should clamp to 100
    assert player.get_volume() == 100

    player.set_volume(-10)  # Should clamp to 0
    assert player.get_volume() == 0


# Note: Tests avec fichiers audio réels nécessitent des fixtures
```

**Critères d'acceptation**:
- ✅ AudioPlayer implémenté avec signals Qt
- ✅ Méthodes play, pause, stop fonctionnent
- ✅ Contrôle volume et position
- ✅ Tests unitaires passent

---

### 1.4 Interface Graphique (Jours 4-5)

#### 1.4.1 Player Controls
```python
# jukebox/ui/components/player_controls.py
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QSlider, QLabel
)
from PySide6.QtCore import Signal, Qt


class PlayerControls(QWidget):
    """Playback control widgets."""

    play_clicked = Signal()
    pause_clicked = Signal()
    stop_clicked = Signal()
    volume_changed = Signal(int)
    position_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        """Initialize UI components."""
        layout = QHBoxLayout()

        # Playback buttons
        self.play_btn = QPushButton("▶")
        self.pause_btn = QPushButton("⏸")
        self.stop_btn = QPushButton("⏹")

        self.play_btn.clicked.connect(self.play_clicked.emit)
        self.pause_btn.clicked.connect(self.pause_clicked.emit)
        self.stop_btn.clicked.connect(self.stop_clicked.emit)

        layout.addWidget(self.play_btn)
        layout.addWidget(self.pause_btn)
        layout.addWidget(self.stop_btn)

        # Position slider
        layout.addWidget(QLabel("Position:"))
        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.sliderMoved.connect(
            lambda val: self.position_changed.emit(val / 1000.0)
        )
        layout.addWidget(self.position_slider)

        # Volume slider
        layout.addWidget(QLabel("Volume:"))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.valueChanged.connect(self.volume_changed.emit)
        layout.addWidget(self.volume_slider)

        self.setLayout(layout)

    def set_position(self, position: float):
        """Update position slider (0.0-1.0)."""
        self.position_slider.setValue(int(position * 1000))

    def set_volume(self, volume: int):
        """Update volume slider (0-100)."""
        self.volume_slider.setValue(volume)
```

#### 1.4.2 Track List
```python
# jukebox/ui/components/track_list.py
from PySide6.QtWidgets import QListWidget, QListWidgetItem
from PySide6.QtCore import Signal
from pathlib import Path
from typing import List


class TrackList(QListWidget):
    """Widget for displaying audio tracks."""

    track_selected = Signal(Path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

    def add_track(self, filepath: Path):
        """Add a track to the list."""
        item = QListWidgetItem(filepath.name)
        item.setData(Qt.UserRole, filepath)
        self.addItem(item)

    def add_tracks(self, filepaths: List[Path]):
        """Add multiple tracks."""
        for filepath in filepaths:
            self.add_track(filepath)

    def clear_tracks(self):
        """Clear all tracks."""
        self.clear()

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """Handle track double-click."""
        filepath = item.data(Qt.UserRole)
        self.track_selected.emit(filepath)
```

#### 1.4.3 Main Window
```python
# jukebox/ui/main_window.py
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QPushButton, QFileDialog
)
from pathlib import Path
from jukebox.core.audio_player import AudioPlayer
from jukebox.core.config import JukeboxConfig
from jukebox.ui.components.player_controls import PlayerControls
from jukebox.ui.components.track_list import TrackList


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, config: JukeboxConfig):
        super().__init__()
        self.config = config
        self.player = AudioPlayer()
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        """Initialize UI."""
        self.setWindowTitle(self.config.ui.window_title)
        self.resize(self.config.ui.window_width, self.config.ui.window_height)

        # Central widget
        central = QWidget()
        layout = QVBoxLayout()

        # Add file button
        self.add_files_btn = QPushButton("Add Files...")
        self.add_files_btn.clicked.connect(self._add_files)
        layout.addWidget(self.add_files_btn)

        # Track list
        self.track_list = TrackList()
        layout.addWidget(self.track_list)

        # Player controls
        self.controls = PlayerControls()
        layout.addWidget(self.controls)

        central.setLayout(layout)
        self.setCentralWidget(central)

    def _connect_signals(self):
        """Connect signals between components."""
        # Track selection
        self.track_list.track_selected.connect(self._load_and_play)

        # Player controls
        self.controls.play_clicked.connect(self.player.play)
        self.controls.pause_clicked.connect(self.player.pause)
        self.controls.stop_clicked.connect(self.player.stop)
        self.controls.volume_changed.connect(self.player.set_volume)
        self.controls.position_changed.connect(self.player.set_position)

        # Player feedback
        self.player.volume_changed.connect(self.controls.set_volume)
        self.player.position_changed.connect(self.controls.set_position)

    def _add_files(self):
        """Open file dialog to add audio files."""
        formats = " ".join(f"*.{fmt}" for fmt in self.config.audio.supported_formats)
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Audio Files",
            str(self.config.audio.music_directory),
            f"Audio Files ({formats})"
        )

        if files:
            paths = [Path(f) for f in files]
            self.track_list.add_tracks(paths)

    def _load_and_play(self, filepath: Path):
        """Load and play selected track."""
        if self.player.load(filepath):
            self.player.play()
```

**Critères d'acceptation**:
- ✅ PlayerControls avec boutons et sliders
- ✅ TrackList affiche les pistes
- ✅ MainWindow intègre tous les composants
- ✅ Signals/slots connectés correctement

---

### 1.5 Point d'Entrée (Jour 5)

#### 1.5.1 main.py
```python
# jukebox/main.py
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from jukebox.core.config import load_config
from jukebox.ui.main_window import MainWindow
from jukebox.utils.logger import setup_logging


def main():
    """Application entry point."""
    # Load configuration
    config = load_config()

    # Setup logging
    setup_logging(config.logging)

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName(config.ui.window_title)

    # Create and show main window
    window = MainWindow(config)
    window.show()

    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

#### 1.5.2 Logger utility
```python
# jukebox/utils/logger.py
import logging
from jukebox.core.config import LoggingConfig


def setup_logging(config: LoggingConfig) -> None:
    """Setup application logging."""
    logging.basicConfig(
        level=getattr(logging, config.level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(config.file),
            logging.StreamHandler()
        ]
    )
```

**Test de l'application**:
```bash
# Lancer l'application
poetry run python -m jukebox.main

# Ou avec le script défini
poetry run jukebox
```

**Critères d'acceptation**:
- ✅ Application démarre sans erreur
- ✅ Fenêtre s'affiche correctement
- ✅ Logging configuré
- ✅ Configuration chargée

---

### 1.6 Documentation Initiale (Jour 5)

#### 1.6.1 README.md
```markdown
# Jukebox

A modular audio jukebox application for Mac, Linux, and Raspberry Pi.

## Features (v0.1.0-alpha)

- Audio playback (MP3, FLAC, AIFF, WAV)
- Simple track list
- Playback controls (play, pause, stop)
- Volume control
- Position seeking

## Requirements

- Python 3.11+
- VLC media player (for python-vlc)

## Installation

### Install VLC
```bash
# macOS
brew install vlc

# Ubuntu/Debian
sudo apt-get install vlc libvlc-dev

# Arch Linux
sudo pacman -S vlc
```

### Install Jukebox
```bash
# Clone repository
git clone https://github.com/yourusername/jukebox.git
cd jukebox

# Install with Poetry
poetry install

# Run application
poetry run jukebox
```

## Configuration

Edit `config/config.yaml` to customize settings.

## Development

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for development setup.

## License

TBD

## Roadmap

See [Roadmap/00-OVERVIEW.md](Roadmap/00-OVERVIEW.md) for detailed roadmap.
```

#### 1.6.2 DEVELOPMENT.md
```markdown
# Development Guide

## Setup Development Environment

```bash
# Install dependencies
poetry install

# Install pre-commit hooks (setup in Phase 2)
poetry run pre-commit install
```

## Running Tests

```bash
poetry run pytest
```

## Code Style

- Format: `black`
- Linting: `ruff`
- Type checking: `mypy`

```bash
poetry run black jukebox tests
poetry run ruff jukebox tests
poetry run mypy jukebox
```

## Project Structure

See main README for architecture details.
```

**Critères d'acceptation**:
- ✅ README.md complet
- ✅ DEVELOPMENT.md avec instructions
- ✅ Instructions d'installation claires

---

## Checklist Phase 1

### Setup (Jour 1)
- [x] Repository Git initialisé et poussé sur GitHub
- [x] uv configuré avec toutes les dépendances
- [x] Structure de dossiers créée
- [x] pyproject.toml configuré avec outils de qualité

### Configuration (Jour 1)
- [x] config.yaml créé avec valeurs par défaut
- [x] Module config.py avec Pydantic
- [x] Tests de configuration passent

### Audio Player (Jours 2-3)
- [x] AudioPlayer implémenté avec python-vlc
- [x] Signals Qt pour communication
- [x] Tests unitaires écrits et passent
- [x] Load, play, pause, stop fonctionnent

### Interface (Jours 4-5)
- [x] PlayerControls créé avec boutons et sliders
- [x] TrackList affiche les pistes
- [x] MainWindow intègre tous les composants
- [x] Signals/slots connectés
- [x] Application démarre et fonctionne

### Documentation (Jour 5)
- [x] README.md écrit
- [x] DEVELOPMENT.md créé
- [x] Instructions d'installation testées

### Tests & Validation
- [x] Tests unitaires passent tous
- [x] Application testée manuellement
- [x] Lecture audio fonctionne
- [x] Interface réactive

---

## Livrables Phase 1

### Code
- ✅ Application fonctionnelle v0.1.0-alpha
- ✅ Tests unitaires
- ✅ Configuration avec Pydantic + YAML

### Documentation
- ✅ README.md
- ✅ DEVELOPMENT.md
- ✅ Code documenté (docstrings)

### Infrastructure
- ✅ Repository GitHub
- ✅ Poetry configuré
- ✅ Structure projet claire

---

## Critères de Succès

1. **Fonctionnel**
   - ✅ Application démarre en < 3s
   - ✅ Lit MP3/FLAC sans erreur
   - ✅ Contrôles répondent instantanément

2. **Qualité**
   - ✅ Code formaté (black)
   - ✅ Pas d'erreurs de linting (ruff)
   - ✅ Type hints présents
   - ✅ Tests passent

3. **Documentation**
   - ✅ README complet
   - ✅ Docstrings présents
   - ✅ Instructions claires

---

## Prochaine Phase

Une fois Phase 1 complète et testée, procéder à :
➡️ [Phase 2 - CI/CD Setup](02-CI-CD-SETUP.md)

---

**Durée estimée**: 5-7 jours
**Effort**: ~40 heures
**Complexité**: Faible à Moyenne
