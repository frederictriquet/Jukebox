# Phase 4: Core Features

**Durée**: Semaines 3-4
**Objectif**: Fonctionnalités essentielles pour un jukebox utilisable
**Milestone**: `v0.3.0-beta` - Jukebox fonctionnel

---

## Vue d'Ensemble

Cette phase transforme le prototype en jukebox fonctionnel avec :
- Base de données SQLite avec métadonnées
- Scan automatique de dossiers musicaux
- Recherche full-text avec FTS5
- Extraction automatique des tags ID3
- Playlists basiques
- Historique d'écoute

**Objectif**: Créer un jukebox réellement utilisable au quotidien.

---

## 4.1 Base de Données SQLite (Jours 1-2)

### 4.1.1 Schema Database
Créer `jukebox/core/database.py`:

```python
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime


class Database:
    """SQLite database manager with FTS5 support."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """Connect to database and enable foreign keys."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def initialize_schema(self) -> None:
        """Create database schema."""
        if self.conn is None:
            raise RuntimeError("Database not connected")

        # Tracks table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filepath TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                title TEXT,
                artist TEXT,
                album TEXT,
                album_artist TEXT,
                genre TEXT,
                year INTEGER,
                track_number INTEGER,
                duration_seconds REAL,
                bitrate INTEGER,
                sample_rate INTEGER,
                file_size INTEGER,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_modified TIMESTAMP,
                play_count INTEGER DEFAULT 0,
                last_played TIMESTAMP
            )
        """)

        # FTS5 search index
        self.conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS tracks_fts USING fts5(
                title, artist, album, album_artist, filename, genre,
                content=tracks,
                content_rowid=id
            )
        """)

        # Triggers to keep FTS5 in sync
        self.conn.execute("""
            CREATE TRIGGER IF NOT EXISTS tracks_ai AFTER INSERT ON tracks BEGIN
                INSERT INTO tracks_fts(rowid, title, artist, album, album_artist, filename, genre)
                VALUES (new.id, new.title, new.artist, new.album, new.album_artist, new.filename, new.genre);
            END
        """)

        self.conn.execute("""
            CREATE TRIGGER IF NOT EXISTS tracks_ad AFTER DELETE ON tracks BEGIN
                INSERT INTO tracks_fts(tracks_fts, rowid, title, artist, album, album_artist, filename, genre)
                VALUES('delete', old.id, old.title, old.artist, old.album, old.album_artist, old.filename, old.genre);
            END
        """)

        self.conn.execute("""
            CREATE TRIGGER IF NOT EXISTS tracks_au AFTER UPDATE ON tracks BEGIN
                INSERT INTO tracks_fts(tracks_fts, rowid, title, artist, album, album_artist, filename, genre)
                VALUES('delete', old.id, old.title, old.artist, old.album, old.album_artist, old.filename, old.genre);
                INSERT INTO tracks_fts(rowid, title, artist, album, album_artist, filename, genre)
                VALUES (new.id, new.title, new.artist, new.album, new.album_artist, new.filename, new.genre);
            END
        """)

        # Playlists
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_modified TIMESTAMP
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS playlist_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                track_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE,
                UNIQUE(playlist_id, track_id)
            )
        """)

        # Play history
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS play_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER NOT NULL,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                play_duration_seconds REAL,
                completed BOOLEAN DEFAULT 0,
                FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
            )
        """)

        self.conn.commit()

    def add_track(self, track_data: Dict[str, Any]) -> int:
        """Add a track to the database."""
        cursor = self.conn.execute("""
            INSERT INTO tracks (
                filepath, filename, title, artist, album, album_artist,
                genre, year, track_number, duration_seconds, bitrate,
                sample_rate, file_size, date_modified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            track_data['filepath'],
            track_data['filename'],
            track_data.get('title'),
            track_data.get('artist'),
            track_data.get('album'),
            track_data.get('album_artist'),
            track_data.get('genre'),
            track_data.get('year'),
            track_data.get('track_number'),
            track_data.get('duration_seconds'),
            track_data.get('bitrate'),
            track_data.get('sample_rate'),
            track_data.get('file_size'),
            track_data.get('date_modified')
        ))
        self.conn.commit()
        return cursor.lastrowid

    def search_tracks(self, query: str, limit: int = 100) -> List[sqlite3.Row]:
        """Search tracks using FTS5."""
        cursor = self.conn.execute("""
            SELECT t.*
            FROM tracks t
            JOIN tracks_fts fts ON t.id = fts.rowid
            WHERE tracks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit))
        return cursor.fetchall()

    def get_all_tracks(self, limit: Optional[int] = None) -> List[sqlite3.Row]:
        """Get all tracks."""
        query = "SELECT * FROM tracks ORDER BY date_added DESC"
        if limit:
            query += f" LIMIT {limit}"
        return self.conn.execute(query).fetchall()

    def record_play(self, track_id: int, duration: float, completed: bool) -> None:
        """Record a play in history."""
        self.conn.execute("""
            INSERT INTO play_history (track_id, play_duration_seconds, completed)
            VALUES (?, ?, ?)
        """, (track_id, duration, completed))

        self.conn.execute("""
            UPDATE tracks
            SET play_count = play_count + 1, last_played = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (track_id,))

        self.conn.commit()
```

**Tests**:
```python
# tests/core/test_database.py
def test_database_initialization(tmp_path):
    """Test database schema creation."""
    db = Database(tmp_path / "test.db")
    db.connect()
    db.initialize_schema()

    # Verify tables exist
    cursor = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    tables = [row[0] for row in cursor.fetchall()]

    assert "tracks" in tables
    assert "tracks_fts" in tables
    assert "playlists" in tables
    assert "play_history" in tables
```

---

## 4.2 Extraction Tags ID3 (Jours 2-3)

### 4.2.1 Metadata Extractor
Créer `jukebox/utils/metadata.py`:

```python
from pathlib import Path
from typing import Dict, Any, Optional
import mutagen
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.aiff import AIFF


class MetadataExtractor:
    """Extract metadata from audio files."""

    @staticmethod
    def extract(filepath: Path) -> Dict[str, Any]:
        """Extract metadata from audio file."""
        try:
            audio = mutagen.File(filepath)
            if audio is None:
                return MetadataExtractor._basic_info(filepath)

            metadata = {
                'filepath': str(filepath),
                'filename': filepath.name,
                'file_size': filepath.stat().st_size,
                'date_modified': filepath.stat().st_mtime,
            }

            # Duration
            if hasattr(audio.info, 'length'):
                metadata['duration_seconds'] = audio.info.length

            # Bitrate
            if hasattr(audio.info, 'bitrate'):
                metadata['bitrate'] = audio.info.bitrate

            # Sample rate
            if hasattr(audio.info, 'sample_rate'):
                metadata['sample_rate'] = audio.info.sample_rate

            # Tags
            metadata.update(MetadataExtractor._extract_tags(audio))

            return metadata

        except Exception as e:
            logging.error(f"Error extracting metadata from {filepath}: {e}")
            return MetadataExtractor._basic_info(filepath)

    @staticmethod
    def _extract_tags(audio: mutagen.File) -> Dict[str, Any]:
        """Extract tag information."""
        tags = {}

        # Title
        tags['title'] = MetadataExtractor._get_tag(
            audio, ['TIT2', 'title', '\xa9nam']
        )

        # Artist
        tags['artist'] = MetadataExtractor._get_tag(
            audio, ['TPE1', 'artist', '\xa9ART']
        )

        # Album
        tags['album'] = MetadataExtractor._get_tag(
            audio, ['TALB', 'album', '\xa9alb']
        )

        # Album Artist
        tags['album_artist'] = MetadataExtractor._get_tag(
            audio, ['TPE2', 'albumartist', 'aART']
        )

        # Genre
        tags['genre'] = MetadataExtractor._get_tag(
            audio, ['TCON', 'genre', '\xa9gen']
        )

        # Year
        year_str = MetadataExtractor._get_tag(
            audio, ['TDRC', 'date', '\xa9day']
        )
        if year_str:
            try:
                tags['year'] = int(str(year_str)[:4])
            except (ValueError, TypeError):
                pass

        # Track number
        track_str = MetadataExtractor._get_tag(
            audio, ['TRCK', 'tracknumber', 'trkn']
        )
        if track_str:
            try:
                # Handle "1/12" format
                track_num = str(track_str).split('/')[0]
                tags['track_number'] = int(track_num)
            except (ValueError, TypeError):
                pass

        return tags

    @staticmethod
    def _get_tag(audio: mutagen.File, keys: list) -> Optional[str]:
        """Get tag value from audio file."""
        for key in keys:
            if key in audio:
                value = audio[key]
                if isinstance(value, list) and value:
                    return str(value[0])
                return str(value)
        return None

    @staticmethod
    def _basic_info(filepath: Path) -> Dict[str, Any]:
        """Return basic file info without metadata."""
        return {
            'filepath': str(filepath),
            'filename': filepath.name,
            'file_size': filepath.stat().st_size,
            'date_modified': filepath.stat().st_mtime,
        }
```

---

## 4.3 File Scanner (Jours 3-4)

### 4.3.1 Directory Scanner
Créer `jukebox/utils/scanner.py`:

```python
from pathlib import Path
from typing import List, Callable, Optional
import logging
from jukebox.utils.metadata import MetadataExtractor
from jukebox.core.database import Database


class FileScanner:
    """Scan directories for audio files."""

    def __init__(
        self,
        database: Database,
        supported_formats: List[str],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ):
        self.database = database
        self.supported_formats = [f".{fmt}" for fmt in supported_formats]
        self.progress_callback = progress_callback

    def scan_directory(self, directory: Path, recursive: bool = True) -> int:
        """Scan directory for audio files."""
        if not directory.exists():
            raise ValueError(f"Directory does not exist: {directory}")

        files = self._find_audio_files(directory, recursive)
        total = len(files)
        added = 0

        for idx, filepath in enumerate(files):
            try:
                # Check if file already in database
                existing = self.database.conn.execute(
                    "SELECT id FROM tracks WHERE filepath = ?",
                    (str(filepath),)
                ).fetchone()

                if existing:
                    continue

                # Extract metadata
                metadata = MetadataExtractor.extract(filepath)

                # Add to database
                self.database.add_track(metadata)
                added += 1

                # Progress callback
                if self.progress_callback:
                    self.progress_callback(idx + 1, total)

            except Exception as e:
                logging.error(f"Error processing {filepath}: {e}")

        return added

    def _find_audio_files(
        self, directory: Path, recursive: bool
    ) -> List[Path]:
        """Find all audio files in directory."""
        files = []

        if recursive:
            for ext in self.supported_formats:
                files.extend(directory.rglob(f"*{ext}"))
        else:
            for ext in self.supported_formats:
                files.extend(directory.glob(f"*{ext}"))

        return sorted(files)
```

### 4.3.2 Intégration UI
Ajouter à `MainWindow`:

```python
def _scan_directory(self):
    """Scan music directory for files."""
    directory = QFileDialog.getExistingDirectory(
        self,
        "Select Music Directory",
        str(self.config.audio.music_directory)
    )

    if not directory:
        return

    # Progress dialog
    progress = QProgressDialog(
        "Scanning for audio files...",
        "Cancel",
        0, 100,
        self
    )
    progress.setWindowModality(Qt.WindowModal)

    def update_progress(current: int, total: int):
        progress.setValue(int(current / total * 100))
        QApplication.processEvents()

    # Scan in background thread
    from jukebox.utils.scanner import FileScanner
    scanner = FileScanner(
        self.database,
        self.config.audio.supported_formats,
        update_progress
    )

    added = scanner.scan_directory(Path(directory), recursive=True)

    progress.close()
    QMessageBox.information(
        self,
        "Scan Complete",
        f"Added {added} new tracks to library"
    )

    # Refresh track list
    self._refresh_tracks()
```

---

## 4.4 Recherche FTS5 (Jour 4)

### 4.4.1 Search Widget
Créer `jukebox/ui/components/search_bar.py`:

```python
from PySide6.QtWidgets import QLineEdit
from PySide6.QtCore import Signal, QTimer


class SearchBar(QLineEdit):
    """Search bar with debounced input."""

    search_triggered = Signal(str)

    def __init__(self, parent=None, debounce_ms: int = 300):
        super().__init__(parent)
        self.setPlaceholderText("Search tracks...")

        # Debounce timer
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self._emit_search)

        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text: str):
        """Handle text change with debounce."""
        self.debounce_timer.stop()
        if len(text) >= 2:
            self.debounce_timer.start(300)
        elif len(text) == 0:
            self.search_triggered.emit("")

    def _emit_search(self):
        """Emit search signal."""
        self.search_triggered.emit(self.text())
```

### 4.4.2 Intégration MainWindow
```python
def _init_search(self):
    """Initialize search functionality."""
    self.search_bar = SearchBar()
    self.search_bar.search_triggered.connect(self._perform_search)
    # Add to toolbar or layout

def _perform_search(self, query: str):
    """Perform FTS5 search."""
    if not query:
        # Show all tracks
        tracks = self.database.get_all_tracks()
    else:
        # Search
        tracks = self.database.search_tracks(query)

    # Update track list
    self.track_list.clear_tracks()
    for track in tracks:
        self.track_list.add_track_from_row(track)
```

---

## 4.5 Playlists (Jour 5)

### 4.5.1 Playlist Manager
Créer `jukebox/core/playlist_manager.py`:

```python
from typing import List, Optional
from jukebox.core.database import Database


class PlaylistManager:
    """Manage playlists."""

    def __init__(self, database: Database):
        self.database = database

    def create_playlist(self, name: str, description: str = "") -> int:
        """Create a new playlist."""
        cursor = self.database.conn.execute("""
            INSERT INTO playlists (name, description)
            VALUES (?, ?)
        """, (name, description))
        self.database.conn.commit()
        return cursor.lastrowid

    def add_track_to_playlist(
        self, playlist_id: int, track_id: int
    ) -> None:
        """Add track to playlist."""
        # Get max position
        cursor = self.database.conn.execute("""
            SELECT COALESCE(MAX(position), 0)
            FROM playlist_tracks
            WHERE playlist_id = ?
        """, (playlist_id,))
        max_pos = cursor.fetchone()[0]

        self.database.conn.execute("""
            INSERT INTO playlist_tracks (playlist_id, track_id, position)
            VALUES (?, ?, ?)
        """, (playlist_id, track_id, max_pos + 1))
        self.database.conn.commit()

    def get_playlist_tracks(self, playlist_id: int) -> List:
        """Get all tracks in playlist."""
        return self.database.conn.execute("""
            SELECT t.*
            FROM tracks t
            JOIN playlist_tracks pt ON t.id = pt.track_id
            WHERE pt.playlist_id = ?
            ORDER BY pt.position
        """, (playlist_id,)).fetchall()
```

---

## Checklist Phase 4

### Database (Jours 1-2)
- [ ] Schema SQLite créé
- [ ] FTS5 configuré avec triggers
- [ ] CRUD operations implémentées
- [ ] Tests database passent

### Metadata (Jours 2-3)
- [ ] MetadataExtractor pour MP3/FLAC/AIFF
- [ ] Support tous les tags ID3v2
- [ ] Gestion erreurs robuste
- [ ] Tests extraction passent

### Scanner (Jours 3-4)
- [ ] FileScanner implémenté
- [ ] Scan récursif fonctionne
- [ ] Progress callback
- [ ] Intégration UI

### Search (Jour 4)
- [ ] SearchBar avec debounce
- [ ] FTS5 search fonctionne
- [ ] Résultats instantanés
- [ ] Tests search passent

### Playlists (Jour 5)
- [ ] PlaylistManager créé
- [ ] CRUD playlists
- [ ] Ordre tracks maintenu
- [ ] Tests playlists passent

---

## Livrables Phase 4

- ✅ Database SQLite avec FTS5
- ✅ Extraction métadonnées automatique
- ✅ Scan dossiers musicaux
- ✅ Recherche full-text rapide
- ✅ Système playlists basique

---

## Prochaine Phase

➡️ [Phase 5 - Plugin System](05-PLUGIN-SYSTEM.md)

---

**Durée estimée**: 5-7 jours
**Effort**: ~40 heures
**Complexité**: Moyenne à Élevée
