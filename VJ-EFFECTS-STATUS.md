# VJing Effects — À développer

## Améliorations d'effets existants

| Effet | Description |
|-------|-------------|
| `morph` | Morphing de formes déclenché par sections musicales |
| `pulse` | Amélioration : envelope ADSR |
| `fft_bars` / `fft_rings` | Amélioration : courbes de Bézier organiques |

## Effets pas terribles

| Effet | Description |
|-------|-------------|
| `matrix` | Pluie de caractères style Matrix, vitesse modulée par l'énergie |
| `oscilloscope` | Forme d'onde audio en temps réel, style oscilloscope XY |
| `terrain` | Survol de terrain 3D wireframe généré par le spectre FFT |
| `dna` | Double hélice 3D en rotation, pulsation sur les beats |
| `prism` | Dispersion de lumière arc-en-ciel à travers un prisme rotatif |

## Nouveaux effets

| Effet | Description |
|-------|-------------|
| `fireflies` | Lucioles flottantes avec clignotements asynchrones, synchronisation sur les beats |
| `rain` | Pluie diagonale avec éclaboussures au sol, densité modulée par l'énergie |
| `mandala` | Motif symétrique radial (6-8 axes) qui se construit progressivement, reset sur les drops |
| `pendulum` | Pendules harmoniques à phases décalées créant des motifs de vague |
| `spectrogram` | Waterfall spectrogramme défilant, coloré par la palette |
| `eq_terrain` | Barres d'égaliseur en perspective 3D isométrique avec profondeur temporelle |
| `mirror` | Symétrie kaléidoscopique configurable (2/4 axes), bords qui bougent au rythme |
| `vignette` | Assombrissement des bords pulsant avec les basses, spotlight central |
| `crystals` | Cristaux géométriques qui poussent/cassent sur les transients |


crée un effet qui dessine 4 barres horizontales qui font chacune 1/4 de la hauteur de l'écran, au début elles sont toutes invisibles, la 1ere et la 3eme s'étendent de la droite vers la gauche tandis que la 2eme et la 4eme s'étendent de la gauche vers la droite. Ensuite elles se rétractent.