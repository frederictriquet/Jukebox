# Phase 6: Essential Modules

**Durée**: Semaines 5-6
**Objectif**: Modules indispensables pour la curation musicale
**Milestone**: `v0.5.0-beta` - MVP Complet

---

## Vue d'Ensemble

Cette phase développe les modules essentiels qui font de Jukebox un véritable outil de curation musicale.

---

## 6.1 Duplicate Finder Module (Jours 1-2)

Créer `plugins/duplicate_finder.py`:

```python
from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QPushButton
from typing import List, Dict
import hashlib


class DuplicateFinderPlugin:
    """Find duplicate tracks based on audio hash and metadata."""

    name = "duplicate_finder"
    version = "1.0.0"
    description = "Find and manage duplicate tracks"

    def initialize(self, context):
        self.context = context

    def register_ui(self, ui_builder):
        menu = ui_builder.add_menu("&Tools")
        ui_builder.add_menu_action(
            menu,
            "Find Duplicates...",
            self._find_duplicates
        )

    def _find_duplicates(self):
        """Find duplicate tracks."""
        # Get all tracks
        tracks = self.context.database.get_all_tracks()

        # Group by potential duplicates
        by_title_artist = {}
        for track in tracks:
            key = (
                (track['title'] or '').lower(),
                (track['artist'] or '').lower()
            )
            if key not in by_title_artist:
                by_title_artist[key] = []
            by_title_artist[key].append(track)

        # Find groups with duplicates
        duplicates = {
            k: v for k, v in by_title_artist.items()
            if len(v) > 1
        }

        # Show dialog
        dialog = DuplicateDialog(duplicates, self.context)
        dialog.exec()

    def register_shortcuts(self, shortcut_manager):
        pass

    def shutdown(self):
        pass


class DuplicateDialog(QDialog):
    """Dialog to show and manage duplicates."""

    def __init__(self, duplicates, context):
        super().__init__()
        self.duplicates = duplicates
        self.context = context
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Duplicate Tracks")
        self.resize(600, 400)

        layout = QVBoxLayout()

        self.list_widget = QListWidget()
        for key, tracks in self.duplicates.items():
            title, artist = key
            item_text = f"{title} - {artist} ({len(tracks)} copies)"
            self.list_widget.addItem(item_text)

        layout.addWidget(self.list_widget)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self.setLayout(layout)
```

---

## 6.2 File Curator Module (Jours 2-3)

Créer `plugins/file_curator.py`:

```python
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QCheckBox
)
from pathlib import Path
import shutil


class FileCuratorPlugin:
    """Organize music files based on metadata."""

    name = "file_curator"
    version = "1.0.0"
    description = "Organize and rename music files"

    def initialize(self, context):
        self.context = context

    def register_ui(self, ui_builder):
        menu = ui_builder.add_menu("&Tools")
        ui_builder.add_menu_action(
            menu,
            "Organize Files...",
            self._show_organizer
        )

    def _show_organizer(self):
        """Show file organizer dialog."""
        dialog = OrganizerDialog(self.context)
        dialog.exec()

    def organize_file(
        self,
        track_id: int,
        dest_root: Path,
        pattern: str = "{artist}/{album}/{track_number:02d} - {title}"
    ) -> Path:
        """Organize a single file based on pattern."""
        track = self.context.database.conn.execute(
            "SELECT * FROM tracks WHERE id = ?",
            (track_id,)
        ).fetchone()

        # Format new path
        new_path = dest_root / pattern.format(
            artist=track['artist'] or 'Unknown',
            album=track['album'] or 'Unknown',
            track_number=track['track_number'] or 0,
            title=track['title'] or track['filename']
        )

        # Add extension
        orig_path = Path(track['filepath'])
        new_path = new_path.with_suffix(orig_path.suffix)

        # Create directories
        new_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy or move file
        shutil.move(str(orig_path), str(new_path))

        # Update database
        self.context.database.conn.execute(
            "UPDATE tracks SET filepath = ?, filename = ? WHERE id = ?",
            (str(new_path), new_path.name, track_id)
        )
        self.context.database.conn.commit()

        return new_path

    def register_shortcuts(self, shortcut_manager):
        pass

    def shutdown(self):
        pass
```

---

## 6.3 Waveform Visualizer Module (Jours 3-5)

Créer `plugins/waveform_visualizer.py`:

```python
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QThread, Signal
import numpy as np
import pyqtgraph as pg


class WaveformVisualizerPlugin:
    """Visualize track waveforms."""

    name = "waveform_visualizer"
    version = "1.0.0"
    description = "Display track waveforms"

    def initialize(self, context):
        self.context = context
        self.waveform_widget = None

        # Subscribe to track loaded event
        from jukebox.core.event_bus import Events
        self.context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)

    def register_ui(self, ui_builder):
        """Add waveform widget."""
        self.waveform_widget = WaveformWidget()
        ui_builder.add_sidebar_widget(self.waveform_widget, "Waveform")

    def _on_track_loaded(self, track_id: int):
        """Generate and show waveform."""
        # Check cache
        cached = self.context.database.conn.execute(
            "SELECT waveform_data FROM waveform_cache WHERE track_id = ?",
            (track_id,)
        ).fetchone()

        if cached:
            # Load from cache
            waveform = np.frombuffer(cached[0], dtype=np.float32)
            self.waveform_widget.display_waveform(waveform)
        else:
            # Generate in background
            track = self.context.database.conn.execute(
                "SELECT filepath FROM tracks WHERE id = ?",
                (track_id,)
            ).fetchone()

            if track:
                self._generate_waveform(track_id, track['filepath'])

    def _generate_waveform(self, track_id: int, filepath: str):
        """Generate waveform in background thread."""
        self.worker = WaveformWorker(track_id, filepath, self.context.database)
        self.worker.finished.connect(
            lambda data: self.waveform_widget.display_waveform(data)
        )
        self.worker.start()

    def register_shortcuts(self, shortcut_manager):
        pass

    def shutdown(self):
        pass


class WaveformWidget(QWidget):
    """Widget to display waveform."""

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        from PySide6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout()

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('k')
        layout.addWidget(self.plot_widget)

        self.setLayout(layout)

    def display_waveform(self, waveform: np.ndarray):
        """Display waveform data."""
        self.plot_widget.clear()
        self.plot_widget.plot(waveform, pen='g')


class WaveformWorker(QThread):
    """Background worker to generate waveform."""

    finished = Signal(np.ndarray)

    def __init__(self, track_id: int, filepath: str, database):
        super().__init__()
        self.track_id = track_id
        self.filepath = filepath
        self.database = database

    def run(self):
        """Generate waveform."""
        try:
            import librosa

            # Load audio
            y, sr = librosa.load(self.filepath, sr=22050, mono=True)

            # Downsample for visualization
            hop_length = 512
            waveform = np.abs(y[::hop_length])

            # Normalize
            waveform = waveform / np.max(waveform) if np.max(waveform) > 0 else waveform

            # Cache in database
            self.database.conn.execute("""
                INSERT OR REPLACE INTO waveform_cache (track_id, waveform_data)
                VALUES (?, ?)
            """, (self.track_id, waveform.astype(np.float32).tobytes()))
            self.database.conn.commit()

            self.finished.emit(waveform)

        except Exception as e:
            import logging
            logging.error(f"Waveform generation failed: {e}")
```

---

## 6.4 Recommendations Module (Jours 5-6)

Créer `plugins/recommendations.py`:

```python
from typing import List
import random


class RecommendationsPlugin:
    """Track recommendations based on listening history."""

    name = "recommendations"
    version = "1.0.0"
    description = "Get track recommendations"

    def initialize(self, context):
        self.context = context

    def register_ui(self, ui_builder):
        menu = ui_builder.add_menu("&Discover")
        ui_builder.add_menu_action(
            menu,
            "Get Recommendations",
            self._show_recommendations
        )

    def _show_recommendations(self):
        """Show recommended tracks."""
        recommendations = self.get_recommendations(limit=20)

        # Emit event with recommendations
        from jukebox.core.event_bus import Events
        self.context.emit(Events.SEARCH_RESULTS, results=recommendations)

    def get_recommendations(self, limit: int = 10) -> List:
        """Get track recommendations based on history."""
        # Get recently played tracks
        recent = self.context.database.conn.execute("""
            SELECT DISTINCT t.artist, t.genre
            FROM tracks t
            JOIN play_history ph ON t.id = ph.track_id
            WHERE ph.completed = 1
            ORDER BY ph.played_at DESC
            LIMIT 20
        """).fetchall()

        if not recent:
            # No history, return random
            return self.context.database.conn.execute(
                f"SELECT * FROM tracks ORDER BY RANDOM() LIMIT {limit}"
            ).fetchall()

        # Get favorite artists and genres
        artists = [r['artist'] for r in recent if r['artist']]
        genres = [r['genre'] for r in recent if r['genre']]

        # Find similar tracks
        recommendations = []

        # Similar artists
        if artists:
            artist_sample = random.sample(artists, min(3, len(artists)))
            for artist in artist_sample:
                tracks = self.context.database.conn.execute("""
                    SELECT * FROM tracks
                    WHERE artist = ?
                    AND id NOT IN (
                        SELECT track_id FROM play_history
                        WHERE played_at > datetime('now', '-7 days')
                    )
                    ORDER BY RANDOM()
                    LIMIT ?
                """, (artist, limit // 3)).fetchall()
                recommendations.extend(tracks)

        # Similar genres
        if genres and len(recommendations) < limit:
            genre_sample = random.sample(genres, min(2, len(genres)))
            for genre in genre_sample:
                tracks = self.context.database.conn.execute("""
                    SELECT * FROM tracks
                    WHERE genre = ?
                    AND id NOT IN (
                        SELECT track_id FROM play_history
                        WHERE played_at > datetime('now', '-7 days')
                    )
                    ORDER BY RANDOM()
                    LIMIT ?
                """, (genre, (limit - len(recommendations)) // 2)).fetchall()
                recommendations.extend(tracks)

        # Shuffle and limit
        random.shuffle(recommendations)
        return recommendations[:limit]

    def register_shortcuts(self, shortcut_manager):
        pass

    def shutdown(self):
        pass
```

---

## Checklist Phase 6

### Duplicate Finder (Jours 1-2)
- [x] Plugin créé
- [x] Détection par métadonnées (title+artist)
- [x] UI dialog
- [x] Menu Tools → Find Duplicates
- [x] **AMÉLIORÉ**: Indicateurs inline (vert/orange/rouge) dans la track list
- [x] **AMÉLIORÉ**: Stratégie trois-pass (exact/filename/fuzzy)
- [x] **AMÉLIORÉ**: Vérification non-bloquante (BackgroundCheckWorker)

### File Curator (Jours 2-3)
- [x] Plugin créé avec organize_file()
- [x] Patterns configurables
- [x] Move files avec update DB
- [x] UI dialog placeholder
- [ ] Tests spécifiques

### Playlists (ajouté)
- [x] Plugin complet (moved from core)
- [x] Create/delete/view/load playlists
- [x] Context menu integration
- [x] UI complète

### Waveform Visualizer (Jours 3-5)
- [x] Génération waveforms
- [x] Cache SQLite (schema existe)
- [x] PyQtGraph integration
- [x] Background processing
- [x] Progressive chunked rendering (10s segments, configurable)
- [x] 3-color frequency separation (bass/mid/treble)
- [x] Engine DJ style stacked visualization
- [x] Interactive seek by clicking waveform

### Recommendations (Jours 5-6)
- [x] Plugin créé
- [x] Algorithme basique (artistes/genres similaires)
- [x] Basé sur historique play_history
- [x] Menu Discover → Get Recommendations
- [ ] Tests spécifiques

---

## Prochaine Phase

➡️ [Phase 7 - Advanced Features](07-ADVANCED-FEATURES.md)

---

**Durée estimée**: 6-7 jours
**Effort**: ~40-45 heures
**Complexité**: Élevée
