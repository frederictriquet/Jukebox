# Recommandation de Stack Technique - Application Jukebox

**Date**: 2026-01-07
**Version**: 2.0 (Révisé après comparaison avec recommandations alternatives)
**Contexte**: Application audio modulaire multiplateforme avec support Raspberry Pi

---

## Changelog v2.0

**Changements principaux suite à comparaison avec recommandations ChatGPT** :

1. ✅ **PySide6 maintenant recommandé en premier** (au lieu de PyQt6)
   - Licence LGPL plus permissive, pas de contraintes GPL
   - Officiellement supporté par Qt Company

2. ✅ **GStreamer ajouté comme alternative sérieuse** à python-vlc
   - Recommandé pour analyse audio avancée et contrôle fin du pipeline
   - Trade-offs clairement expliqués (complexité vs puissance)

3. ✅ **QThreadPool ajouté comme option de threading préférée**
   - Intégration native avec Qt signals/slots
   - Plus cohérent que ThreadPoolExecutor pour architecture Qt

4. ✅ **Nuances sur librosa**
   - Mentionné comme "lourd" (scipy, scikit-learn)
   - Alternative numpy pur + GStreamer appsink proposée

5. ✅ **Deux stacks distinctes proposées**
   - **Stack Simplicité** : python-vlc + librosa (MVP rapide)
   - **Stack Puissance** : GStreamer + numpy pur (contrôle fin)
   - Stratégie de migration claire

**Éléments maintenus de v1.0** :
- Python 3.11+ comme langage
- mutagen pour tags ID3v2
- SQLite + FTS5 direct (pas d'ORM)
- PyYAML + Pydantic pour configuration
- Architecture modulaire avec découverte dynamique

---

## Executive Summary

**Stack recommandée**: **Python 3.11+ avec PySide6, architecture plugin basée sur des hooks**

Cette stack offre le meilleur compromis entre portabilité (Mac, Linux, Raspberry Pi, Windows), écosystème audio mature, facilité de développement d'architecture modulaire, et support natif de l'async pour les traitements en arrière-plan. Python domine l'écosystème audio/multimedia et garantit une compatibilité ARM excellente.

**Deux approches proposées** :
- **Stack "Simplicité"** (MVP rapide) : python-vlc + librosa + threading standard
- **Stack "Puissance"** (analyse audio avancée) : GStreamer + numpy pur + QThreadPool

---

## Stack Technique Recommandée

### 1. Langage Principal: **Python 3.11+**

**Justification**:
- ✅ **Portabilité exceptionnelle**: Support natif Mac, Linux, Windows, ARM (Raspberry Pi)
- ✅ **Écosystème audio/multimedia le plus riche**: mutagen, pydub, librosa, soundfile, pygame
- ✅ **Support SQLite natif**: module `sqlite3` dans la stdlib, support FTS5 garanti
- ✅ **Architecture modulaire naturelle**: imports dynamiques, introspection, duck typing
- ✅ **Async/concurrence mature**: asyncio, threading, multiprocessing intégrés
- ✅ **Prototypage et développement rapide**: moins de boilerplate que Go/Rust
- ✅ **Communauté massive pour audio/DSP**: NumPy, SciPy pour waveforms 3D

**Version minimale**: Python 3.11 (pattern matching, performance améliorée, asyncio mature)

### 2. Interface Graphique: **PySide6** (ou PyQt6 alternative)

**Justification**:
- ✅ **Cross-platform natif**: Mac, Linux, Windows, Raspberry Pi (Qt fonctionne sur ARM)
- ✅ **Performance native**: Bindings C++ vers widgets natifs, pas d'Electron
- ✅ **Architecture signal/slot**: Parfaite pour système de hooks modulaires
- ✅ **Extensibilité**: Widgets personnalisés, layouts dynamiques, injection facile
- ✅ **Mature et stable**: Qt existe depuis 1995
- ✅ **Eco-système riche**: Qt Designer pour prototypage, documentation exhaustive

**Choix PySide6 vs PyQt6**:
- **PySide6** (LGPL) - **RECOMMANDÉ**: Licence plus permissive, officiellement supporté par Qt Company, pas de contraintes GPL
- **PyQt6** (GPL/Commercial): Légèrement plus rapide à jour avec nouvelles versions Qt, mais licence GPL restrictive
- **Recommandation**: Commencer avec PySide6, la migration vers PyQt6 est triviale si besoin (simple renommage imports)

**Alternative rejetée - Tkinter**:
- ❌ Apparence désuète, limitations pour audio/multimedia
- ❌ Extensibilité limitée pour système de plugins complexe

**Alternative rejetée - Electron/Web (Tauri, etc.)**:
- ❌ Overhead mémoire prohibitif sur Raspberry Pi
- ❌ Performance audio sous-optimale (latence, synchronisation)
- ❌ Complexité accrue pour bindings audio natifs

### 3. Bibliothèques Audio

#### A. Lecture Audio: **python-vlc** (Stack Simplicité) ou **GStreamer** (Stack Puissance)

**Option 1: python-vlc** (recommandé pour MVP/simplicité):
```python
# Installation: pip install python-vlc
```
- ✅ Support formats: MP3, FLAC, AIFF, AAC, OGG, WAV, streaming réseau
- ✅ Cross-platform: Utilise libVLC (même moteur que VLC media player)
- ✅ Installation triviale: `pip install python-vlc` + libVLC système
- ✅ API simple et directe
- ✅ Contrôle précis: Position, volume, equalizer, effets
- ✅ Performance: Décodage hardware si disponible
- ✅ Raspberry Pi: Excellent support ARM

**Cons**:
- ❌ Moins de contrôle sur pipeline audio
- ❌ Extraction samples pour waveforms nécessite bibliothèque séparée

**Option 2: GStreamer** (recommandé pour analyse audio avancée):
```python
# Installation: pip install PyGObject
import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst
```
- ✅ Pipeline audio finement contrôlable
- ✅ Extraction directe des samples audio (appsink)
- ✅ Meilleure intégration pour analyse/waveforms
- ✅ Utilisé dans lecteurs professionnels
- ✅ Support streaming, effets temps réel
- ✅ Très stable, bien supporté sur toutes plateformes

**Cons**:
- ❌ Installation plus complexe (GObject, gi bindings)
- ❌ API plus verbeux (construction pipeline)
- ❌ Courbe d'apprentissage plus raide
- ❌ Dépendances système plus lourdes

**Recommandation**:
- **Démarrage**: python-vlc (simplicité, MVP rapide)
- **Si besoin avancé** (analyse audio temps réel, effets DSP): migrer vers GStreamer
- La migration est faisable car l'architecture modulaire isole le player

#### B. Tags ID3v2: **mutagen**

```python
# Installation: pip install mutagen
```
- ✅ Support complet ID3v2.3, ID3v2.4, lecture/écriture
- ✅ Support multi-format: MP3, FLAC, AIFF, OGG, AAC, WAV
- ✅ API pythonique et simple
- ✅ Maintenance active, utilisé par beets, picard, etc.
- ✅ Pure Python (portabilité garantie)

**Alternatives rejetées**:
- `eyed3`: Moins maintenu, API moins intuitive
- `taglib`: Bindings C++, complications build cross-platform

#### C. Waveforms/Analyse Audio: **librosa + soundfile** (Stack Simplicité) ou **numpy + GStreamer** (Stack Puissance)

**Option 1: librosa + soundfile** (recommandé avec python-vlc):
```python
# Installation: pip install librosa soundfile numpy scipy
```

**librosa**: Analyse audio, extraction de features
- ✅ Calcul waveform, spectrogramme, MFCC, tempo, beat tracking
- ✅ Fonctions audio analysis toutes prêtes
- ✅ Documentation excellente
- ✅ Standard de facto pour audio ML/DSP en Python
- ⚠️ **Dépendances lourdes**: scipy, scikit-learn, audioread (100+ MB)

**soundfile**: Lecture/écriture fichiers audio
- ✅ Basé sur libsndfile (C), très performant
- ✅ Support FLAC, AIFF, WAV natif
- ✅ Décoding rapide pour traitement waveform

**Option 2: numpy pur + GStreamer appsink** (recommandé avec GStreamer):
```python
# Installation: pip install numpy
# GStreamer fournit les samples audio directement
```
- ✅ Plus léger (pas de scipy, scikit-learn)
- ✅ Cohérent si GStreamer déjà utilisé pour lecture
- ✅ Extraction samples via GStreamer appsink
- ✅ Traitement waveform avec numpy pur
- ❌ Moins de fonctions audio analysis prêtes à l'emploi

**Pour rendu 3D des waveforms**:
- **PyQtGraph** ou **Vispy** (OpenGL) pour visualisation performante
- Cache des données traitées dans SQLite (BLOB pour arrays NumPy)

**Recommandation**:
- **python-vlc** → librosa + soundfile (plus simple, riche en features)
- **GStreamer** → numpy pur + appsink (plus léger, cohérent)

### 4. Base de Données: **SQLite 3 avec FTS5**

```python
import sqlite3

# Vérification support FTS5
conn = sqlite3.connect(':memory:')
conn.execute('CREATE VIRTUAL TABLE test USING fts5(content)')
```

**Justification**:
- ✅ Intégré dans Python stdlib (pas de dépendance externe)
- ✅ FTS5 disponible depuis SQLite 3.9.0 (2015), garanti dans Python 3.11+
- ✅ Performance excellente pour recherche full-text
- ✅ BLOB support pour cache waveforms (arrays NumPy sérialisés)
- ✅ Sans serveur, parfait pour application locale

**Schema proposé**:
```sql
-- Table principale tracks
CREATE TABLE tracks (
    id INTEGER PRIMARY KEY,
    filepath TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    title TEXT,
    artist TEXT,
    album TEXT,
    duration_seconds REAL,
    bitrate INTEGER,
    sample_rate INTEGER,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified TIMESTAMP
);

-- Index full-text FTS5
CREATE VIRTUAL TABLE tracks_fts USING fts5(
    title, artist, album, filename,
    content=tracks,
    content_rowid=id
);

-- Historique d'écoute
CREATE TABLE play_history (
    id INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    play_duration_seconds REAL,
    completed BOOLEAN,
    FOREIGN KEY (track_id) REFERENCES tracks(id)
);

-- Cache waveforms
CREATE TABLE waveform_cache (
    track_id INTEGER PRIMARY KEY,
    waveform_data BLOB,  -- NumPy array sérialisé
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (track_id) REFERENCES tracks(id)
);

-- Configuration modules
CREATE TABLE module_config (
    module_name TEXT PRIMARY KEY,
    config_json TEXT,
    enabled BOOLEAN DEFAULT 1
);
```

### 5. Architecture Modulaire: **Plugin System avec Hooks**

**Pattern recommandé**: Architecture basée sur découverte dynamique + hooks événementiels

```python
# core/plugin_manager.py
from typing import Protocol, Callable, Any
import importlib
import inspect
from pathlib import Path

class JukeboxModule(Protocol):
    """Interface que tous les modules doivent implémenter"""

    name: str
    version: str

    def initialize(self, context: 'ModuleContext') -> None:
        """Appelé au chargement du module"""
        ...

    def register_ui_elements(self, ui_builder: 'UIBuilder') -> None:
        """Enregistre boutons, widgets, menus"""
        ...

    def register_keyboard_shortcuts(self, kb_manager: 'KeyboardManager') -> None:
        """Enregistre raccourcis clavier"""
        ...

    def shutdown(self) -> None:
        """Appelé à la fermeture"""
        ...

class ModuleContext:
    """Context fourni à chaque module"""

    def __init__(self, db_conn, player, track_list):
        self.db = db_conn  # Connexion SQLite
        self.player = player  # Contrôleur audio
        self.tracks = track_list  # Liste complète des tracks
        self.config = {}  # Config YAML du module

    def emit_event(self, event_name: str, **kwargs):
        """Système d'événements pour communication inter-modules"""
        pass

    def subscribe_event(self, event_name: str, callback: Callable):
        """Abonnement aux événements"""
        pass

class PluginManager:
    def __init__(self, plugins_dir: Path):
        self.plugins_dir = plugins_dir
        self.loaded_modules = {}
        self.event_subscribers = {}

    def discover_modules(self):
        """Charge tous les modules du dossier plugins/"""
        for plugin_file in self.plugins_dir.glob("*.py"):
            if plugin_file.stem.startswith("_"):
                continue

            module_name = f"plugins.{plugin_file.stem}"
            module = importlib.import_module(module_name)

            # Cherche classe implémentant JukeboxModule
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if hasattr(obj, 'initialize') and hasattr(obj, 'name'):
                    self.loaded_modules[obj.name] = obj()

    def initialize_all(self, context: ModuleContext):
        for module in self.loaded_modules.values():
            module.initialize(context)
```

**Exemple de module**:
```python
# plugins/search_module.py
from core.plugin_manager import JukeboxModule, ModuleContext
from PySide6.QtWidgets import QLineEdit, QPushButton

class SearchModule:
    name = "search"
    version = "1.0.0"

    def __init__(self):
        self.context = None
        self.search_input = None

    def initialize(self, context: ModuleContext):
        self.context = context

        # Créer index FTS5 si pas existant
        context.db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS tracks_fts
            USING fts5(title, artist, album, filename)
        """)

    def register_ui_elements(self, ui_builder):
        # Ajoute barre de recherche en haut
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tracks...")
        self.search_input.textChanged.connect(self._on_search)

        ui_builder.add_toolbar_widget(self.search_input)

    def register_keyboard_shortcuts(self, kb_manager):
        kb_manager.register("Ctrl+F", lambda: self.search_input.setFocus())

    def _on_search(self, query: str):
        if len(query) < 2:
            return

        cursor = self.context.db.execute("""
            SELECT t.* FROM tracks t
            JOIN tracks_fts fts ON t.id = fts.rowid
            WHERE tracks_fts MATCH ?
            ORDER BY rank
            LIMIT 100
        """, (query,))

        results = cursor.fetchall()
        self.context.emit_event("search_results", results=results)

    def shutdown(self):
        pass
```

**Avantages de cette architecture**:
- ✅ Découverte automatique des modules (pas de registration manuelle)
- ✅ Interface claire via Protocol (type hints)
- ✅ Communication inter-modules via événements (découplage)
- ✅ Hot-reload possible (reimport dynamique)
- ✅ Accès contrôlé aux ressources via Context

### 6. Gestion Concurrence/Async: **QThreadPool** (recommandé) ou **Threading + asyncio**

**Option 1: QThreadPool + QRunnable** (recommandé pour cohérence Qt):

```python
# core/background_processor.py
from PySide6.QtCore import QThreadPool, QRunnable, QObject, Signal

class WaveformWorkerSignals(QObject):
    """Signaux pour communication thread → UI"""
    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(int)

class WaveformWorker(QRunnable):
    """Worker pour génération waveform en background"""

    def __init__(self, track_id: int, filepath: str):
        super().__init__()
        self.track_id = track_id
        self.filepath = filepath
        self.signals = WaveformWorkerSignals()

    def run(self):
        try:
            import librosa
            import numpy as np

            # Charge audio
            y, sr = librosa.load(self.filepath, sr=22050, mono=True)

            # Calcule waveform
            waveform = librosa.resample(y, orig_sr=sr, target_sr=1000)
            envelope = np.abs(librosa.stft(y))

            result = {
                'track_id': self.track_id,
                'waveform': waveform.tobytes(),
                'envelope': envelope.tobytes(),
            }

            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))

class BackgroundProcessor:
    """Gestionnaire de tâches background intégré Qt"""

    def __init__(self):
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(2)  # Limite pour Raspberry Pi

    def submit_waveform_generation(self, track_id: int, filepath: str, callback):
        """Soumet génération waveform en background"""
        worker = WaveformWorker(track_id, filepath)
        worker.signals.finished.connect(callback)
        self.thread_pool.start(worker)
```

**Avantages QThreadPool**:
- ✅ Intégration native avec Qt signals/slots
- ✅ Pas besoin de concurrent.futures
- ✅ Gestion automatique du cycle de vie des threads
- ✅ Cohérent avec architecture Qt

**Option 2: ThreadPoolExecutor + asyncio** (alternative standard Python):

```python
# core/background_processor.py
import asyncio
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import threading

class BackgroundProcessor:
    """Gestionnaire de tâches background pour waveforms, etc."""

    def __init__(self, max_workers=2):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.task_queue = Queue()
        self.results = {}
        self.loop = asyncio.new_event_loop()

        # Thread dédié pour asyncio loop
        self.async_thread = threading.Thread(
            target=self._run_async_loop,
            daemon=True
        )
        self.async_thread.start()

    def _run_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit_waveform_generation(self, track_id: int, filepath: str, callback):
        """Soumet génération waveform en background"""
        future = self.executor.submit(self._generate_waveform, track_id, filepath)
        future.add_done_callback(lambda f: callback(f.result()))

    def _generate_waveform(self, track_id: int, filepath: str):
        import librosa
        import numpy as np

        # Charge audio
        y, sr = librosa.load(filepath, sr=22050, mono=True)

        # Calcule waveform (downsampled pour visualisation)
        waveform = librosa.resample(y, orig_sr=sr, target_sr=1000)

        # Calcule envelope pour rendu 3D
        envelope = np.abs(librosa.stft(y))

        return {
            'track_id': track_id,
            'waveform': waveform.tobytes(),
            'envelope': envelope.tobytes(),
            'sample_rate': 1000
        }

# Utilisation dans module waveform
class WaveformModule:
    def process_track(self, track_id, filepath):
        def on_complete(result):
            # Store in SQLite cache
            self.context.db.execute("""
                INSERT OR REPLACE INTO waveform_cache
                (track_id, waveform_data)
                VALUES (?, ?)
            """, (result['track_id'], result['waveform']))

            # Emit event pour UI update
            self.context.emit_event('waveform_ready', track_id=track_id)

        self.bg_processor.submit_waveform_generation(
            track_id, filepath, on_complete
        )
```

**Recommandation**: QThreadPool pour cohérence Qt, ThreadPoolExecutor si besoin async/await

**Justification Threading vs Async**:
- **QThreadPool**: Recommandé, intégration Qt native
- **Threading**: Pour I/O bloquant (lecture fichiers, tags ID3)
- **asyncio**: Pour network streaming, événements UI
- **multiprocessing**: Éviter (complexité pickle, overhead sur Pi)
- **GIL Python**: Non-problématique (I/O-bound, pas CPU-bound continu)

### 7. Configuration: **PyYAML + Pydantic**

```python
# pip install pyyaml pydantic
from pydantic import BaseModel, Field
from pathlib import Path
import yaml

class AudioConfig(BaseModel):
    music_directories: list[Path]
    network_shares: list[str] = []
    supported_formats: list[str] = ['mp3', 'flac', 'aiff', 'wav']

class DatabaseConfig(BaseModel):
    db_path: Path = Path.home() / '.jukebox' / 'jukebox.db'
    enable_fts: bool = True

class UIConfig(BaseModel):
    theme: str = 'dark'
    default_mode: str = 'jukebox'  # 'jukebox' ou 'curating'

class JukeboxConfig(BaseModel):
    audio: AudioConfig
    database: DatabaseConfig
    ui: UIConfig
    modules: dict[str, dict] = {}

def load_config(config_path: Path) -> JukeboxConfig:
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return JukeboxConfig(**data)
```

**Exemple config.yaml**:
```yaml
audio:
  music_directories:
    - /home/user/Music
    - /mnt/nas/music
  supported_formats:
    - mp3
    - flac
    - aiff

database:
  db_path: ~/.jukebox/jukebox.db
  enable_fts: true

ui:
  theme: dark
  default_mode: jukebox

modules:
  search:
    fuzzy_matching: true

  waveform:
    quality: medium
    cache_all: false

  recommendations:
    algorithm: collaborative_filtering
    history_lookback_days: 90
```

### 8. Build et Distribution Cross-Platform

#### A. Packaging: **PyInstaller** ou **Briefcase**

**PyInstaller** (recommandé pour démarrage rapide):
```bash
pip install pyinstaller

# Build pour plateforme courante
pyinstaller --name=Jukebox \
            --windowed \
            --add-data="config.yaml:." \
            --hidden-import=PySide6 \
            --icon=icon.ico \
            main.py

# Résultat: dist/Jukebox/ (dossier standalone) ou Jukebox.app sur Mac
```

**Briefcase** (recommandé long terme):
```bash
pip install briefcase

# Projet BeeWare, build natif par plateforme
briefcase create
briefcase build
briefcase package

# Produit: .app (Mac), .AppImage (Linux), .exe (Windows)
```

**Pour Raspberry Pi**:
- Distribution via **pip** + virtual environment (pas de binaire)
- Script d'installation avec dépendances système:

```bash
#!/bin/bash
# install_pi.sh

# Installer dépendances système
sudo apt-get update
sudo apt-get install -y \
    python3.11 \
    python3-pip \
    python3-venv \
    libvlc-dev \
    vlc \
    portaudio19-dev \
    libsndfile1 \
    libatlas-base-dev  # Pour NumPy/SciPy sur ARM

# Créer venv
python3.11 -m venv jukebox_env
source jukebox_env/bin/activate

# Installer dépendances Python
pip install --upgrade pip
pip install -r requirements.txt

# Lancer
python main.py
```

#### B. Gestion Dépendances: **Poetry** (recommandé) ou **pip-tools**

**Poetry**:
```toml
# pyproject.toml
[tool.poetry]
name = "jukebox"
version = "0.1.0"
description = "Modular audio jukebox application"
authors = ["Your Name <you@example.com>"]

[tool.poetry.dependencies]
python = "^3.11"
PySide6 = "^6.6.0"  # Changé: PySide6 au lieu de PyQt6
python-vlc = "^3.0.0"  # Stack Simplicité
# PyGObject = "^3.46.0"  # Stack Puissance (GStreamer)
mutagen = "^1.47.0"
librosa = "^0.10.0"  # Stack Simplicité
soundfile = "^0.12.0"  # Stack Simplicité
numpy = "^1.24.0"
scipy = "^1.10.0"  # Requis par librosa
PyYAML = "^6.0"
pydantic = "^2.5.0"
pyqtgraph = "^0.13.0"  # Pour waveforms

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.0"
black = "^23.0.0"
mypy = "^1.7.0"
ruff = "^0.1.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

```bash
# Installation dev
poetry install

# Lock dependencies pour reproductibilité
poetry lock

# Export requirements.txt pour deployment
poetry export -f requirements.txt --output requirements.txt
```

---

## Alternatives Évaluées et Rejetées

### Alternative 1: **Go + Fyne/Wails**

**Pros**:
- ✅ Binaire statique, déploiement simplifié
- ✅ Performance native, concurrent par défaut (goroutines)
- ✅ Cross-compilation facile

**Cons**:
- ❌ **Écosystème audio immature**: Peu de libs pour ID3, waveforms, DSP
- ❌ **Bibliothèques DSP limitées**: Pas d'équivalent librosa/NumPy
- ❌ **FFI complexe**: Appeler libVLC, libsndfile via CGo (fragile)
- ❌ **Architecture modulaire plus rigide**: Pas de dynamic imports
- ❌ **Courbe d'apprentissage**: Si équipe non familière avec Go

**Verdict**: Rejeté principalement à cause de l'écosystème audio/DSP insuffisant.

### Alternative 2: **Rust + Tauri/egui**

**Pros**:
- ✅ Performance maximale, sécurité mémoire
- ✅ Écosystème audio correct: rodio, symphonia, id3
- ✅ Async mature (tokio)

**Cons**:
- ❌ **Courbe d'apprentissage très raide**: Borrow checker, lifetimes
- ❌ **Développement plus lent**: Compilation longue, boilerplate
- ❌ **DSP limité**: Pas d'équivalent librosa/SciPy
- ❌ **Plugin system complexe**: Dynamic loading en Rust difficile
- ❌ **GUI moins mature**: egui nouveau, Tauri = web (overhead)

**Verdict**: Over-engineering pour ce cas d'usage. Rust excellent pour audio core (ex: DAW), mais Python plus pragmatique ici.

### Alternative 3: **Node.js + Electron**

**Pros**:
- ✅ Écosystème NPM massif
- ✅ UI web moderne (React, Vue)
- ✅ Hot reload, dev rapide

**Cons**:
- ❌ **Overhead mémoire**: Chromium + Node = 200-300MB minimum
- ❌ **Performance audio**: Latence via Web Audio API
- ❌ **Raspberry Pi**: Electron très lourd sur ARM
- ❌ **Bindings natifs fragiles**: node-gyp, dépendances C++ compliquées
- ❌ **Distribution**: Bundle énorme (200+MB)

**Verdict**: Rejeté à cause du overhead sur Raspberry Pi et performance audio.

### Alternative 4: **C++ + Qt**

**Pros**:
- ✅ Performance maximale
- ✅ Qt natif (GUI excellente)
- ✅ Contrôle total sur audio

**Cons**:
- ❌ **Complexité développement**: Gestion mémoire, boilerplate
- ❌ **Développement lent**: Compilation, pas de REPL
- ❌ **Plugin system complexe**: Dynamic loading, ABI stability
- ❌ **Écosystème DSP**: Moins riche que Python
- ❌ **Prototypage difficile**: Itération lente

**Verdict**: Overkill pour ce projet. Utiliser C++ uniquement si performance critique identifiée après profiling.

---

## Comparaison des Options Principales

| Critère | Python + PySide6 | Go + Fyne | Rust + Tauri | C++ + Qt | Node.js + Electron |
|---------|---------------|-----------|--------------|----------|-------------------|
| **Portabilité (Mac/Linux/Pi)** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Écosystème Audio/DSP** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Plugin Architecture** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Performance Runtime** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| **Vitesse Développement** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Overhead Mémoire (Pi)** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ |
| **Distribution Binaire** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Courbe Apprentissage** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| **SQLite FTS5** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **GUI Extensibilité** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **TOTAL** | **45/50** | **37/50** | **35/50** | **40/50** | **35/50** |

**Légende**: ⭐ (1 point) à ⭐⭐⭐⭐⭐ (5 points)

---

## Architecture du Projet Proposée

```
jukebox/
├── main.py                      # Entry point
├── config.yaml                  # Configuration utilisateur
├── pyproject.toml              # Poetry dependencies
├── requirements.txt            # Export pour deployment
│
├── core/
│   ├── __init__.py
│   ├── application.py          # QApplication wrapper
│   ├── plugin_manager.py       # Gestionnaire de modules
│   ├── event_bus.py            # Système événements inter-modules
│   ├── audio_player.py         # Wrapper python-vlc
│   ├── track_manager.py        # Gestion liste tracks + tags
│   ├── database.py             # SQLite + FTS5 wrapper
│   ├── background_processor.py # Threading pour waveforms
│   └── config_manager.py       # Chargement YAML + validation
│
├── ui/
│   ├── __init__.py
│   ├── main_window.py          # Fenêtre principale PySide6
│   ├── ui_builder.py           # API pour modules injecter widgets
│   ├── keyboard_manager.py     # Gestion raccourcis clavier
│   ├── jukebox_mode.py         # Vue mode jukebox
│   ├── curating_mode.py        # Vue mode curating
│   └── components/             # Widgets réutilisables
│       ├── track_list.py
│       ├── player_controls.py
│       └── waveform_view.py
│
├── plugins/                    # Modules utilisateur
│   ├── __init__.py
│   ├── search_module.py        # FTS5 search
│   ├── duplicate_finder.py     # Détection doublons
│   ├── waveform_3d.py          # Génération waveforms
│   ├── recommendations.py      # Recommandations historique
│   └── file_curator.py         # Tri/déplacement fichiers
│
├── utils/
│   ├── __init__.py
│   ├── file_scanner.py         # Scan arborescences
│   ├── audio_metadata.py       # Extraction tags (mutagen)
│   └── network_shares.py       # Montage partages réseau
│
└── tests/
    ├── test_plugin_manager.py
    ├── test_database.py
    └── test_audio_player.py
```

---

## Risques Identifiés et Mitigation

### Risque 1: **Performance sur Raspberry Pi**

**Impact**: Génération waveforms, recherche FTS5 lentes

**Mitigation**:
- Cache agressif des waveforms dans SQLite (BLOB)
- Génération asynchrone en background (ne bloque pas UI)
- Downsampling waveforms (1000Hz vs 44100Hz)
- Index FTS5 avec tokenizer simple (pas de stemming coûteux)
- Profiling early avec `cProfile` et `memory_profiler`

### Risque 2: **Bibliothèque VLC indisponible**

**Impact**: Installation PyQt6 mais pas libVLC sur système

**Mitigation**:
- Fallback vers PyAudio + pydub pour lecture basique
- Instructions install claires par OS:
  - Mac: `brew install vlc`
  - Ubuntu/Debian: `sudo apt-get install vlc libvlc-dev`
  - Raspberry Pi: `sudo apt-get install vlc`
- Check au démarrage + message erreur explicite

### Risque 3: **Hot-reload modules casse état application**

**Impact**: Reload plugin fait perdre état, fuites mémoire

**Mitigation**:
- Implémenter `shutdown()` obligatoire dans modules
- Cleanup événements + timers avant reload
- Reload complet application (pas hot-reload) en phase MVP
- Feature hot-reload = nice-to-have, pas MVP

### Risque 4: **Compatibilité PySide6 vs PyQt6**

**Impact**: Besoin éventuel de migrer vers PyQt6 (plus à jour) ou vice-versa

**Mitigation**:
- Coder contre abstractions Qt (pas specifics PySide6/PyQt6)
- Migration PySide6 ↔ PyQt6 triviale (import renaming)
- Tester sur les deux régulièrement (CI) si besoin
- PySide6 recommandé (licence LGPL sans contraintes)

### Risque 5: **Distribution binaire volumineuse**

**Impact**: PyInstaller bundle = 100-200MB (includes Python + libs)

**Mitigation**:
- Pas de binaire pour Raspberry Pi (pip install via requirements.txt)
- Binaire Mac/Linux optionnel (utilisateurs avancés = pip install)
- Priorité: fonctionnel > binaire optimisé
- Compression UPX pour réduire taille si nécessaire

---

## Plan de Développement par Phases

### Phase 1: Core Foundation (Semaines 1-2)
- [ ] Setup projet Poetry + structure dossiers
- [ ] **Choix Stack**: Simplicité (python-vlc) ou Puissance (GStreamer)
- [ ] Core audio player (wrapper choisi)
- [ ] Track manager + scan directories
- [ ] SQLite database + schema
- [ ] Configuration YAML + validation
- [ ] UI basique PySide6 (fenêtre + liste tracks)

### Phase 2: Plugin System (Semaines 3-4)
- [ ] Plugin manager avec découverte automatique
- [ ] Event bus pour communication inter-modules
- [ ] UIBuilder API pour injection widgets
- [ ] KeyboardManager pour shortcuts
- [ ] Module exemple: search avec FTS5
- [ ] Tests plugin loading/unloading

### Phase 3: Modules MVP (Semaines 5-6)
- [ ] Module search (FTS5 full-text)
- [ ] Module duplicate finder (hash audio + tags)
- [ ] Module file curator (déplacement fichiers)
- [ ] Background processor pour tâches async

### Phase 4: Waveforms & Visualisation (Semaines 7-8)
- [ ] Module waveform 3D (librosa + cache SQLite)
- [ ] PyQtGraph ou Vispy pour rendu performant
- [ ] Génération asynchrone + progress bar
- [ ] Cache invalidation si fichier modifié

### Phase 5: Recommendations & Polish (Semaines 9-10)
- [ ] Module recommendations (historique d'écoute)
- [ ] Mode jukebox vs mode curating (switch UI)
- [ ] Thèmes UI (dark/light)
- [ ] Tests Raspberry Pi + optimisations
- [ ] Documentation utilisateur

### Phase 6: Distribution (Semaines 11-12)
- [ ] PyInstaller builds Mac/Linux
- [ ] Script installation Raspberry Pi
- [ ] CI/CD (GitHub Actions)
- [ ] README + contributing guide
- [ ] Release v1.0

---

## Métriques de Succès

### Performance
- ✅ Démarrage application < 3s (Raspberry Pi)
- ✅ Scan 10,000 tracks < 30s (première fois)
- ✅ Recherche FTS5 < 100ms (10,000 tracks)
- ✅ Génération waveform < 5s/track (background)
- ✅ Utilisation mémoire < 150MB idle (Raspberry Pi)

### Portabilité
- ✅ Fonctionne Mac OS 12+, Ubuntu 22.04+, Raspberry Pi 4
- ✅ Installation une commande (`pip install` ou `poetry install`)
- ✅ Pas de dépendances système exotiques

### Extensibilité
- ✅ Ajout nouveau module < 100 lignes code
- ✅ Module peut ajouter UI sans modifier core
- ✅ Hot-reload modules sans crash (si implémenté)

### Maintenabilité
- ✅ Tests unitaires coverage > 70%
- ✅ Type hints complets (mypy strict)
- ✅ Documentation API pour plugin developers

---

## Ressources et Documentation

### Documentation Officielle
- **Python**: https://docs.python.org/3/
- **PySide6**: https://doc.qt.io/qtforpython-6/
- **PyQt6** (alternative): https://www.riverbankcomputing.com/static/Docs/PyQt6/
- **python-vlc**: https://www.olivieraubert.net/vlc/python-ctypes/
- **GStreamer**: https://gstreamer.freedesktop.org/documentation/
- **mutagen**: https://mutagen.readthedocs.io/
- **librosa**: https://librosa.org/doc/latest/
- **SQLite FTS5**: https://www.sqlite.org/fts5.html
- **Poetry**: https://python-poetry.org/docs/

### Tutoriels et Exemples
- Qt for Python (PySide6): https://doc.qt.io/qtforpython-6/tutorials/index.html
- PyQt6/PySide6 Architecture: https://www.pythonguis.com/
- Plugin Systems in Python: https://realpython.com/python-application-layouts/
- Audio Processing with librosa: https://musicinformationretrieval.com/
- GStreamer Python Tutorial: https://gstreamer.freedesktop.org/documentation/tutorials/

### Communauté
- Qt Forum: https://forum.qt.io/category/15/qt-for-python
- PyQt Forums: https://www.riverbankcomputing.com/mailman/listinfo/pyqt
- r/Python: https://reddit.com/r/Python
- Audio Programming Discord: https://discord.gg/audioprogramming
- GStreamer IRC/Matrix: #gstreamer sur irc.oftc.net

---

## Comparaison des Deux Stacks Proposées

### Stack "Simplicité" (Recommandé pour MVP)

| Composant | Choix | Justification |
|-----------|-------|---------------|
| Langage | Python 3.11+ | Portabilité, écosystème |
| UI | PySide6 | Licence LGPL, officiel Qt Company |
| Audio playback | python-vlc | Installation simple, API directe |
| Tags | mutagen | Standard, pure Python |
| Waveforms | librosa + soundfile | Riche en features, documentation |
| Threading | ThreadPoolExecutor | Standard Python, simple |
| DB | SQLite + FTS5 | Stdlib, pas de dépendances |
| Config | PyYAML + Pydantic | Validation typée forte |

**Avantages**:
- ✅ Installation rapide (`pip install` pour tout)
- ✅ Démarrage MVP en quelques jours
- ✅ Documentation abondante pour chaque composant
- ✅ Courbe d'apprentissage douce

**Inconvénients**:
- ⚠️ Dépendances plus lourdes (~200MB avec librosa)
- ⚠️ Moins de contrôle sur pipeline audio

### Stack "Puissance" (Pour besoins avancés)

| Composant | Choix | Justification |
|-----------|-------|---------------|
| Langage | Python 3.11+ | Portabilité, écosystème |
| UI | PySide6 | Licence LGPL, officiel Qt Company |
| Audio playback | **GStreamer** | Pipeline contrôlable, appsink |
| Tags | mutagen | Standard, pure Python |
| Waveforms | **numpy pur + GStreamer** | Léger, extraction directe samples |
| Threading | **QThreadPool** | Intégration Qt native |
| DB | SQLite + FTS5 | Stdlib, pas de dépendances |
| Config | PyYAML + Pydantic | Validation typée forte |

**Avantages**:
- ✅ Plus léger (pas scipy/scikit-learn)
- ✅ Contrôle fin du pipeline audio
- ✅ Extraction samples directe pour analyse
- ✅ Architecture Qt cohérente (signals/slots)

**Inconvénients**:
- ⚠️ Installation plus complexe (GObject, gi)
- ⚠️ API GStreamer plus verbeux
- ⚠️ Courbe d'apprentissage plus raide

### Stratégie de Migration

```
Phase 1 (MVP):
  Stack Simplicité
    ↓
  Validation concept, tests utilisateurs
    ↓
Phase 2 (Optimisation si nécessaire):
  Profiling (cProfile, memory_profiler)
    ↓
  Si bottleneck audio identifié:
    Migration vers Stack Puissance
    (architecture modulaire facilite migration)
```

**Recommandation finale**: Commencer avec **Stack Simplicité**, migrer vers Stack Puissance uniquement si profiling révèle bottlenecks réels.

---

## Conclusion

La stack **Python 3.11+ avec PySide6** offre le meilleur équilibre entre:
1. **Portabilité native** (Mac, Linux, Raspberry Pi, Windows)
2. **Écosystème audio mature** (mutagen, librosa/GStreamer, python-vlc)
3. **Architecture modulaire naturelle** (imports dynamiques, introspection)
4. **Vitesse de développement** (prototypage rapide, REPL, hot-reload)
5. **Performance acceptable** (I/O-bound, pas CPU-bound critique)

Les alternatives (Go, Rust, C++) apporteraient performance native mais au prix d'une complexité développement significativement accrue, d'un écosystème audio moins riche, et d'une architecture plugin plus rigide.

**Deux stacks proposées** selon vos besoins:
- **Stack Simplicité** (python-vlc + librosa): MVP rapide, riche en features
- **Stack Puissance** (GStreamer + numpy): Contrôle fin, plus léger

**Stratégie recommandée**:
1. Démarrer avec Stack Simplicité pour valider concept rapidement
2. Profiler après MVP pour identifier bottlenecks réels
3. Migrer sélectivement vers Stack Puissance si nécessaire
4. Éviter optimisation prématurée

---

**Prochaines étapes**:
1. Valider cette recommandation avec l'équipe
2. Setup projet Poetry (voir Phase 1)
3. Créer POC minimal (lecture audio + liste tracks + 1 module plugin)
4. Tester sur Raspberry Pi early (valider performance)
5. Itérer rapidement avec feedback utilisateur
