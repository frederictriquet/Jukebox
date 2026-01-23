# Sans XGBoost
uv sync --extra ml

# Avec XGBoost
uv sync --extra ml-xgboost

Et utiliser le CLI :
# Statistiques des données
uv run genre-classifier stats

# Entraîner (choix: random_forest, xgboost, svm)
uv run genre-classifier train -m random_forest -o models/rf.pkl
uv run genre-classifier train -m xgboost -o models/xgb.pkl
uv run genre-classifier train -m svm -o models/svm.pkl

# Comparer les 3 modèles
uv run genre-classifier compare

# Prédire
uv run genre-classifier predict models/rf.pkl 123 --top-n 3



sqlite3 ~/.jukebox/jukebox.db "SELECT COUNT(*) FROM audio_analysis WHERE rms_mean IS NOT NULL;"

sqlite3 ~/.jukebox/jukebox.db "SELECT COUNT(*) FROM tracks t LEFT JOIN audio_analysis a ON t.id = a.track_id WHERE a.rms_mean IS NULL;"


