# Checklist après completion d'une tâche

Après avoir modifié du code, il est important de suivre ces étapes pour garantir la qualité:

## 1. Formatage du code

```bash
make format
```

Cela exécute:
- `black jukebox tests` - Formatage automatique
- `ruff check --fix jukebox tests` - Auto-correction des problèmes de linting

**Quand:** Toujours après avoir modifié du code

## 2. Vérification du linting

```bash
make lint
```

Vérifie les problèmes de style et qualité avec ruff.

**Quand:** Après le formatage, avant de commit

## 3. Vérification des types

```bash
make type-check
```

Exécute mypy en mode strict pour détecter les problèmes de types.

**Quand:** Si vous avez modifié des signatures de fonctions ou ajouté du nouveau code

## 4. Exécution des tests

```bash
make test
```

Exécute tous les tests avec couverture. Minimum requis: 70% de couverture.

**Quand:** Toujours, surtout si vous avez:
- Modifié de la logique métier
- Ajouté de nouvelles fonctionnalités
- Corrigé des bugs

### Tests spécifiques

Si vous travaillez sur un composant spécifique:
```bash
# Test d'un fichier
uv run pytest tests/core/test_audio_player.py

# Test d'une fonction
uv run pytest tests/core/test_audio_player.py::test_load_file
```

## 5. Vérification complète CI

```bash
make ci
```

Exécute **tout** dans l'ordre:
1. Formatage (black + ruff --fix)
2. Linting (ruff check)
3. Type checking (mypy)
4. Tests (pytest avec couverture)

**Quand:** Avant de commit ou push, pour être sûr que CI passera

## 6. Test manuel de l'application

```bash
make run
```

Lancez l'application et testez manuellement vos modifications.

**Quand:** 
- Après des modifications UI
- Pour des fonctionnalités nécessitant interaction utilisateur
- Pour vérifier le comportement global

## 7. Vérification Git

```bash
git status
git diff
```

Vérifiez que:
- Vous commitez seulement les fichiers voulus
- Pas de debug code, console.log, commentaires TODO inappropriés
- Pas de fichiers sensibles (.env, credentials, etc.)

## 8. Pre-commit hooks

Les hooks pre-commit s'exécutent automatiquement lors du `git commit`.

Si vous souhaitez les exécuter manuellement:
```bash
pre-commit run --all-files
```

## Ordre recommandé (workflow typique)

```bash
# 1. Après avoir fait vos modifications
make format

# 2. Vérifier que tout passe
make ci

# 3. Test manuel si nécessaire
make run

# 4. Vérifier les changements
git status
git diff

# 5. Commit (hooks s'exécutent automatiquement)
git add <files>
git commit -m "descriptive message"

# 6. Push
git push
```

## Cas spéciaux

### Modifications de plugins uniquement
- Formatage et linting minimum
- Tester le plugin spécifique
- Vérifier que le plugin se charge correctement

### Modifications de configuration
- Valider avec Pydantic (automatique au démarrage)
- Tester l'application avec la nouvelle config

### Modifications de la base de données
- Vérifier les migrations si nécessaire
- Tester avec une base vide et une base existante
- Vérifier la compatibilité backwards

### Ajout de nouvelles dépendances
```bash
# Après modification de pyproject.toml
uv sync
make ci
```

## Si quelque chose échoue

1. **Formatage échoue:** Généralement black auto-corrige, vérifier les conflits
2. **Linting échoue:** Corriger les erreurs signalées par ruff
3. **Type checking échoue:** Ajouter/corriger les type hints
4. **Tests échouent:** Débugger et corriger les tests ou le code
5. **Couverture trop basse:** Ajouter des tests pour atteindre 70%

## Notes importantes

- **Ne pas skip les hooks:** `--no-verify` déconseillé sauf urgence
- **CI doit passer:** Si CI échoue sur GitHub, corriger avant merge
- **Tests d'abord:** Pour TDD, écrire tests avant le code
- **Commits atomiques:** Un commit = une fonctionnalité/fix cohérent
