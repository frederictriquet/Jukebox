# Phase 7: Advanced Features & Polish

**Durée**: Semaines 6-8
**Objectif**: Fonctionnalités avancées et optimisations
**Milestone**: `v0.9.0-rc` - Feature Complete

---

## Vue d'Ensemble

Cette phase ajoute les fonctionnalités avancées et optimise l'application.

---

## 7.1 Modes Jukebox vs Curating (Jours 1-2)

### 7.1.1 Mode System
Créer `jukebox/core/mode_manager.py`:

```python
from enum import Enum
from PySide6.QtCore import QObject, Signal


class AppMode(Enum):
    """Application modes."""
    JUKEBOX = "jukebox"
    CURATING = "curating"


class ModeManager(QObject):
    """Manage application modes."""

    mode_changed = Signal(AppMode)

    def __init__(self):
        super().__init__()
        self._current_mode = AppMode.JUKEBOX

    def set_mode(self, mode: AppMode):
        """Switch application mode."""
        if mode != self._current_mode:
            self._current_mode = mode
            self.mode_changed.emit(mode)

    def get_mode(self) -> AppMode:
        """Get current mode."""
        return self._current_mode

    def is_jukebox_mode(self) -> bool:
        """Check if in jukebox mode."""
        return self._current_mode == AppMode.JUKEBOX

    def is_curating_mode(self) -> bool:
        """Check if in curating mode."""
        return self._current_mode == AppMode.CURATING
```

### 7.1.2 Mode UI Adaptation
```python
# In MainWindow
def _on_mode_changed(self, mode: AppMode):
    """Adapt UI based on mode."""
    if mode == AppMode.JUKEBOX:
        # Hide curating tools
        self.file_curator_action.setVisible(False)
        self.duplicate_finder_action.setVisible(False)
        # Show simplified UI
    else:
        # Show all tools
        self.file_curator_action.setVisible(True)
        self.duplicate_finder_action.setVisible(True)
```

---

## 7.2 Thèmes UI (Jours 2-3)

### 7.2.1 Theme Manager
Créer `jukebox/ui/theme_manager.py`:

```python
from PySide6.QtWidgets import QApplication
from pathlib import Path


class ThemeManager:
    """Manage application themes."""

    THEMES = {
        'dark': """
            QMainWindow {
                background-color: #1e1e1e;
            }
            QWidget {
                background-color: #2d2d2d;
                color: #ffffff;
            }
            QPushButton {
                background-color: #3d3d3d;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
            }
            QLineEdit {
                background-color: #3d3d3d;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 3px;
            }
        """,
        'light': """
            QMainWindow {
                background-color: #ffffff;
            }
            QWidget {
                background-color: #f5f5f5;
                color: #000000;
            }
            QPushButton {
                background-color: #e0e0e0;
                border: 1px solid #cccccc;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                padding: 5px;
                border-radius: 3px;
            }
        """
    }

    @staticmethod
    def apply_theme(theme_name: str):
        """Apply theme to application."""
        if theme_name in ThemeManager.THEMES:
            QApplication.instance().setStyleSheet(
                ThemeManager.THEMES[theme_name]
            )
```

---

## 7.3 Keyboard Shortcuts (Jour 3)

### 7.3.1 Shortcut Manager
Créer `jukebox/core/shortcut_manager.py`:

```python
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import QWidget
from typing import Callable, Dict


class ShortcutManager:
    """Manage keyboard shortcuts."""

    def __init__(self, parent: QWidget):
        self.parent = parent
        self.shortcuts: Dict[str, QShortcut] = {}

    def register(self, key_sequence: str, callback: Callable):
        """Register a keyboard shortcut."""
        shortcut = QShortcut(QKeySequence(key_sequence), self.parent)
        shortcut.activated.connect(callback)
        self.shortcuts[key_sequence] = shortcut

    def unregister(self, key_sequence: str):
        """Unregister a shortcut."""
        if key_sequence in self.shortcuts:
            self.shortcuts[key_sequence].setEnabled(False)
            del self.shortcuts[key_sequence]

    def get_all_shortcuts(self) -> Dict[str, QShortcut]:
        """Get all registered shortcuts."""
        return self.shortcuts.copy()
```

### 7.3.2 Default Shortcuts
```python
# In MainWindow
def _register_shortcuts(self):
    """Register default keyboard shortcuts."""
    self.shortcut_manager = ShortcutManager(self)

    # Playback
    self.shortcut_manager.register("Space", self.player.play)
    self.shortcut_manager.register("Ctrl+P", self.player.pause)
    self.shortcut_manager.register("Ctrl+S", self.player.stop)

    # Volume
    self.shortcut_manager.register(
        "Ctrl+Up",
        lambda: self.player.set_volume(self.player.get_volume() + 10)
    )
    self.shortcut_manager.register(
        "Ctrl+Down",
        lambda: self.player.set_volume(self.player.get_volume() - 10)
    )

    # Navigation
    self.shortcut_manager.register("Ctrl+N", self._next_track)
    self.shortcut_manager.register("Ctrl+B", self._previous_track)

    # Application
    self.shortcut_manager.register("Ctrl+Q", self.close)
    self.shortcut_manager.register("F11", self._toggle_fullscreen)
```

---

## 7.4 Optimisations Raspberry Pi (Jours 4-5)

### 7.4.1 Performance Settings
Ajouter dans config.yaml:

```yaml
performance:
  enable_waveform_cache: true
  max_waveform_threads: 1
  ui_update_interval_ms: 100
  lazy_load_album_art: true
  cache_size_mb: 50
```

### 7.4.2 Optimized Settings
```python
# jukebox/core/performance.py
class PerformanceSettings:
    """Platform-specific performance settings."""

    @staticmethod
    def is_raspberry_pi() -> bool:
        """Detect if running on Raspberry Pi."""
        try:
            with open('/proc/cpuinfo', 'r') as f:
                return 'Raspberry Pi' in f.read()
        except:
            return False

    @staticmethod
    def get_optimal_settings():
        """Get optimal settings for current platform."""
        if PerformanceSettings.is_raspberry_pi():
            return {
                'max_threads': 1,
                'enable_opengl': False,
                'cache_size_mb': 50,
                'ui_update_interval': 200,
            }
        else:
            return {
                'max_threads': 4,
                'enable_opengl': True,
                'cache_size_mb': 200,
                'ui_update_interval': 50,
            }
```

---

## 7.5 Tests Performance (Jour 5-6)

### 7.5.1 Profiling
```python
# tests/performance/test_profiling.py
import cProfile
import pstats
from pathlib import Path


def profile_startup():
    """Profile application startup."""
    profiler = cProfile.Profile()
    profiler.enable()

    from jukebox.main import main
    # ... startup code

    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(20)


def profile_database_operations():
    """Profile database operations."""
    # Test FTS5 search performance
    # Test large dataset operations
    pass
```

---

## 7.6 Documentation Polish (Jour 7)

### 7.6.1 User Guide
Créer `docs/USER_GUIDE.md`:

```markdown
# Jukebox User Guide

## Getting Started

### Installation
[Instructions...]

### First Launch
[Steps...]

## Features

### Playback Controls
[Description...]

### Library Management
[Description...]

### Search
[Description...]

### Playlists
[Description...]

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Space | Play/Pause |
| Ctrl+N | Next Track |
| Ctrl+F | Search |

## Troubleshooting

[Common issues and solutions...]
```

---

## Checklist Phase 7

### Modes (Jours 1-2)
- [x] Mode manager créé (jukebox/core/mode_manager.py)
- [x] Mode switcher plugin with Mode menu
- [x] UI adapts based on mode (hides Tools menu in jukebox mode)
- [x] Runtime mode switching (Ctrl+M toggle)
- [x] Configurable in config.ui.mode
- [x] Tests

### Thèmes (Jours 2-3)
- [x] Theme manager (jukebox/ui/theme_manager.py)
- [x] Dark/Light themes
- [x] Theme switcher plugin with View menu
- [x] Runtime theme switching (no restart needed)
- [x] Toggle shortcut (Ctrl+T)
- [x] Style cohérent (buttons, menus, lists, sliders, toolbars, docks)

### Shortcuts (Jour 3)
- [x] ShortcutManager
- [x] Shortcuts par défaut (Space, Ctrl+P/S, Ctrl+Up/Down, Ctrl+Q/F)
- [x] Plugin API (register_shortcuts method)
- [x] Tests

### Pi Optimization (Jours 4-5)
- [ ] Détection Pi
- [ ] Settings optimisés
- [ ] Tests sur Pi
- [ ] Performance validée

### Performance (Jours 5-6)
- [ ] Profiling
- [ ] Bottlenecks identifiés
- [ ] Optimisations appliquées
- [ ] Benchmarks

### Documentation (Jour 7)
- [ ] User guide
- [ ] Keyboard shortcuts
- [ ] Troubleshooting
- [ ] Screenshots

---

## Prochaine Phase

➡️ [Phase 8 - Distribution & Release](08-DISTRIBUTION-RELEASE.md)

---

**Durée estimée**: 7 jours
**Effort**: ~40-45 heures
**Complexité**: Moyenne-Élevée

**Note**: Waveforms 3D supprimé de cette phase car la visualisation 3-color (Engine DJ style) complétée en Phase 6 couvre déjà les besoins de visualisation avancée.
