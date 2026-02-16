Commandes disponibles
# Statistiques
uv run shazamix stats
# Indexer tous les morceaux (6000+ tracks → ~2-3h)
uv run shazamix index
# Indexer uniquement le mode jukebox
uv run shazamix index --mode jukebox
# Identifier un fichier audio
uv run shazamix identify /path/to/audio.mp3
# Analyser un mix et générer la cue sheet
uv run shazamix analyze /path/to/mix.mp3 -o cuesheet.txt

## Genre Classifier (ML)

Commandes pour préparer les données et entraîner le classifieur de genres.

### 1. Analyser les tracks (extraction des features ML)

```bash
# Analyser toutes les tracks sans features ML (8 workers)
uv run python -m ml.genre_classifier.cli analyze -w 8

# Mode jukebox uniquement
uv run python -m ml.genre_classifier.cli analyze -w 8 -m jukebox

# Ré-analyser tout (même les tracks déjà analysées)
uv run python -m ml.genre_classifier.cli analyze -w 8 --force

# Limiter à N tracks (pour tester)
uv run python -m ml.genre_classifier.cli analyze -w 8 -l 10 -v
```

### 2. Vérifier les stats

```bash
uv run python -m ml.genre_classifier.cli stats
```

Affiche le nombre de tracks utilisables pour l'entraînement (= ayant un genre ET des features ML).
Si `tracks_with_analysis` > `tracks_with_ml_features`, relancer `analyze`.

### 3. Entraîner le modèle

```bash
# Entraîner avec le modèle par défaut (random_forest)
uv run python -m ml.genre_classifier.cli train

# Comparer tous les modèles disponibles
uv run python -m ml.genre_classifier.cli compare

# Sauvegarder le modèle entraîné
uv run python -m ml.genre_classifier.cli train -o model.pkl
```

### 4. Prédire le genre d'un track

```bash
uv run python -m ml.genre_classifier.cli predict model.pkl <track_id>
uv run python -m ml.genre_classifier.cli predict model.pkl <track_id> --top-n 3
```

---

Limitations actuelles (prototype)
1. Hash pas assez discriminant - trop de collisions entre morceaux
2. Scoring à améliorer - la confiance devrait être relative au nombre total de fingerprints
3. Pas encore testé avec tempo modifié - le vrai test sera avec un mix


sqlite3 ~/.jukebox/jukebox.db "SELECT filepath FROM tracks WHERE id IN (SELECT track_id FROM fingerprint_status) AND filepath LIKE '%Alan%' LIMIT 1;