# Cue Maker Plugin

> Plugin Jukebox pour créer des cue sheets à partir de mixes DJ avec analyse automatique des morceaux

## Vue d'ensemble

Le plugin Cue Maker permet d'analyser un mix DJ (fichier audio continu) et de générer automatiquement une cue sheet (fichier .cue) contenant les timestamps et métadonnées de chaque morceau. Il utilise l'analyse d'empreintes audio (via shazamix) pour identifier les morceaux et leurs positions dans le mix.

## Fonctionnalités

- **Analyse automatique** : Reconnaissance des morceaux dans un mix via fingerprinting audio
- **Édition manuelle** : Correction des métadonnées (artiste, titre, timestamps)
- **Ajout manuel** : Insertion de morceaux non détectés automatiquement
- **Import de bibliothèque** : Récupération des métadonnées depuis la bibliothèque Jukebox
- **Visualisation waveform** : Affichage de la forme d'onde du mix avec marqueurs de cue points
- **Export CUE standard** : Génération de fichiers .cue compatibles avec les standards DJ
- **Cache intelligent** : Mise en cache des fingerprints et waveforms pour performances optimales

## Utilisation

### Activer le mode Cue Maker

1. Lancer Jukebox
2. Menu **Mode** → **Cue Maker Mode**
3. Ou utiliser le raccourci clavier (si configuré)

### Workflow typique

1. **Charger un mix** : Cliquer sur "Load Mix" et sélectionner un fichier audio
2. **Analyser** : Cliquer sur "Analyze" pour détecter automatiquement les morceaux
3. **Valider/Corriger** :
   - Double-clic sur une entrée pour écouter à partir de ce timestamp
   - Éditer les timestamps en cliquant directement dans les cellules
   - Éditer les métadonnées (artiste, titre) dans les cellules correspondantes
   - Ajuster la durée si nécessaire
4. **Ajouter manuellement** :
   - Cliquer sur "+" dans la colonne Actions pour insérer un morceau
   - Cliquer sur "⬇" pour importer les métadonnées depuis la bibliothèque
5. **Exporter** : Cliquer sur "Export" pour générer le fichier .cue

### Actions disponibles

| Bouton | Action |
|--------|--------|
| **🗑️** | Supprimer l'entrée |
| **+** | Insérer une nouvelle entrée après celle-ci |
| **⬇** | Importer les métadonnées du morceau sélectionné dans la bibliothèque |

### Import CUE existant

Le bouton "Import CUE" permet de charger un fichier .cue existant pour le modifier :

1. Cliquer sur "Import CUE"
2. Confirmer l'écrasement des données actuelles
3. Sélectionner le fichier .cue
4. Les entrées sont chargées dans la table pour édition

## Format de fichier CUE

Le plugin génère des fichiers .cue au format standard :

```
FILE "mix.mp3" MP3
  TRACK 01 AUDIO
    PERFORMER "Artist Name"
    TITLE "Track Title"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    PERFORMER "Another Artist"
    TITLE "Another Track"
    INDEX 01 03:45:12
```

**Format des timestamps** : `MM:SS:FF` (minutes:secondes:frames, 75 frames/sec)

## Architecture

### Structure du plugin

```
plugins/cue_maker/
├── __init__.py           # Point d'entrée du plugin
├── plugin.py             # Lifecycle et intégration avec Jukebox
├── constants.py          # Constantes (couleurs, colonnes, icônes)
├── model.py              # Modèle de données (CueEntry, CueSheet, EntryStatus)
├── table_model.py        # Qt model pour la table (QAbstractTableModel)
├── exporter.py           # Export vers format .cue
├── analyzer.py           # Worker thread pour l'analyse shazamix
├── cache.py              # Cache pour fingerprints et waveforms
└── widgets/
    └── cue_maker_widget.py  # Widget principal de l'interface
```

### Composants principaux

#### CueEntry (model.py)

Représente un morceau dans le mix :

```python
@dataclass
class CueEntry:
    start_time_ms: int          # Position de départ (ms)
    artist: str                 # Nom de l'artiste
    title: str                  # Titre du morceau
    confidence: float | str     # Score de confiance (0.0-1.0) ou "manual"
    duration_ms: int            # Durée (ms)
    status: EntryStatus         # PENDING | CONFIRMED | DELETED
    filepath: str               # Chemin vers le fichier audio source
    track_id: int | None        # ID dans la base de données Jukebox
    time_stretch_ratio: float   # Ratio de time-stretch (1.0 = normal)
```

#### CueSheet (model.py)

Contient la liste des morceaux et les métadonnées du mix :

```python
@dataclass
class CueSheet:
    mix_filepath: str           # Chemin du fichier mix
    mix_title: str              # Titre du mix
    mix_performer: str          # DJ / performeur
    entries: list[CueEntry]     # Liste des morceaux
```

#### AnalyzeWorker (analyzer.py)

Thread d'analyse asynchrone qui :
1. Charge le mix audio
2. Extrait les fingerprints audio (ou charge depuis cache)
3. Matche contre la base de données shazamix
4. Émet les résultats via signaux Qt

**Signaux** :
- `progress(current, total, message)` - Progression de l'analyse
- `finished(entries)` - Analyse terminée avec succès
- `error(error_message)` - Erreur durant l'analyse

#### CueExporter (exporter.py)

Génère des fichiers .cue au format standard à partir d'un CueSheet.

**Conversion des timestamps** : Millisecondes → `MM:SS:FF` (75 frames/sec)

### Cache

Le plugin utilise un cache disque (`~/.jukebox/cue_cache/`) pour :

- **Fingerprints** : Évite de réextraire les fingerprints d'un mix déjà analysé
- **Waveforms** : Évite de régénérer la waveform à chaque ouverture
- **Entries** : Sauvegarde les cue entries pour restauration rapide

Le cache est invalidé automatiquement si le fichier mix change (taille ou mtime).

## Configuration

Le plugin est activé dans `config/config.yaml` :

```yaml
plugins:
  enabled:
    - cue_maker
```

Aucune configuration supplémentaire n'est requise. La configuration de la waveform est héritée du plugin `waveform_visualizer`.

## Dépendances

- **shazamix** : Bibliothèque de fingerprinting audio et matching
- **waveform_visualizer** : Plugin pour l'affichage de la waveform
- **PySide6** : Framework Qt pour l'interface utilisateur
- **numpy** : Manipulation des données audio et cache

## Événements émis

Le plugin émet les événements suivants via l'EventBus :

- `CUE_MAKER_ACTIVATED` : Mode Cue Maker activé
- `CUE_MAKER_DEACTIVATED` : Mode Cue Maker désactivé
- `CUE_ANALYSIS_STARTED` : Analyse du mix démarrée
- `CUE_ANALYSIS_COMPLETED` : Analyse terminée avec succès
- `CUE_SHEET_EXPORTED` : Fichier .cue exporté
- `STATUS_MESSAGE` : Messages de statut affichés dans la status bar

## Tests

Les tests du plugin sont situés dans `tests/plugins/` :

```bash
# Exécuter tous les tests du plugin
uv run pytest tests/plugins/test_cue_maker*.py -v

# Tests spécifiques
uv run pytest tests/plugins/test_cue_maker_model.py
uv run pytest tests/plugins/test_cue_maker_widget.py
uv run pytest tests/plugins/test_cue_maker_cache.py
```

**Couverture actuelle** : 127 tests, couverture du module cue_maker > 85%

## Limitations et futures améliorations

### Limitations actuelles

- Pas de détection automatique des transitions/beatmatches
- Pas de support des formats exotiques de cue sheets
- Analyse limitée par la qualité de la base de données shazamix

### Roadmap

- [ ] Détection automatique de BPM et key
- [ ] Support du format .m3u pour playlists
- [ ] Export vers Traktor/Rekordbox
- [ ] Amélioration de la détection de transitions (analyse spectrale)
- [ ] Mode "batch" pour analyser plusieurs mixes

## Contribution

Voir [CONTRIBUTING.md](../../CONTRIBUTING.md) pour les guidelines de contribution au projet Jukebox.

## License

Ce plugin fait partie du projet Jukebox. Voir [LICENSE](../../LICENSE) pour les détails.
