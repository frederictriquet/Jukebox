# Roadmap Jukebox - Vue d'Ensemble

**Date**: 2026-01-07
**Version**: 1.0
**Objectif**: Développer une application audio modulaire multiplateforme avec un MVP fonctionnel rapidement

---

## Philosophie de Développement

Cette roadmap suit une approche **progressive et itérative** qui privilégie :

1. **MVP First** : Fonctionnalités essentielles en priorité
2. **Quality Early** : Tests, CI/CD et qualité de code dès le départ
3. **Build Often** : Packages distribuables dès les premières semaines
4. **Incremental Complexity** : Architecture simple puis évolution vers la modularité

---

## Chronologie Globale

```
Semaine 1-2  │ MVP Foundation + CI/CD Setup
Semaine 2-3  │ Core Features + Testing Infrastructure
Semaine 3-4  │ Plugin System Architecture
Semaine 4-6  │ Essential Modules Development
Semaine 6-8  │ Advanced Features + Optimization
Semaine 8-10 │ Polish, Distribution & Release
```

---

## Structure de la Roadmap

### [Phase 1: MVP Foundation](01-MVP-FOUNDATION.md) (Semaines 1-2)
**Objectif**: Application minimale fonctionnelle avec lecture audio et liste de pistes

**Livrables**:
- ✅ Setup projet (uv, structure)
- ✅ UI basique avec PySide6
- ✅ Lecture audio (python-vlc)
- ✅ Liste de pistes simple
- ✅ Configuration YAML

**Milestone**: `v0.1.0-alpha` - Application qui lit de la musique

---

### [Phase 2: CI/CD & Quality](02-CI-CD-SETUP.md) (Semaine 2)
**Objectif**: Infrastructure de qualité et déploiement automatisé

**Livrables**:
- ✅ GitHub Actions CI/CD
- ✅ Tests automatisés (pytest)
- ✅ Qualité code (ruff, mypy, black)
- ✅ Build automatique des packages
- ✅ Pre-commit hooks

**Milestone**: `v0.2.0-alpha` - CI/CD opérationnel

---

### [Phase 3: Testing Infrastructure](03-TESTING-QUALITY.md) (Semaine 2-3)
**Objectif**: Framework de tests complet et contrôles qualité

**Livrables**:
- ✅ Tests unitaires (core)
- ✅ Tests d'intégration
- ✅ Coverage reporting
- ✅ Documentation standards
- ✅ Linting et formatage

**Milestone**: Coverage > 70%, tous les checks passent

---

### [Phase 4: Core Features](04-CORE-FEATURES.md) (Semaines 3-4)
**Objectif**: Fonctionnalités essentielles pour un jukebox utilisable

**Livrables**:
- ✅ Database SQLite + FTS5
- ✅ Scan automatique de dossiers
- ✅ Extraction tags ID3 (mutagen)
- ✅ Recherche full-text
- ✅ Playlists basiques
- ✅ Historique d'écoute

**Milestone**: `v0.3.0-beta` - Jukebox fonctionnel

---

### [Phase 5: Plugin System](05-PLUGIN-SYSTEM.md) (Semaines 4-5)
**Objectif**: Architecture modulaire extensible

**Livrables**:
- ✅ Plugin Manager
- ✅ Event Bus
- ✅ UIBuilder API
- ✅ Module discovery
- ✅ 2-3 plugins exemples

**Milestone**: `v0.4.0-beta` - Architecture modulaire

---

### [Phase 6: Essential Modules](06-ESSENTIAL-MODULES.md) (Semaines 5-6)
**Objectif**: Modules indispensables pour la curation

**Livrables**:
- ✅ Module duplicate finder
- ✅ Module file curator
- ✅ Module waveform visualizer
- ✅ Module recommendations

**Milestone**: `v0.5.0-beta` - MVP Complet

---

### [Phase 7: Advanced Features](07-ADVANCED-FEATURES.md) (Semaines 6-8)
**Objectif**: Fonctionnalités avancées et optimisations

**Livrables**:
- ✅ Waveforms 3D
- ✅ Mode jukebox vs curating
- ✅ Thèmes UI
- ✅ Raccourcis clavier
- ✅ Optimisations Raspberry Pi

**Milestone**: `v0.9.0-rc` - Feature Complete

---

### [Phase 8: Distribution & Release](08-DISTRIBUTION-RELEASE.md) (Semaines 8-10)
**Objectif**: Packages finalisés et documentation

**Livrables**:
- ✅ PyInstaller builds (Mac/Linux/Windows)
- ✅ Script installation Raspberry Pi
- ✅ Documentation utilisateur
- ✅ Contributing guide
- ✅ Release notes

**Milestone**: `v1.0.0` - Production Ready

---

## Priorités par Objectif

### 🎯 Priorité 1 - MVP (Semaines 1-3)
Ce qui permet d'avoir une application utilisable :
- Lecture audio
- Liste de pistes
- Recherche basique
- CI/CD
- Tests

### 🎯 Priorité 2 - Utilisabilité (Semaines 3-6)
Ce qui rend l'application pratique :
- Database avec métadonnées
- Scan automatique
- Playlists
- Architecture modulaire
- Quelques modules essentiels

### 🎯 Priorité 3 - Excellence (Semaines 6-10)
Ce qui distingue l'application :
- Waveforms avancées
- Recommandations
- Interface polie
- Performance optimisée
- Distribution multiplateforme

---

## Principes de Développement

### 1. Test-Driven Development (TDD)
- Écrire les tests AVANT le code
- Viser 70%+ de coverage
- Tests automatisés dans la CI

### 2. Continuous Integration
- Tous les commits passent par la CI
- Checks automatiques (lint, types, tests)
- Builds automatiques des packages

### 3. Incremental Complexity
- Commencer simple
- Ajouter la complexité progressivement
- Refactorer quand nécessaire

### 4. Documentation as Code
- Docstrings pour toutes les fonctions publiques
- README à jour
- CHANGELOG systématique

### 5. User Feedback Early
- Tester sur Raspberry Pi dès la Phase 1
- Itérations rapides
- MVP utilisable rapidement

---

## Stack Technique Rappel

### Core
- **Langage**: Python 3.11+
- **UI**: PySide6 (LGPL)
- **Audio**: python-vlc
- **Database**: SQLite + FTS5

### Development
- **Gestion dépendances**: uv
- **Tests**: pytest
- **Linting**: ruff
- **Type checking**: mypy
- **Formatage**: black
- **CI/CD**: GitHub Actions

### Distribution
- **Packaging**: PyInstaller
- **Raspberry Pi**: pip + requirements.txt

---

## Métriques de Succès

### Phase MVP (Semaines 1-3)
- ✅ Application démarre en < 3s
- ✅ Lit MP3/FLAC sans latence
- ✅ CI/CD opérationnel
- ✅ Tests passent à 100%
- ✅ Un package distribuable existe

### Phase Beta (Semaines 3-6)
- ✅ Scan 1000 pistes en < 30s
- ✅ Recherche FTS5 < 100ms
- ✅ Coverage > 70%
- ✅ Architecture modulaire validée
- ✅ 3+ modules fonctionnels

### Phase Release (Semaines 8-10)
- ✅ Fonctionne sur Mac/Linux/Raspberry Pi
- ✅ Packages pour toutes plateformes
- ✅ Documentation complète
- ✅ Performance validée sur Pi
- ✅ Zero known critical bugs

---

## Gestion des Risques

### Risque: Performance Raspberry Pi
- **Mitigation**: Tests early, profiling continu
- **Phase**: 1, 6, 7

### Risque: Complexité architecture modulaire
- **Mitigation**: Commencer simple, refactorer progressivement
- **Phase**: 5

### Risque: Distribution multiplateforme
- **Mitigation**: CI/CD avec builds automatiques dès Phase 2
- **Phase**: 2, 8

### Risque: Scope creep
- **Mitigation**: Roadmap stricte, features dans backlog
- **Phase**: Toutes

---

## Notes d'Implémentation

### Versioning Sémantique
```
v0.1.0-alpha : MVP Foundation
v0.2.0-alpha : CI/CD Setup
v0.3.0-beta  : Core Features
v0.4.0-beta  : Plugin System
v0.5.0-beta  : Essential Modules (MVP Complet)
v0.9.0-rc    : Feature Complete
v1.0.0       : Production Release
```

### Git Workflow
- **main**: Code stable, releasable
- **develop**: Intégration features
- **feature/***: Branches par feature
- **hotfix/***: Corrections urgentes

### Release Process
1. Feature freeze
2. Tests complets
3. Documentation update
4. CHANGELOG update
5. Version bump
6. Tag release
7. Build packages
8. GitHub Release

---

## Ressources

### Documentation Interne
- [Phase 1 - MVP Foundation](01-MVP-FOUNDATION.md)
- [Phase 2 - CI/CD Setup](02-CI-CD-SETUP.md)
- [Phase 3 - Testing & Quality](03-TESTING-QUALITY.md)
- [Phase 4 - Core Features](04-CORE-FEATURES.md)
- [Phase 5 - Plugin System](05-PLUGIN-SYSTEM.md)
- [Phase 6 - Essential Modules](06-ESSENTIAL-MODULES.md)
- [Phase 7 - Advanced Features](07-ADVANCED-FEATURES.md)
- [Phase 8 - Distribution & Release](08-DISTRIBUTION-RELEASE.md)

### Références Externes
- [Tech Stack Recommendations](../tech-stack-recommendation.md)
- [Python Documentation](https://docs.python.org/3/)
- [PySide6 Documentation](https://doc.qt.io/qtforpython-6/)
- [uv Documentation](https://github.com/astral-sh/uv)

---

## Prochaines Étapes

1. ✅ Lire cette overview complète
2. 📖 Consulter [Phase 1 - MVP Foundation](01-MVP-FOUNDATION.md)
3. 🚀 Commencer par le setup du projet
4. 🔄 Suivre la roadmap phase par phase
5. 📊 Tracker la progression avec les milestones

---

**Dernière mise à jour**: 2026-01-07
**Prochaine revue**: Fin de chaque phase
