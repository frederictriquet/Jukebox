# Genre Filter Plugin

Plugin de filtrage par genre pour le mode jukebox de Jukebox.

## Vue d'ensemble

Le plugin Genre Filter ajoute une barre d'outils avec des boutons à bascule permettant de filtrer la liste des pistes par genre. Chaque bouton représente un code de genre (H, T, W, etc.) et peut prendre trois états :

- **INDIFFERENT** (gris) : Le genre n'est pas pris en compte dans le filtrage
- **ON** (vert) : Les pistes doivent avoir ce genre
- **OFF** (rouge) : Les pistes ne doivent PAS avoir ce genre

## Installation

1. Le plugin est déjà présent dans `plugins/genre_filter.py`
2. Activez-le dans `config/config.yaml` :

```yaml
plugins:
  enabled:
    - genre_filter
```

3. Redémarrez l'application

## Utilisation

### En mode jukebox

1. Basculez en mode jukebox (le plugin s'active automatiquement)
2. Les boutons de genre apparaissent dans la barre d'outils
3. Cliquez sur un bouton pour faire défiler les états :
   - Gris → Vert → Rouge → Gris...

### Logique de filtrage

#### Filtres ON (boutons verts)
Les pistes doivent avoir **TOUS** les genres marqués ON.

**Exemple** : Si H (House) et W (Weed) sont ON, seules les pistes avec "H-W" ou "H-W-T" seront affichées.

#### Filtres OFF (boutons rouges)
Les pistes ne doivent avoir **AUCUN** des genres marqués OFF.

**Exemple** : Si T (Trance) est OFF, toutes les pistes contenant "T" seront masquées.

#### Combinaison
Vous pouvez combiner des filtres ON et OFF.

**Exemple** : H ON, W OFF → Affiche les pistes House qui ne sont pas Weed.

### Interaction avec d'autres fonctionnalités

Le filtre fonctionne de manière transparente avec :
- **Recherche** : Le filtre s'applique aux résultats de recherche
- **Navigation** : Les flèches haut/bas ne visitent que les pistes visibles
- **Random** : Ne sélectionne que parmi les pistes visibles
- **Count** : Le compteur affiche le nombre de pistes filtrées

### Basculement de mode

- Le filtre est **actif uniquement en mode jukebox**
- Lorsque vous basculez vers un autre mode, le filtre est désactivé (toutes les pistes sont affichées)
- Lorsque vous revenez au mode jukebox, l'état du filtre est restauré

## Architecture technique

### Composants

#### GenreFilterProxyModel
Modèle proxy Qt (`QSortFilterProxyModel`) qui s'intercale entre le `TrackListModel` et la vue `QTableView`. Implémente la logique de filtrage dans `filterAcceptsRow()`.

#### GenreFilterButton
Bouton personnalisé avec cycle à 3 états. Dimensions compactes (28x22 px) pour la barre d'outils.

#### GenreFilterPlugin
Point d'entrée du plugin. Gère le cycle de vie et la coordination entre les boutons et le modèle proxy.

### Format des genres

Les genres sont stockés sous forme de chaînes comme `"H-W-*3"` où :
- `H`, `W` : Codes de genre (lettres)
- `*3` : Étoiles de notation (ignorées par le filtre)

Le parsing extrait les codes de genre en excluant les parties commençant par `*`.

### Événements

**Écoute** :
- `TRACKS_ADDED` : Re-applique le filtre quand la liste change

**Émet** :
- `GENRE_FILTER_CHANGED` : Notifie les changements de filtre
  - kwargs: `on_genres` (set), `off_genres` (set)

## Configuration

Les codes de genre sont définis dans `config/config.yaml` sous `genre_editor.codes` :

```yaml
genre_editor:
  codes:
    - code: H
      name: House
    - code: T
      name: Trance
    - code: W
      name: Weed
    # etc.
```

Le plugin crée automatiquement un bouton pour chaque code, trié alphabétiquement.

## Tests

Le plugin est entièrement testé :
- 25 tests dans `tests/plugins/test_genre_filter.py`
- Couverture des états, logique de filtrage, cycle de vie du plugin

Exécuter les tests :
```bash
uv run pytest tests/plugins/test_genre_filter.py -v
```

## Dépannage

### Les boutons n'apparaissent pas
- Vérifiez que le plugin est activé dans `config/config.yaml`
- Assurez-vous d'être en mode jukebox
- Redémarrez l'application

### Le filtre ne fonctionne pas
- Vérifiez que vos pistes ont des genres définis
- Les genres doivent être au format "H-W-*3" (codes séparés par des tirets)
- Consultez les logs pour les erreurs : `[Genre Filter]`

### Performances
Le filtrage est très rapide (Qt natif). Si vous rencontrez des ralentissements avec des milliers de pistes, vérifiez les performances globales de l'application.

## Développement

### Modifier le style des boutons

Les styles sont définis dans `GenreFilterButton._STYLES` :

```python
_STYLES = {
    GenreFilterState.INDIFFERENT: "background-color: #555; color: #aaa;",
    GenreFilterState.ON: "background-color: #2d7a2d; color: white;",
    GenreFilterState.OFF: "background-color: #7a2d2d; color: white;",
}
```

### Ajouter des états supplémentaires

Pour ajouter un 4e état, modifiez :
1. `GenreFilterState` (ajoutez une valeur)
2. `GenreFilterButton._cycle()` (changez le modulo)
3. `GenreFilterButton._STYLES` (ajoutez un style)
4. `GenreFilterProxyModel.filterAcceptsRow()` (logique de filtrage)

### Logs de debug

Le plugin utilise le logger standard Python :
- `logging.info()` pour les événements majeurs
- `logging.debug()` pour les détails (activation, désactivation)

Activez les logs debug dans `config/config.yaml` :
```yaml
logging:
  level: DEBUG
```

## Licence

MIT (comme le reste du projet Jukebox)
