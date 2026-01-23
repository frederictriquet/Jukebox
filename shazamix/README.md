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

Limitations actuelles (prototype)
1. Hash pas assez discriminant - trop de collisions entre morceaux
2. Scoring à améliorer - la confiance devrait être relative au nombre total de fingerprints
3. Pas encore testé avec tempo modifié - le vrai test sera avec un mix


sqlite3 ~/.jukebox/jukebox.db "SELECT filepath FROM tracks WHERE id IN (SELECT track_id FROM fingerprint_status) AND filepath LIKE '%Alan%' LIMIT 1;