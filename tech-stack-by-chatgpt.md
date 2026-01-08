Voici une **proposition de stack technique cohérente, portable et réaliste** pour ton jukebox, avec un accent sur :

* portabilité (macOS, Linux, Raspberry Pi, Windows optionnel)
* extensibilité par **modules internes**
* performance (audio + UI non bloquante)
* maîtrise fine du système (tags, fichiers, sqlite, audio)

Je vais structurer la réponse en **couches** (langage, audio, base de données, UI, modules, threading), puis proposer **une architecture globale**.

---

## 1. Langage principal

### 👉 **Python 3.11+**

C’est le meilleur compromis pour ton projet :

✅ Portable
✅ Excellente intégration SQLite
✅ Écosystème audio solide
✅ Très bon pour un système de plugins / modules
✅ Rapidité de prototypage
✅ Facile à interfacer avec du C/C++ si besoin plus tard

👉 Les parties *CPU-intensives* (waveforms, décodage lourd) pourront être :

* soit déléguées à des libs natives
* soit isolées dans des threads / process

---

## 2. Lecture audio (fichiers + streaming)

### 🎵 Backend audio

**GStreamer**

* Support natif : mp3, flac, aiff, streams (HTTP, Icecast, etc.)
* Très stable
* Déjà utilisé dans des lecteurs pros
* Bien supporté sur Linux, macOS, Windows, Raspberry Pi

➡️ Via bindings Python :

```python
import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst
```

**Pourquoi GStreamer plutôt que VLC ou ffmpeg direct ?**

* Pipeline audio finement contrôlable
* Accès au positionnement (seek)
* Meilleure intégration pour waveforms / analyse
* Streaming facile

---

## 3. Gestion des tags audio (ID3v2, FLAC, AIFF)

### 🏷️ **mutagen**

Lib Python de référence :

* Lecture / écriture ID3v2
* FLAC Vorbis comments
* AIFF
* Très robuste

```python
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
```

👉 Complémentaire à GStreamer (qui lit mais n’écrit pas bien les tags).

---

## 4. Base de données locale

### 🗄️ **SQLite + FTS5**

* SQLite embarqué
* FTS5 pour recherche full-text
* Très performant pour une base locale
* Compatible partout

### ORM recommandé

👉 **SQLAlchemy 2.x**

* Abstraction propre
* Accès direct possible pour FTS5
* Migration possible (Alembic)

Exemple :

```sql
CREATE VIRTUAL TABLE tracks_fts USING fts5(
  title, artist, album, path, tags
);
```

---

## 5. Interface graphique

### 🖥️ **Qt 6 (PySide6)**

C’est le **meilleur choix** pour ce type d’application :

✅ Cross-platform natif
✅ Widgets riches
✅ Très bon support clavier
✅ Threading propre (signals/slots)
✅ Intégration OpenGL / GPU pour waveforms
✅ Interface modulaire

Alternatives (moins adaptées ici) :

* GTK → moins portable sur macOS
* Electron → trop lourd
* TUI (Textual) → pas adapté aux waveforms

---

## 6. Architecture des modules (clé de ton projet)

### 🧩 Concept : **Plugin interne dynamique**

Chaque module est :

* un package Python
* chargé dynamiquement
* avec accès contrôlé au cœur

#### Interface commune des modules

```python
class JukeboxModule:
    name: str

    def on_load(self, context): ...
    def on_unload(self): ...

    def ui_elements(self) -> list[QWidget]: ...
    def key_bindings(self) -> dict: ...
    def on_track_change(self, track): ...
```

### 🔌 Le `context` exposé aux modules

```python
context = {
    "db": sqlite_connection,
    "player": audio_player,
    "track_manager": track_manager,
    "ui": ui_manager,
    "config": config,
}
```

➡️ **Très important** :
les modules **ne manipulent jamais directement le cœur**, uniquement via des interfaces.

---

## 7. Gestion des morceaux

### 🎼 Track Manager

Responsable de :

* scan des répertoires
* extraction des métadonnées
* mise à jour DB
* déplacement de fichiers (mode curating)

```python
Track {
  id
  path
  filename
  duration
  bitrate
  tags
  waveform_id
}
```

---

## 8. Mode "Curating"

### 📂 Mécanique simple et robuste

* Dossier `incoming/`
* Dossier `library/`
* Dossier `trash/`

Actions :

* **Garder** → move vers `library/`
* **Rejeter** → move vers `trash/`

➡️ Le DB garde l’historique même après déplacement.

---

## 9. Waveforms (calcul en arrière-plan)

### 🌊 Traitement audio

**Libs possibles :**

* `librosa` (simple mais lourd)
* `numpy + soundfile`
* ou **GStreamer appsink**

👉 Recommandation :

* Décodage audio → GStreamer
* Calcul → numpy

### 🧵 Exécution

* `QThreadPool + QRunnable`
* ou `concurrent.futures.ProcessPoolExecutor`

Les résultats :

* stockés en SQLite (BLOB ou fichier cache)
* liés au hash du fichier

---

## 10. Recherche Full-text (module dédié)

### 🔍 Module FTS5

Fonctions :

* indexation automatique
* requêtes avancées
* filtres combinés

```sql
SELECT * FROM tracks
JOIN tracks_fts ON tracks.id = tracks_fts.rowid
WHERE tracks_fts MATCH 'jazz AND 1970*';
```

---

## 11. Module "doublons"

### ♻️ Approche hybride

* Hash rapide (taille + durée)
* Hash audio (Chromaprint / AcoustID optionnel)
* Comparaison tags + waveform simplifié

---

## 12. Module "écoute oubliée"

### ⏳ Basé sur l’historique SQLite

```sql
SELECT track_id
FROM listens
GROUP BY track_id
ORDER BY MAX(listened_at) ASC
LIMIT 50;
```

---

## 13. Configuration

### ⚙️ **YAML**

Lib : `ruamel.yaml`

* chemins musique
* DB
* flux streaming
* modules actifs

---

## 14. Packaging & distribution

### 📦

* `poetry` ou `uv`
* `pyinstaller` pour binaire standalone
* flatpak possible sur Linux
* dmg sur macOS

---

## 15. Résumé de la stack

| Couche    | Choix             |
| --------- | ----------------- |
| Langage   | Python 3.11       |
| Audio     | GStreamer         |
| Tags      | mutagen           |
| UI        | Qt 6 (PySide6)    |
| DB        | SQLite + FTS5     |
| ORM       | SQLAlchemy        |
| Waveforms | numpy + GStreamer |
| Modules   | Plugins Python    |
| Config    | YAML              |
| Packaging | PyInstaller       |

---

## Bonus : évolutions possibles

* API interne (RPC) pour pilotage distant
* Interface web (FastAPI) en parallèle
* Synchronisation DB multi-machines
* Machine learning (reco musicale)

---

Si tu veux, je peux ensuite :

* te proposer **un schéma d’architecture détaillé**
* définir **l’API exacte des modules**
* ou te faire **un squelette de projet** prêt à coder 🚀
