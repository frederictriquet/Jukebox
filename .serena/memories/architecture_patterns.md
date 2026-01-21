# Architecture et patterns du projet Jukebox

## Paradigme architectural

### Event-Driven Architecture (EDA)

L'application utilise une architecture pilotée par événements avec un EventBus central pour la communication découplée entre composants et plugins.

**EventBus** (`jukebox/core/event_bus.py`):
- Implémente un pattern pub/sub
- Classe `Events` contient les constantes d'événements standard
- Permet aux composants de communiquer sans dépendances directes

**Événements standard:**
- `TRACK_LOADED` - Piste chargée dans le lecteur
- `TRACK_PLAYING` - Lecture démarrée
- `TRACK_STOPPED` - Lecture arrêtée
- `TRACKS_ADDED` - Pistes ajoutées à la bibliothèque
- `SEARCH_PERFORMED` - Recherche effectuée

### Plugin Architecture

**Système extensible de plugins** qui peuvent:
- Ajouter des éléments UI (menus, toolbars, sidebars, widgets)
- S'abonner à des événements via EventBus
- Accéder aux services core (database, player, config, event_bus)
- Être activés/désactivés via configuration

**Protocole JukeboxPlugin:**
```python
class JukeboxPlugin:
    name: str
    version: str
    description: str
    
    def initialize(self, context: PluginContext) -> None:
        """Appelé au chargement. Accède aux services via context."""
        
    def register_ui(self, ui_builder: UIBuilder) -> None:
        """Ajoute des éléments UI."""
        
    def shutdown(self) -> None:
        """Nettoyage au déchargement."""
```

**PluginContext API:**
- `context.database` - Instance Database
- `context.player` - Instance AudioPlayer
- `context.config` - Instance JukeboxConfig
- `context.event_bus` - Instance EventBus
- `context.emit(event, **data)` - Émettre un événement
- `context.subscribe(event, callback)` - S'abonner à un événement

**UIBuilder API** (`jukebox/ui/ui_builder.py`):
- `add_menu(name)` - Ajouter menu à la menubar
- `add_menu_action(menu, text, callback, shortcut)` - Ajouter action à menu
- `add_toolbar_widget(widget)` - Ajouter widget à toolbar
- `add_sidebar_widget(widget, title)` - Ajouter dock widget à droite
- `add_bottom_widget(widget)` - Ajouter widget en bas

## Flow de l'application

### 1. Démarrage (`jukebox/main.py`)
1. Charger config depuis `config/config.yaml`
2. Setup logging
3. Créer QApplication
4. Initialiser MainWindow

### 2. Initialisation MainWindow (`jukebox/ui/main_window.py`)
1. Connexion à la base de données (`~/.jukebox/jukebox.db`)
2. Initialiser AudioPlayer
3. Créer EventBus
4. Construire UI (track list, player controls, search bar)
5. Charger plugins depuis `plugins/`
6. Charger pistes depuis database

### 3. Chargement des plugins (`jukebox/core/plugin_manager.py`)
1. Découvrir fichiers `.py` dans `plugins/`
2. Vérifier si activé dans config (`plugins.enabled`)
3. Instancier classes de plugins
4. Appeler `initialize(context)` avec PluginContext
5. Appeler `register_ui(ui_builder)` avec UIBuilder

## Patterns de design

### Dependency Injection via Context
Les plugins reçoivent un `PluginContext` contenant toutes les dépendances nécessaires, évitant les imports directs et le couplage fort.

### Observer Pattern via EventBus
Communication découplée entre composants via événements pub/sub.

### Strategy Pattern pour les modes
`ModeManager` gère différents modes (curating/jukebox) avec comportements spécifiques.

### Builder Pattern pour UI
`UIBuilder` fournit une interface fluide pour construire l'UI des plugins.

### Mixin Pattern
`ShortcutMixin` (`jukebox/core/shortcut_mixin.py`) fournit fonctionnalité de raccourcis réutilisable.

## Composants Core

### AudioPlayer (`jukebox/core/audio_player.py`)
- Wrapper autour de python-vlc
- Hérite de QObject pour signaux Qt
- Émet signaux pour changements d'état, position, volume
- API asynchrone avec callbacks

### Database (`jukebox/core/database.py`)
- SQLite avec FTS5 pour recherche full-text
- Schéma: table tracks avec métadonnées complètes
- Indices de recherche optimisés
- Support des requêtes full-text avec ranking

### Config (`jukebox/core/config.py`)
- Chargement YAML avec validation Pydantic
- Modèles de données typés pour toutes les sections
- Validation automatique des types et valeurs
- Support de configuration hiérarchique

## Guidelines architecturaux

### 1. Découplage via EventBus
- Préférer EventBus pour communication inter-composants
- Éviter dépendances directes entre plugins
- Utiliser événements standard quand possible

### 2. Plugin-first design
- Nouvelles fonctionnalités devraient être des plugins si possible
- Garder le core minimal et stable
- Plugins doivent être optionnels et indépendants

### 3. Configuration centralisée
- Toute configuration dans `config/config.yaml`
- Validation Pydantic pour sécurité des types
- Pas de valeurs hard-codées dans le code

### 4. Type safety
- Type hints obligatoires (mypy strict)
- Utiliser Pydantic pour validation de données
- Éviter `Any` sauf absolument nécessaire

### 5. Qt best practices
- Signaux/slots pour communication UI
- Pas de logique métier dans les widgets
- Thread safety pour opérations longues

### 6. Database patterns
- Utiliser FTS5 pour recherche textuelle
- Préférer requêtes préparées (SQL injection safety)
- Transactions pour opérations multiples

### 7. Testing
- Tests unitaires pour logique métier
- pytest-qt pour composants UI
- Mocks pour dépendances externes (VLC)
- Viser 70%+ de couverture

### 8. Error handling
- Logger les erreurs importantes
- Graceful degradation pour plugins qui échouent
- Feedback utilisateur approprié pour erreurs UI

## Conventions de code spécifiques

### Événements
Définir événements comme constantes dans `Events`:
```python
class Events:
    TRACK_LOADED = "track_loaded"
    # ...
```

### Plugins
Toujours définir les métadonnées:
```python
class MyPlugin:
    name = "my_plugin"  # snake_case
    version = "1.0.0"   # semantic versioning
    description = "Clear description"
```

### Configuration
Utiliser Pydantic models pour validation:
```python
class MyConfig(BaseModel):
    setting: int = Field(default=10, ge=0, le=100)
```

### Database
Utiliser context manager pour connexions:
```python
with database.get_connection() as conn:
    # ... opérations
```

## Anti-patterns à éviter

1. **Couplage fort entre plugins** - Utiliser EventBus
2. **Logique métier dans UI** - Séparer concerns
3. **Imports circulaires** - Restructurer dépendances
4. **Magic numbers** - Utiliser constantes ou config
5. **Ignorer type hints** - Respecter mypy strict
6. **Blocage de UI thread** - Utiliser workers pour I/O
7. **Hardcoding paths** - Utiliser config ou paths relatifs
8. **Skip de tests** - Maintenir couverture 70%+
