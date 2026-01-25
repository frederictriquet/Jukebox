# Roadmap VJing Effects - Video Exporter Plugin

## Vue d'ensemble

Cette roadmap définit le plan d'implémentation et d'amélioration des effets visuels VJing pour le plugin video_exporter. Les effets sont organisés par catégorie et priorité.

---

## Phase 1 : Fondations (✅ COMPLÉTÉ)

### 1.1 Infrastructure audio
- [x] Extraction énergie globale par frame
- [x] Séparation basses/mids/aigus (filtres Butterworth)
- [x] Détection de beats (onset detection sur basses)
- [x] Pré-calcul FFT 32 bandes par frame
- [x] Normalisation des données

### 1.2 Architecture des effets
- [x] Système de contexte (`ctx`) avec energy, bass, mid, treble, fft, is_beat
- [x] Mapping genre → effet configurable
- [x] Support multi-effets (genres multi-lettres)
- [x] Liste `AVAILABLE_EFFECTS` pour documentation

---

## Phase 2 : Effets de base (✅ COMPLÉTÉ)

### 2.1 Effets classiques
| Effet | Status | Description |
|-------|--------|-------------|
| `wave` | ✅ | Vagues sinusoïdales fluides |
| `neon` | ✅ | Formes néon pulsantes |
| `vinyl` | ✅ | Sillons de vinyle rotatifs |
| `particles` | ✅ | Particules colorées basiques |

### 2.2 Effets rythmiques
| Effet | Status | Description |
|-------|--------|-------------|
| `pulse` | ✅ | Cercles expansifs sur beats |
| `strobe` | ✅ | Stroboscope intelligent |

---

## Phase 3 : Effets spectraux (✅ COMPLÉTÉ)

| Effet | Status | Description |
|-------|--------|-------------|
| `fft_bars` | ✅ | Barres FFT verticales colorées |
| `fft_rings` | ✅ | Anneaux concentriques FFT |
| `bass_warp` | ✅ | Déformation polygonale par basses |

---

## Phase 4 : Systèmes de particules avancés (✅ COMPLÉTÉ)

| Effet | Status | Description |
|-------|--------|-------------|
| `flow_field` | ✅ | Champ de flux pseudo-Perlin |
| `explosion` | ✅ | Explosion sur beats forts |

---

## Phase 5 : Effets géométriques (✅ COMPLÉTÉ)

| Effet | Status | Description |
|-------|--------|-------------|
| `kaleidoscope` | ✅ | Motifs kaléidoscopiques |
| `lissajous` | ✅ | Courbes de Lissajous modulées |
| `tunnel` | ✅ | Tunnel infini avec profondeur |
| `spiral` | ✅ | Spirale animée colorée |

---

## Phase 6 : Post-processing (✅ COMPLÉTÉ)

| Effet | Status | Description |
|-------|--------|-------------|
| `chromatic` | ✅ | Aberration chromatique RGB |
| `glitch` | ✅ | Glitch + bruit digital |
| `pixelate` | ✅ | Pixelisation dynamique |
| `feedback` | ✅ | Traînées avec décroissance |

---

## Phase 7 : Effets naturels (✅ COMPLÉTÉ)

| Effet | Status | Description |
|-------|--------|-------------|
| `fire` | ✅ | Flammes animées |
| `water` | ✅ | Ondulations d'eau sur beats |
| `aurora` | ✅ | Aurore boréale ondulante |

---

## Phase 8 : Améliorations futures (🔄 À FAIRE)

### 8.1 Effets supplémentaires (Priorité Haute) ✅ COMPLÉTÉ
| Effet | Status | Description | Complexité |
|-------|--------|-------------|------------|
| `fractal` | ✅ | Fractales Julia animées (modulées par audio) | Élevée |
| `wormhole` | ✅ | Trou de ver avec distorsion spirale | Moyenne |
| `plasma` | ✅ | Plasma coloré ondulant (sinus combinés) | Moyenne |
| `matrix` | ✅ | Pluie de caractères style Matrix | Faible |
| `radar` | ✅ | Balayage radar circulaire avec blips | Faible |

### 8.2 Effets supplémentaires (Priorité Moyenne) ✅ COMPLÉTÉ
| Effet | Status | Description | Complexité |
|-------|--------|-------------|------------|
| `starfield` | ✅ | Champ d'étoiles 3D avec perspective | Faible |
| `lightning` | ✅ | Éclairs ramifiés sur beats | Moyenne |
| `voronoi` | ✅ | Diagramme de Voronoï animé | Moyenne |
| `metaballs` | ✅ | Métaballs fluides (blob effect) | Élevée |
| `smoke` | ✅ | Simulation de fumée avec turbulence | Élevée |

### 8.3 Améliorations techniques
| Amélioration | Status | Description |
|--------------|--------|-------------|
| Vrai bruit de Perlin | ⬜ | Remplacer pseudo-noise par noise library |
| Shaders GPU (optionnel) | ⬜ | Moderngl pour effets lourds |
| Présets d'effets | ⬜ | Combinaisons pré-configurées |
| Transitions entre effets | ⬜ | Fondu entre effets |
| LFO modulables | ⬜ | Oscillateurs basse fréquence paramétrables |

### 8.4 Configuration avancée
| Feature | Status | Description |
|---------|--------|-------------|
| Intensité par effet | ⬜ | Slider d'intensité individuel |
| Palette de couleurs | ⬜ | Palettes configurables par effet |
| Sensibilité audio | ⬜ | Ajuster réactivité par bande |
| Mode preview | ⬜ | Aperçu temps réel dans le dialog |

---

## Mappings par défaut actuels

Genres valides: D, C, P, T, H, G, I, A, W, B, F, R, L, U, O, N

```python
DEFAULT_MAPPINGS = {
    "D": "aurora",       # Deep - chill, ambient
    "C": "kaleidoscope", # Classic - elegant
    "P": "strobe",       # Power - energetic
    "T": "fractal",      # Trance - hypnotic, psychedelic
    "H": "fire",         # House - groovy, warm
    "G": "flow_field",   # Garden - natural
    "I": "neon",         # Ibiza - club, colorful
    "A": "wave",         # A Cappella - soft
    "W": "plasma",       # Weed - chill, psychedelic
    "B": "glitch",       # Banger - intense
    "F": "particles",    # Fun - playful, festive
    "R": "vinyl",        # Retro - vintage
    "L": "lissajous",    # Loop - repetitive, hypnotic
    "U": "wormhole",     # Unclassable - weird, experimental
    "O": "flow_field",   # Organic - natural
    "N": "wave",         # Namaste - zen, calm
}
```

---

## Notes techniques

### Pilotage audio
- **energy** : Énergie RMS globale (0-1)
- **bass** : Énergie 20-250 Hz (0-1)
- **mid** : Énergie 250-4000 Hz (0-1)
- **treble** : Énergie 4000+ Hz (0-1)
- **fft** : 32 bandes FFT normalisées
- **is_beat** : Booléen, vrai sur les beats détectés

### Fichiers concernés
- `plugins/video_exporter/layers/vjing_layer.py` : Tous les effets
- `plugins/video_exporter/plugin.py` : Configuration et settings
- `config/config.yaml` : Mappings VJing

### Performance
- Pré-calcul des données audio dans `_precompute()`
- Effets à particules : limiter le nombre max
- Éviter allocations mémoire dans `render()`
- Feedback buffer : réutiliser l'image

---

## Changelog

### v1.5 (2026-01-25)
- Ajout effet `metaballs` (blobs fluides qui fusionnent, field function)
- Ajout effet `smoke` (fumée avec particules et turbulence)
- Suppression effet `glitch` (à la demande)
- Total: 30 effets disponibles
- Phase 8.2 complétée

### v1.4 (2026-01-25)
- Support multi-effets par genre (ex: `effects: ["fractal", "tunnel"]`)
- Format config.yaml modifié: `effect` → `effects` (liste)
- Rétrocompatibilité avec ancien format via `get_effects()`

### v1.3 (2026-01-25)
- Ajout effet `starfield` (champ d'étoiles 3D avec perspective et motion trails)
- Ajout effet `lightning` (éclairs ramifiés récursifs sur beats)
- Ajout effet `voronoi` (diagramme de Voronoï animé avec détection de bords)
- Total: 29 effets disponibles

### v1.2 (2026-01-25)
- Ajout effet `radar` (balayage radar avec blips sur beats)
- Ajout effet `plasma` (plasma ondulant multi-couleurs)
- Ajout effet `wormhole` (tunnel spirale avec effet de profondeur)
- Suppression effet `matrix` (à la demande)

### v1.1 (2026-01-25)
- Ajout effet `fractal` (Julia set animé)
- Mapping: T (Trance) → fractal

### v1.0 (2026-01-25)
- Implémentation initiale de 22 effets
- Système de contexte audio complet
- Mappings par genre configurables
