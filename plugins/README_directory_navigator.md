# Directory Navigator Plugin

Plugin de navigation par répertoires pour le mode jukebox de Jukebox.

## Vue d'ensemble

Le plugin Directory Navigator ajoute un arbre de répertoires dans la barre latérale gauche permettant de naviguer et filtrer les pistes par dossier. L'arbre affiche la structure hiérarchique de vos répertoires musicaux avec des compteurs de pistes, ainsi que vos playlists.

### Structure de l'arbre

L'arbre affiche trois sections :

- **All Tracks (N)** : Affiche toutes les pistes de la bibliothèque
- **Directories** : Arbre hiérarchique de vos répertoires musicaux avec compteurs
- **Playlists (N)** : Liste de vos playlists avec le nombre de pistes (si des playlists existent)

## Installation

1. Le plugin est déjà présent dans `plugins/directory_navigator.py`
2. Activez-le dans `config/config.yaml` :

```yaml
plugins:
  enabled:
    - directory_navigator
```

3. Redémarrez l'application

## Utilisation

### En mode jukebox

1. Basculez en mode jukebox (le plugin s'active automatiquement)
2. L'arbre de répertoires apparaît dans la barre latérale gauche
3. La section "Directories" est automatiquement dépliée

### Navigation

#### Cliquer sur "All Tracks"
Affiche toutes les pistes de votre bibliothèque dans la liste principale.

#### Cliquer sur un répertoire
Affiche **récursivement** toutes les pistes dans ce répertoire et ses sous-répertoires.

**Exemple** : Si vous cliquez sur `/Music/RECENT`, toutes les pistes dans ce dossier et tous ses sous-dossiers seront affichées.

#### Cliquer sur une playlist
Affiche les pistes de la playlist dans l'ordre défini dans la playlist.

#### Compteurs
Chaque nœud affiche le nombre de pistes :
- Pour un répertoire : nombre total de pistes (direct + sous-répertoires)
- Pour une playlist : nombre de pistes dans la playlist

### Interaction avec d'autres fonctionnalités

Le plugin fonctionne de manière transparente avec les autres filtres :

- **Genre Filter** : Si le genre filter est actif, il s'applique **après** la sélection du répertoire
- **Recherche** : La recherche fonctionne sur les pistes affichées par le directory navigator
- **Navigation** : Les flèches haut/bas fonctionnent normalement sur les pistes filtrées

**Ordre d'application** : Directory Navigator → Genre Filter → Recherche

### Basculement de mode

- L'arbre est **visible uniquement en mode jukebox**
- En mode curating, l'arbre est caché mais reste en mémoire
- Lorsque vous revenez au mode jukebox, l'arbre se reconstruit automatiquement pour refléter les changements effectués en mode curating

### Mise à jour automatique

L'arbre se reconstruit automatiquement dans ces cas :
- **Ajout de pistes** : L'arbre intègre les nouvelles pistes
- **Suppression de pistes** : Les compteurs se mettent à jour
- **Déplacement de fichiers** : L'arbre reflète la nouvelle structure
- **Retour en mode jukebox** : L'arbre se synchronise avec les changements du mode curating

## Architecture technique

### Composants

#### DirectoryTreeWidget
Widget Qt (`QWidget`) contenant un `QTreeView` avec un `QStandardItemModel`. Responsable de :
- Construction de l'arbre à partir des filepaths de la base de données
- Calcul du préfixe commun pour une vue optimale
- Gestion des compteurs cumulés (répertoire + sous-répertoires)

#### DirectoryNavigatorPlugin
Point d'entrée du plugin. Gère :
- Le cycle de vie (activate/deactivate)
- Les subscriptions aux événements
- Les requêtes à la base de données
- L'émission d'événements LOAD_TRACK_LIST

### Algorithme de construction de l'arbre

1. **Collecte** : Récupère tous les filepaths depuis la base de données
2. **Comptage** : Calcule le nombre de pistes par répertoire parent
3. **Préfixe commun** : Trouve le répertoire ancêtre commun de tous les répertoires
4. **Construction** : Crée l'arbre hiérarchique à partir des chemins relatifs
5. **Compteurs cumulés** : Chaque nœud affiche la somme de ses pistes directes + descendants

### Data Roles Qt

Le plugin utilise deux rôles Qt personnalisés pour stocker les métadonnées :

```python
ROLE_PATH = Qt.ItemDataRole.UserRole        # Chemin complet ou "playlist:{id}"
ROLE_NODE_TYPE = Qt.ItemDataRole.UserRole + 1  # "all_tracks", "directory", "playlist", "root"
```

Ces rôles permettent de distinguer le type de nœud lors du clic.

### Requêtes SQL

#### Récupération des pistes d'un répertoire
```sql
SELECT filepath FROM tracks WHERE filepath LIKE '/path/to/dir/%'
```

Utilise `LIKE` avec `%` pour une récursivité automatique.

#### Récupération des pistes d'une playlist
```sql
SELECT t.filepath
FROM tracks t
JOIN playlist_tracks pt ON t.id = pt.track_id
WHERE pt.playlist_id = ?
ORDER BY pt.position
```

### Événements

**Écoute** :
- `TRACKS_ADDED` : Reconstruit l'arbre quand des pistes sont ajoutées
- `TRACK_DELETED` : Reconstruit l'arbre quand une piste est supprimée
- `TRACK_METADATA_UPDATED` : Reconstruit l'arbre en cas de changement de métadonnées

**Émet** :
- `LOAD_TRACK_LIST` : Charge une nouvelle liste de pistes dans la vue principale
  - kwargs: `filepaths` (list[Path])

## Tests

Le plugin est entièrement testé :
- 29 tests dans `tests/plugins/test_directory_navigator.py`
- Couverture des widgets, construction d'arbre, lifecycle, filtrage

Exécuter les tests :
```bash
uv run pytest tests/plugins/test_directory_navigator.py -v
```

### Couverture des tests

**DirectoryTreeWidget** (10 tests) :
- Initialisation UI
- Construction d'arbre (vide, simple, multi-niveaux, playlists)
- Calcul du préfixe commun
- Compteurs cumulés
- Expansion par défaut de "Directories"

**DirectoryNavigatorPlugin** (19 tests) :
- Métadonnées du plugin
- Subscriptions aux événements
- Création et visibilité du widget
- Lifecycle (activate/deactivate)
- Rebuild automatique
- Gestion des clics (all_tracks, directory, playlist, root)
- Conversion Path objects
- Base de données vide

## Dépannage

### L'arbre n'apparaît pas
- Vérifiez que le plugin est activé dans `config/config.yaml`
- Assurez-vous d'être en mode jukebox (pas en curating)
- Redémarrez l'application
- Vérifiez les logs : `[Directory Navigator]`

### L'arbre est vide
- Vérifiez que vous avez des pistes dans la base de données
- La base se trouve dans `~/.jukebox/jukebox.db`
- Consultez les logs pour les erreurs SQL

### Les compteurs sont incorrects
- Le plugin se met à jour automatiquement lors des événements
- Si les compteurs sont désynchronisés, redémarrez l'application
- Vérifiez que les événements TRACK_DELETED sont bien émis lors des suppressions

### Performances avec de nombreux répertoires
L'algorithme de calcul des compteurs a une complexité O(n*m) où :
- n = nombre de répertoires uniques
- m = nombre de répertoires à vérifier pour descendants

Pour des bibliothèques typiques (< 100 répertoires), cela reste instantané.
Si vous observez des ralentissements avec des centaines de répertoires, contactez les mainteneurs.

## Développement

### Modifier le comportement de filtrage

Le filtrage se fait dans `_on_item_clicked()` :

```python
def _on_item_clicked(self, index) -> None:
    # Récupère le type de nœud et le chemin
    node_type = item.data(ROLE_NODE_TYPE)
    path_data = item.data(ROLE_PATH)

    # Query selon le type
    if node_type == "directory":
        rows = db.conn.execute(
            "SELECT filepath FROM tracks WHERE filepath LIKE ?",
            (path_data + "/%",)
        ).fetchall()
```

### Ajouter des nœuds personnalisés

Pour ajouter un nouveau type de nœud (ex: "Favoris", "Récents") :

1. Ajoutez un nœud root dans `build_tree()`
2. Créez des items enfants avec `ROLE_NODE_TYPE` = votre nouveau type
3. Gérez le nouveau type dans `_on_item_clicked()`

### Optimiser les performances

Si le calcul des descendants devient lent :

1. Pré-calculer les totaux cumulés en un seul pass
2. Utiliser un dictionnaire pour stocker les compteurs
3. Éviter la boucle imbriquée dans `_build_directory_nodes()` lignes 145-147

### Logs de debug

Le plugin utilise le logger standard Python :
- `logging.info()` pour la construction de l'arbre
- `logging.debug()` pour l'activation/désactivation et les clics

Activez les logs debug dans `config/config.yaml` :
```yaml
logging:
  level: DEBUG
```

### Intégration avec d'autres plugins

Le plugin émet `LOAD_TRACK_LIST` qui est intercepté par :
- `GenreFilterPlugin` : Applique le filtre de genre sur la nouvelle liste
- Autres plugins écoutant cet événement

Pour créer un plugin qui réagit à la sélection de répertoire :
```python
def initialize(self, context):
    context.subscribe(Events.LOAD_TRACK_LIST, self.on_tracklist_changed)

def on_tracklist_changed(self, filepaths: list[Path]):
    # Réagir au changement de liste
    pass
```

## Améliorations futures

### Fonctionnalités envisagées
- Recherche dans l'arbre
- Glisser-déposer pour déplacer des fichiers
- Menu contextuel (ouvrir dans le finder, etc.)
- Affichage des artistes/albums sous les répertoires
- Indicateur visuel du répertoire actuellement affiché

### Contributions
Les contributions sont les bienvenues ! Suivez ces étapes :
1. Ajoutez vos tests dans `tests/plugins/test_directory_navigator.py`
2. Suivez les conventions de code du projet (black, ruff, mypy)
3. Documentez vos changements dans ce README

## Licence

MIT (comme le reste du projet Jukebox)
