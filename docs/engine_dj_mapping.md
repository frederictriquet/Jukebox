# Engine DJ Database Mapping (m.db)

## Source

Fichier : `m.db` — base SQLite exportée depuis Engine DJ (Denon/InMusic).
Schema version 3.0.1, UUID `e1b19e84-cf9e-4f32-a4d6-067a668527be`.

## Statistiques de correspondance

- **Engine DJ** : 6 477 tracks
- **Jukebox** : 6 498 tracks
- **Correspondances exactes** (jointure sur `filename`) : **6 339 tracks**
- Jukebox uniquement : 276 | Engine uniquement : 254
- ~115 filenames non-uniques dans chaque base (même nom dans des dossiers différents)

**Clé de jointure** : `Track.filename` (Engine) = `tracks.filename` (Jukebox).
Couvre 97,5%+ des deux bases. Les différences restantes sont de vraies différences de contenu entre les deux logiciels — on s'intéresse exclusivement aux matchings exacts.

## Structure Engine DJ

### Tables principales

| Table | Rôle |
|---|---|
| `Track` | Métadonnées des morceaux |
| `PerformanceData` | Waveform, beatgrid, cue points, loops (BLOB, 1:1 avec Track) |
| `AlbumArt` | Pochettes en BLOB avec hash |
| `Playlist` | Playlists hiérarchiques (arbre via `parentListId`) |
| `PlaylistEntity` | Association playlist↔track (linked list via `nextEntityId`) |
| `Smartlist` | Playlists intelligentes (règles en texte) |
| `PreparelistEntity` | File de préparation DJ (vide) |
| `Information` | Métadonnées de la base (uuid, version) |
| `Pack` | Gestion export/sync USB |

### Vues

| Vue | Rôle |
|---|---|
| `PlaylistPath` | Chemin complet des playlists (CTE récursif) |
| `PlaylistAllChildren` | Tous les enfants d'une playlist |
| `PlaylistAllParent` | Tous les parents d'une playlist |
| `ChangeLog` | Stub vide |

## Mapping Track (Engine) → tracks (Jukebox)

### Champs avec correspondance directe

| Engine DJ (`Track`) | Jukebox (`tracks`) | Notes |
|---|---|---|
| `filename` | `filename` | **Clé de jointure** |
| `path` | `filepath` | Relatif (`../NORMALIZED/...`) vs absolu |
| `title` | `title` | |
| `artist` | `artist` | |
| `album` | `album` | |
| `genre` | `genre` | |
| `year` | `year` | |
| `length` | `duration_seconds` | Secondes entières vs REAL |
| `bitrate` | `bitrate` | |
| `fileBytes` | `file_size` | |
| `dateAdded` | `date_added` | Epoch vs ISO timestamp |
| `timeLastPlayed` | `last_played` | |
| `isPlayed` / `playedIndicator` | `play_count` | Booléen vs compteur |

### Champs Engine DJ sans équivalent Jukebox (candidats à l'import)

| Champ | Type | Description |
|---|---|---|
| `key` | INTEGER (0-23) | Tonalité musicale (encodage Camelot) |
| `bpmAnalyzed` | REAL | BPM analysé par Engine DJ |
| `rating` | INTEGER (0-100) | Note utilisateur |
| `comment` | TEXT | Commentaire libre |
| `label` | TEXT | Label discographique |
| `composer` | TEXT | Compositeur |
| `remixer` | TEXT | Remixeur |

### Champs Jukebox sans équivalent Engine DJ

| Champ | Notes |
|---|---|
| `album_artist` | |
| `sample_rate` | |
| `track_number` | |
| `mode` | Spécifique Jukebox (curating/jukebox) |

## Mapping PerformanceData → waveform_cache / audio_analysis

| Engine DJ (`PerformanceData`) | Jukebox | Notes |
|---|---|---|
| `overviewWaveFormData` (BLOB) | `waveform_cache.waveform_data` | Formats BLOB incompatibles |
| `beatData` (BLOB) | `audio_analysis.tempo` | Engine : grille complète, Jukebox : valeur scalaire |
| `quickCues` (BLOB) | *(absent)* | Cue points DJ |
| `loops` (BLOB) | *(absent)* | Boucles DJ |
| `trackData` (BLOB) | *(absent)* | Données internes Engine |

## Mapping Playlist → playlists / playlist_tracks

| Engine DJ | Jukebox | Notes |
|---|---|---|
| `Playlist.title` | `playlists.name` | |
| `Playlist.parentListId` | *(absent)* | Jukebox : playlists plates, pas hiérarchiques |
| `PlaylistEntity` (linked list) | `playlist_tracks` (position INTEGER) | Même concept, implémentation différente |
| `Smartlist` | *(absent)* | Pas de playlists intelligentes dans Jukebox |

### Playlists statiques — structure détaillée

Engine DJ utilise des **listes chaînées** à deux niveaux :

**Niveau 1 — Ordre des playlists** (`Playlist`)
- `nextListId` pointe vers la playlist suivante dans l'ordre d'affichage (0 = dernière)
- `parentListId` permet la hiérarchie (sous-dossiers). Actuellement toutes les playlists ont `parentListId = 0` (structure plate)
- Les triggers `trigger_before_insert_List` / `trigger_after_insert_List` maintiennent automatiquement la cohérence de la linked list lors des insertions

**Niveau 2 — Ordre des tracks dans une playlist** (`PlaylistEntity`)
- `nextEntityId` pointe vers le track suivant dans la playlist (0 = dernier)
- `listId` → FK vers `Playlist.id`
- `trackId` → FK vers `Track.id`
- `databaseUuid` identifie la base d'origine (pour les bibliothèques multi-périphériques)
- Contrainte d'unicité sur `(listId, databaseUuid, trackId)` — un track ne peut apparaître qu'une fois par playlist
- Le trigger `trigger_before_delete_PlaylistEntity` recoud la chaîne lors de la suppression d'un élément

**30 playlists statiques** avec répartition :

| Playlist | Tracks | Type |
|---|---|---|
| RECENT | 2 222 | Sélection récente |
| RETRO | 1 791 | Morceaux rétro |
| 2025-07 | 338 | Mensuelle |
| PROCESSED | 295 | Morceaux traités |
| 2024-07 | 280 | Mensuelle |
| 2025-02 | 228 | Mensuelle |
| GILDO | 188 | Thématique |
| ... | ... | ... |
| NO_SHARE | 13 | Exclusions |

Total : 7 206 associations playlist↔track.

**Requête de reconstitution de l'ordre** (linked list → position séquentielle) :

```sql
-- Reconstituer l'ordre des tracks dans une playlist
WITH RECURSIVE ordered AS (
  SELECT pe.id, pe.trackId, pe.nextEntityId, 1 AS pos
  FROM PlaylistEntity pe
  WHERE pe.listId = :playlist_id AND pe.nextEntityId = 0
  UNION ALL
  SELECT pe.id, pe.trackId, pe.nextEntityId, o.pos + 1
  FROM PlaylistEntity pe
  JOIN ordered o ON pe.nextEntityId = o.id
  WHERE pe.listId = :playlist_id
)
SELECT (SELECT MAX(pos) FROM ordered) - pos + 1 AS position,
       t.filename
FROM ordered o
JOIN Track t ON t.id = o.trackId
ORDER BY position;
```

**Conversion vers Jukebox** : la requête ci-dessus produit directement les colonnes `position` et `filename` nécessaires pour alimenter `playlist_tracks` après résolution du `track_id` Jukebox via jointure sur `filename`.

## Encodage des clés musicales (`Track.key`)

Valeurs 0-23 observées. Encodage Camelot probable :

| Valeur | Clé | Valeur | Clé |
|---|---|---|---|
| 0 | (non défini) | 12 | 1A (A♭m) |
| 1 | 1B (B) | 13 | 2A (E♭m) |
| 2 | 2B (F♯) | 14 | 3A (B♭m) |
| 3 | 3B (D♭) | 15 | 4A (Fm) |
| 4 | 4B (A♭) | 16 | 5A (Cm) |
| 5 | 5B (E♭) | 17 | 6A (Gm) |
| 6 | 6B (B♭) | 18 | 7A (Dm) |
| 7 | 7B (F) | 19 | 8A (Am) |
| 8 | 8B (C) | 20 | 9A (Em) |
| 9 | 9B (G) | 21 | 10A (Bm) |
| 10 | 10B (D) | 22 | 11A (F♯m) |
| 11 | 11B (A) | 23 | 12A (C♯m) |
| 12 | 12B (E) | | |

## Export playlist Jukebox → Engine DJ

### Objectif

Exporter une playlist Jukebox (table `playlists` + `playlist_tracks`) vers la base Engine DJ (`m.db`)
en créant une `Playlist` et ses `PlaylistEntity` avec la linked list correcte.

### Pré-requis de sécurité

1. **Ne jamais modifier `m.db` directement** — travailler sur une copie, ou dans une transaction avec ROLLBACK en cas d'erreur
2. **Backup systématique** de `m.db` avant toute écriture
3. **Mode dry-run** : simuler l'export et afficher le rapport avant d'écrire

### Étapes de l'export

#### 1. Validation et détection d'incohérences

Avant toute écriture, vérifier :

**a) Résolution des tracks** — pour chaque track de la playlist Jukebox, chercher le `Track.id` Engine DJ correspondant via `filename` :

```sql
ATTACH 'm.db' AS engine;
SELECT t.filename,
       t.id AS jukebox_id,
       e.id AS engine_id
FROM playlist_tracks pt
JOIN tracks t ON t.id = pt.track_id
LEFT JOIN engine.Track e ON e.filename = t.filename
WHERE pt.playlist_id = :playlist_id
ORDER BY pt.position;
```

**b) Incohérences à détecter et reporter** :

| Cas | Détection | Action |
|---|---|---|
| Track Jukebox absent d'Engine DJ | `engine_id IS NULL` | Warning — track exclu de l'export, reporter au user |
| Filename dupliqué dans Engine DJ (58 cas) | `COUNT(e.id) > 1` pour un même `filename` | Résolution déterministe : voir stratégie ci-dessous |
| Playlist de même nom déjà existante dans Engine DJ | `SELECT id FROM Playlist WHERE title = :name` | Proposer : écraser / renommer / annuler |
| Track déjà présent dans la playlist cible (si écrasement) | Contrainte UNIQUE `(listId, databaseUuid, trackId)` | Supprimer les anciennes PlaylistEntity avant réinsertion |

**Stratégie de résolution des doublons de filename** (58 cas dans Engine DJ) :

Les doublons sont des fichiers identiques importés depuis des dossiers mensuels différents
(ex: `../NORMALIZED/2024-07/` et `../NORMALIZED/2025-03/`). Résolution en 2 passes :

1. **Match par path** : extraire le sous-dossier mensuel du `filepath` Jukebox et le comparer
   au `path` Engine DJ (après normalisation relatif/absolu). Si un seul match → résolu.
2. **Fallback par dateAdded** : si aucun match de path, prendre le track Engine DJ avec le
   `dateAdded` le plus élevé (epoch secondes).

```sql
-- Résolution des doublons : prendre le track avec dateAdded max
SELECT filename, id AS engine_id
FROM Track
WHERE (filename, dateAdded) IN (
    SELECT filename, MAX(dateAdded)
    FROM Track
    GROUP BY filename
)
```

**c) Rapport de pré-export** à afficher :

```
Playlist "House" — 15 tracks
  ✓ 13 tracks résolus dans Engine DJ
  ✗ 2 tracks non trouvés :
    - Unknown Artist - Rare Track.mp3
    - Another Missing.mp3
  ⚠ 1 filename ambigu (doublon Engine DJ) :
    - ANOTR - How You Feel.mp3 → id 19950 (2025-03, le plus récent)
  ⚠ Playlist "House" inexistante dans Engine DJ → sera créée
```

#### 2. Création de la playlist dans Engine DJ

**Insérer en fin de liste chaînée** (position = dernière) :

```sql
-- nextListId = 0 signifie "dernier de la liste"
-- Le trigger trigger_before_insert_List recoud automatiquement la chaîne :
--   il trouve l'ancien dernier (nextListId = 0), le fait pointer vers le nouveau
INSERT INTO Playlist (title, parentListId, isPersisted, nextListId, lastEditTime, isExplicitlyExported)
VALUES (:title, 0, 1, 0, datetime('now'), 1);
```

Le trigger `trigger_before_insert_List` + `trigger_after_insert_List` se charge de :
1. Trouver l'ancienne queue (actuellement `tribal truffles`, id 42, `nextListId = 0`)
2. Mettre à jour son `nextListId` pour pointer vers la nouvelle playlist

Valeurs :
- `parentListId = 0` (racine, pas de sous-dossier)
- `isPersisted = 1` (toutes les playlists existantes ont cette valeur)
- `isExplicitlyExported = 1` (toutes les playlists existantes ont 1 — nécessaire pour la visibilité sur clé USB)
- `lastEditTime` : format **ISO datetime** (`datetime('now')`) — attention, `Playlist.lastEditTime` utilise le format `YYYY-MM-DD HH:MM:SS`, contrairement à `Track.lastEditTime` qui est en epoch secondes (incohérence native d'Engine DJ)
- `databaseUuid` : lire dynamiquement depuis `SELECT uuid FROM Information LIMIT 1`

#### 3. Insertion des tracks (PlaylistEntity) en linked list

Les tracks doivent être insérés **en ordre inverse** (du dernier au premier) car chaque insertion se fait en tête de liste avec `nextEntityId` pointant vers le précédemment inséré :

```python
# Pseudo-code
new_list_id = cursor.lastrowid  # id de la playlist créée
db_uuid = conn.execute("SELECT uuid FROM Information LIMIT 1").fetchone()[0]

prev_entity_id = 0  # le premier inséré sera la queue (nextEntityId = 0)

# Parcourir les tracks en ordre INVERSE (dernier → premier)
for engine_track_id in reversed(resolved_track_ids):
    cursor.execute("""
        INSERT INTO PlaylistEntity (listId, trackId, databaseUuid, nextEntityId, membershipReference)
        VALUES (?, ?, ?, ?, 0)
    """, (new_list_id, engine_track_id, db_uuid, prev_entity_id))
    prev_entity_id = cursor.lastrowid
```

Note : pas de trigger d'insertion sur `PlaylistEntity` qui gère la linked list automatiquement (contrairement à `Playlist`). L'insertion doit donc construire la chaîne manuellement.

#### 4. Cas de mise à jour d'une playlist existante

Si la playlist existe déjà dans Engine DJ :

```sql
-- Supprimer toutes les entrées existantes
-- Le trigger trigger_before_delete_PlaylistEntity recoud la chaîne à chaque suppression
DELETE FROM PlaylistEntity WHERE listId = :existing_list_id;

-- Puis réinsérer les tracks comme en étape 3
```

### Séquence complète avec protection

```python
import shutil
import sqlite3

def export_playlist_to_engine(jukebox_db_path, engine_db_path, playlist_id):
    # 1. Backup
    backup_path = engine_db_path + '.backup'
    shutil.copy2(engine_db_path, backup_path)

    conn = sqlite3.connect(engine_db_path)
    conn.execute("ATTACH ? AS jukebox", (jukebox_db_path,))

    try:
        # 2. Résolution des tracks
        rows = conn.execute("""
            SELECT pt.position, jt.filename, et.id AS engine_id
            FROM jukebox.playlist_tracks pt
            JOIN jukebox.tracks jt ON jt.id = pt.track_id
            LEFT JOIN Track et ON et.filename = jt.filename
            WHERE pt.playlist_id = ?
            ORDER BY pt.position
        """, (playlist_id,)).fetchall()

        # 3. Détection d'incohérences
        missing = [r for r in rows if r[2] is None]
        resolved = [r for r in rows if r[2] is not None]
        # ... vérifier doublons, playlist existante, etc.

        # 4. Afficher rapport, attendre confirmation

        # 5. Écriture dans une transaction
        conn.execute("BEGIN")
        # ... INSERT Playlist + PlaylistEntity
        conn.execute("COMMIT")

    except Exception:
        conn.execute("ROLLBACK")
        # Restaurer le backup si nécessaire
        raise
    finally:
        conn.close()
```

### Contraintes techniques

- **Séquence autoincrement** : `PlaylistEntity` est à seq 17426, `Playlist` à seq 45. Les nouveaux IDs seront > à ces valeurs (le trigger `trigger_after_insert_Track_check_id` sur Track interdit le recyclage d'IDs, mais pas de trigger équivalent sur Playlist/PlaylistEntity)
- **databaseUuid** : lire dynamiquement via `SELECT uuid FROM Information LIMIT 1` (actuellement `e1b19e84-cf9e-4f32-a4d6-067a668527be`)
- **membershipReference** : toujours 0 (7 206/7 206 entrées). Sémantique inconnue, valeur sûre à conserver
- **isExplicitlyExported** : toujours 1 (30/30 playlists). Probablement lié à la visibilité sur clé USB — mettre à 1
- **lastEditTime** : **attention format mixte dans Engine DJ** — `Playlist.lastEditTime` est en ISO datetime (`2025-03-28 18:38:15`), alors que `Track.lastEditTime` est en epoch secondes (`1772559999`). Utiliser `datetime('now')` pour les playlists
- **Pas de trigger automatique** sur `PlaylistEntity` pour la linked list à l'insertion — seul le DELETE est géré par trigger
- **Table Pack** : vide actuellement. Non nécessaire pour l'export de playlists (elle concerne le packaging vers clé USB, un workflow séparé géré par Engine DJ)

### Vérification d'intégrité de la linked list

Avant et après l'export, vérifier que chaque linked list est cohérente :

```sql
-- Vérifier qu'une playlist a exactement un élément terminal (nextEntityId = 0)
SELECT listId, COUNT(*) AS tails
FROM PlaylistEntity
WHERE nextEntityId = 0
GROUP BY listId
HAVING tails != 1;

-- Vérifier qu'aucun nextEntityId ne pointe vers un id inexistant
SELECT pe.id, pe.nextEntityId
FROM PlaylistEntity pe
LEFT JOIN PlaylistEntity pe2 ON pe.nextEntityId = pe2.id
WHERE pe.nextEntityId != 0 AND pe2.id IS NULL;

-- Vérifier la longueur de la chaîne vs le nombre d'entrées
WITH RECURSIVE chain AS (
    SELECT id, nextEntityId, 1 AS len FROM PlaylistEntity
    WHERE listId = :list_id AND nextEntityId = 0
    UNION ALL
    SELECT pe.id, pe.nextEntityId, c.len + 1
    FROM PlaylistEntity pe JOIN chain c ON pe.nextEntityId = c.id
    WHERE pe.listId = :list_id
)
SELECT MAX(len) AS chain_length,
       (SELECT COUNT(*) FROM PlaylistEntity WHERE listId = :list_id) AS total_entries
FROM chain;
-- chain_length DOIT être = total_entries
```

### Scope et hors-scope

- **En scope** : export de playlists statiques Jukebox → Engine DJ
- **Hors scope** : import Engine DJ → Jukebox (playlists et métadonnées key/rating/bpm), smartlists, gestion de la table Pack/USB

## Exemples de requêtes utiles

```sql
-- Jointure entre les deux bases
ATTACH 'm.db' AS engine;

-- Tous les tracks matchés
SELECT t.id AS jukebox_id, e.id AS engine_id, t.filename
FROM tracks t
JOIN engine.Track e ON t.filename = e.filename;

-- Import BPM analysé
UPDATE tracks SET ...
FROM engine.Track e
WHERE tracks.filename = e.filename;

-- Playlists Engine avec leurs tracks
SELECT p.title, e.filename
FROM engine.PlaylistEntity pe
JOIN engine.Playlist p ON p.id = pe.listId
JOIN engine.Track t ON t.id = pe.trackId;
```
