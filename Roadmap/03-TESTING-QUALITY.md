# Phase 3: Testing Infrastructure & Quality Standards

**Durée**: Semaine 2-3 (parallèle à Phase 1-2)
**Objectif**: Framework de tests complet et standards de qualité
**Milestone**: Coverage > 70%, all checks pass

---

## Vue d'Ensemble

Cette phase établit une infrastructure de tests robuste et des standards de qualité stricts. Elle doit être mise en place **en parallèle** avec les phases 1 et 2.

**Philosophie**: "Test first, debug less"

---

## 3.1 Structure de Tests

### 3.1.1 Organisation
```
tests/
├── __init__.py
├── conftest.py              # Fixtures pytest globales
├── core/
│   ├── __init__.py
│   ├── test_audio_player.py
│   ├── test_config.py
│   └── fixtures/
│       └── sample.mp3       # Fichiers de test
├── ui/
│   ├── __init__.py
│   ├── test_main_window.py
│   ├── test_player_controls.py
│   └── test_track_list.py
├── integration/
│   ├── __init__.py
│   └── test_full_playback.py
└── utils/
    ├── __init__.py
    └── test_logger.py
```

### 3.1.2 Fixtures Pytest communes
Créer `tests/conftest.py`:

```python
import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from jukebox.core.config import JukeboxConfig, AudioConfig, UIConfig, LoggingConfig
from jukebox.core.audio_player import AudioPlayer


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.quit()


@pytest.fixture
def test_config():
    """Provide test configuration."""
    return JukeboxConfig(
        audio=AudioConfig(
            default_volume=50,
            supported_formats=["mp3", "flac"],
            music_directory=Path("/tmp/test_music")
        ),
        ui=UIConfig(
            window_title="Test Jukebox",
            window_width=800,
            window_height=600,
            theme="dark"
        ),
        logging=LoggingConfig(
            level="DEBUG",
            file="test.log"
        )
    )


@pytest.fixture
def audio_player(qapp):
    """Provide AudioPlayer instance."""
    return AudioPlayer()


@pytest.fixture
def sample_audio_file(tmp_path):
    """Provide path to sample audio file."""
    # For real tests, copy a small sample audio file
    sample = tmp_path / "sample.mp3"
    # Copy from tests/core/fixtures/sample.mp3
    fixtures_dir = Path(__file__).parent / "core" / "fixtures"
    if (fixtures_dir / "sample.mp3").exists():
        import shutil
        shutil.copy(fixtures_dir / "sample.mp3", sample)
    return sample
```

---

## 3.2 Tests Unitaires

### 3.2.1 Tests Audio Player
Compléter `tests/core/test_audio_player.py`:

```python
import pytest
from pathlib import Path
from jukebox.core.audio_player import AudioPlayer


class TestAudioPlayer:
    """Test suite for AudioPlayer."""

    def test_initialization(self, audio_player):
        """Test player initializes correctly."""
        assert audio_player is not None
        assert audio_player.current_file is None
        assert not audio_player.is_playing()

    def test_volume_control(self, audio_player):
        """Test volume control and clamping."""
        audio_player.set_volume(50)
        assert audio_player.get_volume() == 50

        audio_player.set_volume(150)
        assert audio_player.get_volume() == 100

        audio_player.set_volume(-10)
        assert audio_player.get_volume() == 0

    def test_load_nonexistent_file(self, audio_player):
        """Test loading non-existent file fails gracefully."""
        result = audio_player.load(Path("/nonexistent/file.mp3"))
        assert result is False

    def test_load_valid_file(self, audio_player, sample_audio_file):
        """Test loading valid audio file."""
        if sample_audio_file.exists():
            result = audio_player.load(sample_audio_file)
            assert result is True
            assert audio_player.current_file == sample_audio_file

    def test_signals_emitted(self, audio_player, qtbot):
        """Test that signals are emitted correctly."""
        with qtbot.waitSignal(audio_player.volume_changed, timeout=1000):
            audio_player.set_volume(75)

    @pytest.mark.parametrize("volume", [0, 25, 50, 75, 100])
    def test_volume_range(self, audio_player, volume):
        """Test various volume levels."""
        audio_player.set_volume(volume)
        assert audio_player.get_volume() == volume
```

### 3.2.2 Tests Configuration
```python
# tests/core/test_config.py
import pytest
from pathlib import Path
from jukebox.core.config import (
    AudioConfig, UIConfig, LoggingConfig, JukeboxConfig
)
import yaml


class TestAudioConfig:
    """Test AudioConfig validation."""

    def test_default_values(self):
        """Test default configuration values."""
        config = AudioConfig()
        assert config.default_volume == 70
        assert "mp3" in config.supported_formats

    def test_volume_validation(self):
        """Test volume is clamped to valid range."""
        with pytest.raises(ValueError):
            AudioConfig(default_volume=150)

        with pytest.raises(ValueError):
            AudioConfig(default_volume=-10)


class TestJukeboxConfig:
    """Test full configuration."""

    def test_load_from_yaml(self, tmp_path):
        """Test loading configuration from YAML."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "audio": {
                "default_volume": 60,
                "supported_formats": ["mp3", "flac"],
                "music_directory": str(Path.home() / "Music")
            },
            "ui": {
                "window_title": "Test",
                "window_width": 1024,
                "window_height": 768,
                "theme": "dark"
            },
            "logging": {
                "level": "INFO",
                "file": "test.log"
            }
        }

        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        from jukebox.core.config import load_config
        config = load_config(config_file)

        assert config.audio.default_volume == 60
        assert config.ui.window_title == "Test"
```

### 3.2.3 Tests UI Components
```python
# tests/ui/test_player_controls.py
import pytest
from jukebox.ui.components.player_controls import PlayerControls


class TestPlayerControls:
    """Test PlayerControls widget."""

    def test_initialization(self, qapp):
        """Test controls initialize correctly."""
        controls = PlayerControls()
        assert controls.play_btn is not None
        assert controls.pause_btn is not None
        assert controls.stop_btn is not None

    def test_button_signals(self, qapp, qtbot):
        """Test button signals are emitted."""
        controls = PlayerControls()

        with qtbot.waitSignal(controls.play_clicked, timeout=1000):
            controls.play_btn.click()

        with qtbot.waitSignal(controls.pause_clicked, timeout=1000):
            controls.pause_btn.click()

    def test_volume_slider(self, qapp, qtbot):
        """Test volume slider."""
        controls = PlayerControls()

        with qtbot.waitSignal(controls.volume_changed, timeout=1000):
            controls.volume_slider.setValue(50)

        assert controls.volume_slider.value() == 50
```

---

## 3.3 Tests d'Intégration

### 3.3.1 Test Playback complet
```python
# tests/integration/test_full_playback.py
import pytest
from pathlib import Path
from jukebox.core.audio_player import AudioPlayer
from jukebox.ui.main_window import MainWindow


class TestFullPlayback:
    """Integration tests for full playback flow."""

    def test_load_and_play_track(self, qapp, test_config, sample_audio_file):
        """Test complete load and play workflow."""
        if not sample_audio_file.exists():
            pytest.skip("Sample audio file not available")

        window = MainWindow(test_config)

        # Add track to list
        window.track_list.add_track(sample_audio_file)
        assert window.track_list.count() == 1

        # Simulate track selection
        item = window.track_list.item(0)
        window.track_list.setCurrentItem(item)

        # Load and play
        window._load_and_play(sample_audio_file)

        # Verify player state
        assert window.player.current_file == sample_audio_file

    def test_volume_sync(self, qapp, test_config):
        """Test volume synchronization between player and controls."""
        window = MainWindow(test_config)

        # Set volume via controls
        window.controls.volume_slider.setValue(75)

        # Verify player volume
        assert window.player.get_volume() == 75
```

---

## 3.4 Tests de Performance

### 3.4.1 Benchmarks
Créer `tests/performance/test_benchmarks.py`:

```python
import pytest
import time
from pathlib import Path


@pytest.mark.benchmark
class TestPerformance:
    """Performance benchmarks."""

    def test_player_initialization_time(self, benchmark, qapp):
        """Benchmark player initialization."""
        from jukebox.core.audio_player import AudioPlayer

        def init_player():
            return AudioPlayer()

        result = benchmark(init_player)
        assert result is not None

    def test_config_load_time(self, benchmark, tmp_path):
        """Benchmark configuration loading."""
        from jukebox.core.config import load_config

        # Setup test config file
        config_file = tmp_path / "config.yaml"
        # ... write config

        result = benchmark(load_config, config_file)
        assert result is not None

    def test_ui_startup_time(self, benchmark, qapp, test_config):
        """Benchmark UI initialization."""
        from jukebox.ui.main_window import MainWindow

        def create_window():
            return MainWindow(test_config)

        result = benchmark(create_window)
        assert result is not None
```

---

## 3.5 Mocks et Fixtures

### 3.5.1 Mocking VLC
```python
# tests/mocks/mock_vlc.py
from unittest.mock import Mock


class MockVLCPlayer:
    """Mock VLC player for testing."""

    def __init__(self):
        self._playing = False
        self._volume = 70
        self._position = 0.0

    def play(self):
        self._playing = True

    def pause(self):
        self._playing = False

    def stop(self):
        self._playing = False
        self._position = 0.0

    def is_playing(self):
        return self._playing

    def audio_set_volume(self, volume):
        self._volume = max(0, min(100, volume))

    def audio_get_volume(self):
        return self._volume

    def set_position(self, pos):
        self._position = max(0.0, min(1.0, pos))

    def get_position(self):
        return self._position


@pytest.fixture
def mock_vlc_player(monkeypatch):
    """Provide mocked VLC player."""
    mock = MockVLCPlayer()
    # Patch vlc module
    monkeypatch.setattr("vlc.Instance", lambda: Mock())
    return mock
```

---

## 3.6 Coverage Configuration

### 3.6.1 Exclure du coverage
Ajouter dans `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["jukebox"]
omit = [
    "*/tests/*",
    "*/__init__.py",
    "*/conftest.py",
    "*/mocks/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "def __str__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "if sys.platform",
    "@abstractmethod",
    "@overload",
]
precision = 2
show_missing = true
fail_under = 70

[tool.coverage.html]
directory = "htmlcov"
```

### 3.6.2 Commandes Coverage
```bash
# Run tests with coverage
poetry run pytest --cov=jukebox --cov-report=html --cov-report=term

# View HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

---

## 3.7 Standards de Documentation

### 3.7.1 Docstrings
```python
def example_function(param1: str, param2: int) -> bool:
    """Short description of the function.

    Longer description if needed. Can span multiple lines.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Description of return value

    Raises:
        ValueError: When param2 is negative

    Example:
        >>> example_function("test", 42)
        True
    """
    if param2 < 0:
        raise ValueError("param2 must be positive")
    return True
```

### 3.7.2 Type Hints
```python
from typing import Optional, List, Dict
from pathlib import Path


def process_tracks(
    filepaths: List[Path],
    config: Dict[str, Any],
    volume: Optional[int] = None
) -> List[str]:
    """Process audio tracks with type hints."""
    ...
```

---

## Checklist Phase 3

### Structure Tests (Jour 1)
- [x] Dossiers tests créés (core, ui, utils, integration, performance)
- [x] conftest.py avec fixtures
- [x] Fichiers de test pour chaque module

### Tests Unitaires (Jours 2-3)
- [x] Tests AudioPlayer complets
- [x] Tests Configuration complets
- [x] Tests UI Components (PlayerControls, TrackList, SearchBar)
- [x] Tests Database
- [x] Tests EventBus
- [x] Tests Scanner
- [x] Tests Metadata (basiques)
- [x] Coverage > 70% (74%)

### Tests Intégration (Jour 4)
- [x] Test playback complet
- [x] Test synchronisation composants
- [x] Test workflow utilisateur

### Tests Performance (Jour 5)
- [x] Benchmarks startup
- [x] Benchmarks operations
- [x] Tests performance ajout tracks

### Documentation (Jour 5)
- [x] Docstrings sur fonctions publiques
- [x] Type hints complets
- [ ] Documentation exhaustive (peut être amélioré)

---

## Critères de Succès

1. **Coverage**
   - ✅ Coverage global > 70%
   - ✅ Core modules > 80%
   - ✅ Pas de fichiers < 50%

2. **Quality**
   - ✅ Tous les tests passent
   - ✅ Tests rapides (< 30s total)
   - ✅ Pas de tests flaky

3. **Documentation**
   - ✅ Toutes fonctions documentées
   - ✅ Type hints présents
   - ✅ Exemples dans docstrings

---

## Prochaine Phase

➡️ [Phase 4 - Core Features](04-CORE-FEATURES.md)

---

**Durée estimée**: 5 jours
**Effort**: ~30-35 heures
**Complexité**: Moyenne
