# VJing Effects - Status & Roadmap

Ce fichier documente tous les effets VJing du plugin video_exporter, leur statut d'implémentation et les améliorations futures.

---

## Effets Implémentés (30 effets)

### Effets rythmiques (beat/tempo)

| Effet | Description | Audio-réactif | GPU | Complet | Commentaire |
|-------|-------------|---------------|-----|---------|-------------|
| `pulse` | Cercles expansifs sur beats | energy, bass, is_beat | Non | Partiel | Manque envelope ADSR pour variation plus musicale |
| `strobe` | Stroboscope intelligent | energy, treble | Non | Partiel | Manque pattern euclidien et synchronisation BPM |

### Effets spectraux (FFT)

| Effet | Description | Audio-réactif | GPU | Complet | Commentaire |
|-------|-------------|---------------|-----|---------|-------------|
| `fft_bars` | Barres FFT verticales colorées | fft (32 bandes) | Non | Partiel | Manque version organique avec courbes de Bézier |
| `fft_rings` | Anneaux concentriques FFT | fft (32 bandes) | Non | Partiel | Manque interpolation lissée |
| `bass_warp` | Déformation polygonale par basses | bass, energy | Non | Oui | Correspond à "Bass-Driven Distortion" |

### Systèmes de particules

| Effet | Description | Audio-réactif | GPU | Complet | Commentaire |
|-------|-------------|---------------|-----|---------|-------------|
| `particles` | Particules colorées basiques | energy, is_beat | Non | Oui | Particules rythmiques |
| `flow_field` | Champ de flux Perlin/Simplex | energy, bass | Non | Oui | Utilise vrai bruit Perlin. Idéal organic house |
| `explosion` | Explosion de particules sur beats forts | bass, is_beat | Non | Oui | Explosion/implosion sonore |
| `starfield` | Champ d'étoiles 3D avec perspective | energy, bass | Non | Oui | Bonus. Non décrit dans VJ-effects.md |

### Effets géométriques

| Effet | Description | Audio-réactif | GPU | Complet | Commentaire |
|-------|-------------|---------------|-----|---------|-------------|
| `kaleidoscope` | Motifs kaléidoscopiques symétriques | energy, bass | Non | Oui | Correspond à "Mandalas/formes radiales" |
| `lissajous` | Courbes de Lissajous modulées | energy, bass, mid | Non | Oui | Bonus. Non décrit dans VJ-effects.md |
| `tunnel` | Tunnel infini avec profondeur | energy, bass | Non | Oui | Correspond à "Tunnels/vortex" |
| `spiral` | Spirale animée colorée | energy, bass | Non | Oui | Bonus. Non décrit dans VJ-effects.md |
| `radar` | Balayage radar circulaire avec blips | energy, is_beat | Non | Oui | Bonus. Non décrit dans VJ-effects.md |

### Effets procéduraux / GPU

| Effet | Description | Audio-réactif | GPU | Complet | Commentaire |
|-------|-------------|---------------|-----|---------|-------------|
| `fractal` | Fractales Julia animées | energy, bass | Oui | Oui | Bonus. Shader GLSL optimisé |
| `plasma` | Plasma coloré ondulant | energy, bass | Oui | Oui | Correspond à "Bruit procédural animé" |
| `wormhole` | Trou de ver avec distorsion spirale | energy, bass | Oui | Oui | Variante de tunnel/vortex |
| `voronoi` | Diagramme de Voronoï animé | energy, bass | Oui | Oui | Bonus. Non décrit dans VJ-effects.md |
| `metaballs` | Métaballs fluides (blob effect) | energy, bass, is_beat | Oui | Oui | Correspond à "Simulation fluides simplifiée" |

### Effets naturels

| Effet | Description | Audio-réactif | GPU | Complet | Commentaire |
|-------|-------------|---------------|-----|---------|-------------|
| `fire` | Flammes animées | energy, bass | Non | Oui | Bonus. Non décrit dans VJ-effects.md |
| `water` | Ondulations d'eau sur beats | bass, is_beat | Non | Oui | Bonus. Non décrit dans VJ-effects.md |
| `aurora` | Aurore boréale ondulante | energy, mid | Non | Oui | Bonus. Non décrit dans VJ-effects.md |
| `smoke` | Simulation de fumée avec turbulence | energy, bass | Non | Oui | Correspond à "Simulation fluides" avec turbulence |
| `lightning` | Éclairs ramifiés sur beats | bass, is_beat | Non | Oui | Bonus. Non décrit dans VJ-effects.md |

### Effets classiques / ambiance

| Effet | Description | Audio-réactif | GPU | Complet | Commentaire |
|-------|-------------|---------------|-----|---------|-------------|
| `wave` | Vagues sinusoïdales fluides | energy, bass | Non | Oui | Bonus. Non décrit dans VJ-effects.md |
| `neon` | Formes néon pulsantes | energy, bass, is_beat | Non | Oui | Bonus. Non décrit dans VJ-effects.md |
| `vinyl` | Sillons de vinyle rotatifs | energy | Non | Oui | Bonus. Non décrit dans VJ-effects.md |

### Post-processing

| Effet | Description | Audio-réactif | GPU | Complet | Commentaire |
|-------|-------------|---------------|-----|---------|-------------|
| `chromatic` | Aberration chromatique RGB | energy, bass | Non | Oui | Correspond à "Aberration chromatique" |
| `pixelate` | Pixelisation dynamique | energy | Non | Oui | Bonus. Non décrit dans VJ-effects.md |
| `feedback` | Traînées avec décroissance (motion trails) | energy | Non | Oui | Correspond à "Video Feedback" et "Motion trails" |
| `timestretch` | Ralenti/accélération selon énergie | energy (derivative) | Non | Oui | Correspond à "Time-stretch visuel" |

---

## Effets Non Implémentés (à développer)

### Priorité Haute

| Effet | Description | Complexité | Notes |
|-------|-------------|------------|-------|
| `spectogram` | Spectrogramme temporel abstrait | Moyenne | Accumulation FFT avec défilement horizontal/radial. Idéal ambient/deep house |
| `grid` | Grilles dynamiques 2D/3D | Moyenne | Déformation par ondes sinusoïdales déclenchées par kicks |
| `bloom` | Glow/Bloom audio-réactif | Faible | Intensité liée aux hautes fréquences. Post-processing |

### Priorité Moyenne

| Effet | Description | Complexité | Notes |
|-------|-------------|------------|-------|
| `morph` | Morphing de formes | Élevée | Interpolation continue entre formes, déclenché par sections musicales |

### Améliorations des effets existants

| Effet | Amélioration | Description |
|-------|--------------|-------------|
| `pulse` | Envelope ADSR | Variation plus musicale avec attack/decay/sustain/release |
| `fft_bars` | Courbes de Bézier | Version organique avec interpolation lissée |
| `fft_rings` | Courbes de Bézier | Version organique avec interpolation lissée |

---

## Architecture technique

### Fichiers concernés
- `plugins/video_exporter/layers/vjing_layer.py` - Tous les effets (méthodes `_render_*`)
- `plugins/video_exporter/layers/gpu_shaders.py` - Shaders GPU ModernGL (5 shaders)
- `plugins/video_exporter/renderers/frame_renderer.py` - Compositeur de frames
- `plugins/video_exporter/export_dialog.py` - Dialog d'export + EffectPreviewDialog

### Contexte audio disponible
```python
ctx = {
    "energy": float,      # Énergie RMS globale (0-1)
    "bass": float,        # Énergie 20-250 Hz (0-1)
    "mid": float,         # Énergie 250-4000 Hz (0-1)
    "treble": float,      # Énergie 4000+ Hz (0-1)
    "fft": np.array,      # 32 bandes FFT normalisées
    "is_beat": bool,      # Vrai sur les beats détectés
}
```

### Palettes de couleurs disponibles
- `neon` - Rose, cyan, jaune, violet, vert
- `fire` - Oranges et rouges
- `ice` - Bleus et blancs
- `nature` - Verts et bruns
- `sunset` - Oranges, roses, violets
- `ocean` - Bleus et turquoises
- `cosmic` - Violets et roses
- `retro` - Couleurs années 80
- `monochrome` - Niveaux de gris
- `rainbow` - Arc-en-ciel complet

### Shaders GPU (ModernGL)
Les shaders GPU supportent les palettes dynamiques via uniforms `vec3 palette[5]`.
Effets GPU : `plasma`, `fractal`, `metaballs`, `wormhole`, `voronoi`

---

## Combinaisons recommandées par style

### House
- `pulse` + `particles` + `wave`
- Couleurs chaudes (`fire`, `sunset`)
- Mouvement fluide

### Techno
- `tunnel` + `strobe` + `grid` (à implémenter)
- Contraste fort (`monochrome`, `neon`)
- Répétition hypnotique

### Organic House
- `flow_field` + `aurora` + `smoke`
- Couleurs naturelles (`nature`, `ocean`)
- Morphing lent, non linéaire

### Trance / Psychédélique
- `fractal` + `wormhole` + `kaleidoscope`
- Couleurs vives (`cosmic`, `rainbow`)
- Mouvements hypnotiques

### Deep House / Ambient
- `plasma` + `water` + `spectogram` (à implémenter)
- Couleurs douces (`ice`, `ocean`)
- Transitions lentes

---

## Changelog

### v1.17 (2026-01-26)
- Support palettes dynamiques dans les shaders GPU
- Uniform `vec3 palette[5]` dans tous les shaders GPU
- Audio indépendant pour les previews (VLC local)

### v1.16 (2026-01-25)
- Fix: Toutes les previews utilisent la palette de couleurs configurée
- 16+ méthodes de rendu modifiées pour utiliser `self.color_palette`

### v1.15 (2026-01-25)
- Preview individuelle par effet (bouton 👁)

### v1.14 (2026-01-25)
- Mode preview temps réel avec Play/Pause

### v1.9-v1.13
- Shaders GPU ModernGL
- Bibliothèque noise pour Perlin
- Système LFO
- Transitions crossfade
- Présets d'effets
- Configuration avancée (intensité, palettes, sensibilité audio)

### v1.0 (2026-01-25)
- Implémentation initiale de 22 effets
