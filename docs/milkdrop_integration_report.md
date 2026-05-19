# Rapport d'exploration : Intégration MilkDrop dans Jukebox

> Document de synthèse — branche `feat/milkdrop-exploration` — 2026-05-11.
> Sources primaires : `/tmp/milkdrop_research.md`, `/tmp/jukebox_exploration.md`.

---

## 1. Qu'est-ce que MilkDrop ?

### 1.1 Historique et contexte

- **Auteur** : Ryan Geiss.
- **Origine** : plug-in de visualisation musicale pour le lecteur **Winamp**, publié en 2001 par Nullsoft.
- **Dernier binaire officiel** : MilkDrop 2.0d (janvier 2008).
- **Dernier code source publié** : MilkDrop 2.25c (mai 2013), sur SourceForge (`milkdrop2`).
- **Activation Winamp** : `CTRL+K` (lancer), double-clic (plein écran), `ALT+K` (config).
- **Plateformes d'origine** : Windows 98 → Windows 7.
- **Fonctionnement général** : à partir du flux PCM injecté par Winamp, MilkDrop calcule en temps réel des features audio (FFT → `bass`/`mid`/`treb`) et exécute pour chaque frame deux passes de shaders programmables (warp + composite) dont les paramètres sont pilotés par un langage d'expressions intégré (EEL2). Le résultat est un visuel audio-réactif persistant entre les frames (le warp distord la frame précédente).

### 1.2 Architecture technique

- **API graphique** : **DirectX 9**.
- **Modèle de shader** : Pixel Shader Model **2.0** minimum (introduit dans MilkDrop 2).
- **Langage shader natif** : **HLSL** (DirectX High-Level Shader Language).
- **Moteur d'expressions** : **ns-eel2** (Nullsoft Expression Evaluation Library v2), langage de scripting custom assemblant du code machine via des fragments asm — très performant mais non portable.

#### Format de preset `.milk`

Fichier texte INI-like (ASCII) contenant une section `[preset00]` puis un header de paramètres et **7 blocs de code** :

1. **Preset Init Code** — exécuté une fois au chargement ; initialise les variables persistantes et les valeurs par défaut des `q1`-`q32`.
2. **Per-Frame Equations** — exécutées à chaque frame ; animent les paramètres en fonction du temps et de l'audio.
3. **Per-Vertex Equations** — exécutées sur les points de la grille de mesh ; permettent de faire varier les effets spatialement.
4. **Custom Wave / Shape Init & Per-Frame Code** — contrôle des waveforms / formes custom.
5. **Custom Wave Per-Point Code** — positionne individuellement chaque échantillon d'une waveform.
6. **Warp Shader** (PS 2.0+) — distord le canvas interne d'une frame à l'autre via les coordonnées UV ; l'output persiste.
7. **Composite Shader** (PS 2.0+) — rendu final à l'écran ; reçoit des UVs non distordus.

#### Variables intégrées

- **Lecture seule (entrée)** :
  - Temporelles : `time`, `fps`, `frame`, `progress`.
  - Audio (cœur de la réactivité) : `bass`, `mid`, `treb`, `bass_att`, `mid_att`, `treb_att` (valeur 1.0 = niveau normal ; < 0.7 = calme ; > 1.3 = forte présence).
  - Spatiales (per-vertex) : `x`, `y`, `rad`, `ang`.
  - Géométrie : `meshx`, `meshy`, `pixelsx`, `pixelsy`, `aspectx`, `aspecty`.
- **Écriture (modifiables)** : `dx`, `dy`, `cx`, `cy`, `sx`, `sy`, zoom, rotation, warp, propriétés des waveforms, bords, motion vectors, decay, brightness.
- **Passerelles** : `q1`-`q32` (preset init → per-frame → per-vertex → shaders), `t1`-`t8` (custom wave/shape).

#### Pipeline de rendu (2 passes par frame)

1. Per-frame equations → met à jour les variables globales.
2. Per-vertex equations sur la grille de mesh.
3. **Warp shader** lit la frame précédente avec distorsion UV → écrit un canvas interne (persistant).
4. **Composite shader** lit ce canvas → écrit le framebuffer final.

#### Audio-réactivité

- `bass`, `mid`, `treb` proviennent d'une **FFT** sur le PCM d'entrée, segmentée en 3 bandes.
- Variantes `_att` : valeurs lissées dans le temps.
- Pas de beat detection explicite dans le format — détection en pratique via surveillance des seuils de `bass`/`bass_att`.

### 1.3 Écosystème de presets

- **Cream of the Crop** (pack par défaut de projectM depuis 2022) : **9 795 presets** curatés par ISOSCELES à partir de ~52 000 presets bruts. 11 catégories principales (Dancer, Drawing, Fractal, Geometric, Hypnotic, Particles, Reaction, Sparkle, Supernova, Waveform, Transition) et 183 sous-catégories.
  - `https://github.com/projectM-visualizer/presets-cream-of-the-crop`
- **projectM Classic** : ~4 200 presets (pack historique jusqu'à projectM 3.1.12).
  - `https://github.com/projectM-visualizer/presets-projectm-classic`
- **milkdrop.co.uk** : dépôt communautaire historique de presets utilisateur.
- Qualité artistique reconnue : 25 ans de production communautaire, large diversité stylistique.
- **Licence MilkDrop d'origine** : **BSD 3-Clause** depuis l'ouverture du source en 2013.

---

## 2. Portages open-source disponibles

### 2.1 projectM

| Champ | Valeur |
|---|---|
| **Langage** | C++ (83.8 %), CMake (8.3 %), C (5.9 %) |
| **Licence** | **LGPL-2.1** (compatible shared lib dans une app closed-source) |
| **Version actuelle** | **4.1.6** (nov. 2025, à vérifier) |
| **Dépendances obligatoires** | C++ compiler, CMake, **OpenGL 3.0+ Core Profile** (ou GLES 3), GLM |
| **Dépendances optionnelles** | SDL2 ≥ 2.0.5 (test UI), LLVM (JIT expérimental), GLEW (Windows) |
| **Maturité** | Très mature, initié en 2003, maintenu activement |
| **Plateformes** | Linux, macOS, Windows, Android, Emscripten/WASM, Xbox, Windows Phone |
| **URL** | `https://github.com/projectM-visualizer/projectm` |
| **Site** | `https://projectm-visualizer.org/` |
| **C API** | Pure C depuis v4.0.0 (mars 2023), **ABI forward-compatible** sur toute la branche 4.x |
| **Limitations** | Contexte OpenGL doit être actif avant `projectm_create()` (sinon `NULL`). Suppression v4 : text overlays, key handler, settings struct, config file builtin. Playlist déplacé dans `projectM-playlist` (lib séparée optionnelle). |

**Caractéristique clé pour Jukebox** : la C API pure facilite le wrapping ctypes / CFFI / pybind11 sans toucher au C++.

### 2.2 projectm-eval

| Champ | Valeur |
|---|---|
| **Langage** | C |
| **Licence** | **MIT** |
| **Rôle** | Réimplémentation cross-platform et cross-arch de ns-eel2, **sans assembleur** (drop-in replacement portable) |
| **URL** | `https://github.com/projectM-visualizer/projectm-eval` |
| **Différence vs ns-eel2** | Rejette les erreurs de syntaxe alors que ns-eel2 les ignorait parfois — peut casser des presets très permissifs |

### 2.3 pym (bindings Python projectM)

| Champ | Valeur |
|---|---|
| **Langage** | Python + Cython |
| **Dépendances** | pysdl2, cython, numpy, PyOpenGL, PyOpenGL_accelerate, libprojectM installée séparément |
| **Maturité** | **Pre-alpha / proof of concept** — avertissement explicite dans le README, **7 commits** sur master |
| **PyPI** | **Non publié** ; build manuel (modifier `base_path` dans `setup.py`) |
| **Python** | 3.6+ (testé sous Ubuntu 17.10) |
| **URL** | `https://github.com/walshbp/pym` |
| **Limitations** | Non utilisable en production : non maintenu, pas de release, dépend de pysdl2 (introduit SDL dans le projet). |

### 2.4 butterchurn

| Champ | Valeur |
|---|---|
| **Langage** | JavaScript (83.9 %), HTML (10.6 %), TypeScript (5.4 %) |
| **Licence** | **MIT** |
| **Maturité** | Actif (205 commits master, 6 PR ouverts, CI active) |
| **Pré-requis runtime** | **WebGL 2** obligatoire |
| **Audio input** | **Web Audio API** (`audioNode`, micro ou source audio) |
| **Compatibilité presets** | Shaders HLSL **convertis en GLSL** via `milkdrop-shader-converter` |
| **URL** | `https://github.com/jberg/butterchurn` |
| **Outils associés** | `milkdrop-shader-converter`, `milkdrop-eel-parser`, `eel-wasm` |
| **Limitations pour Jukebox** | Nécessiterait `QWebEngineView` (~150 Mo) et routage audio vers Web Audio API. |

### 2.5 Autres portages pertinents

- **foo_vis_projectM** (foobar2000) — `https://github.com/djdron/foo_vis_projectM`
- **foo_vis_milk2** — portage MilkDrop 2 sous **DirectX 11** pour foobar2000 (`https://github.com/jecassis/foo_vis_milk2`)
- **MilkDrop3** (fork communautaire) — supporte n'importe quelle source audio, double-preset `.milk2`, beat detection-driven loading (`https://github.com/milkdrop2077/MilkDrop3`)
- **milkdrop2-musikcube** (clangen) — portage MilkDrop 2 dans musikcube (`https://github.com/clangen/milkdrop2-musikcube`)
- **projectm-android-tv** — `https://github.com/johnneerdael/projectm-android-tv`
- **Project-M Emscripten WASM** — `https://github.com/ford442/Project-M`
- **NestDrop V2** — VJ tool propriétaire basé MilkDrop (`https://nestimmersion.ca/nestdrop.php`)

---

## 3. Architecture actuelle de Jukebox (pertinente pour l'intégration)

### 3.1 Stack technologique

- **UI / threading** : `PySide6 >= 6.6.0` (QThread, signaux).
- **Audio** : `python-vlc >= 3.0.0`, `librosa >= 0.10.0,<0.11.0` (pin à cause d'un SIGSEGV `beat_track()` sur Apple Silicon en 0.11), `sounddevice` (capture micro live).
- **Analyse** : `numpy >= 1.24`, `scipy >= 1.11`, `numba < 0.63`.
- **Rendu vidéo** : `Pillow >= 10.0` (compositing PIL Image RGBA), `moderngl >= 5.8` (shaders GPU GLSL 330 core, extra `[video]` désactivé sur ARM64 d'après commentaires `pyproject.toml`), `opencv-python` (lecture vidéo de fond), `noise` (Perlin/Simplex, fallback pseudo-noise).
- **Encodage** : FFmpeg via `subprocess.Popen`, `libx264` CRF 23 + AAC 192k.
- **Live waveform UI** : `pyqtgraph` (non utilisé dans l'export).
- **Absent** : aucune dépendance MilkDrop / projectM / SDL / pygame / GLFW. Contexte OpenGL créé en mode standalone via `moderngl.create_standalone_context()`.

### 3.2 Pattern central : `BaseVisualLayer → PIL.Image → FrameRenderer`

Toutes les couches dérivent de `BaseVisualLayer(ABC)` (`plugins/video_exporter/layers/base.py` l.15-120) :

```python
class BaseVisualLayer(ABC):
    z_index: int = 0  # ordre de compositing (faible = arrière-plan)

    def __init__(self, width, height, fps, audio, sr, duration, **kwargs): ...
    def _precompute(self) -> None: ...           # opt., appelé en fin de __init__
    @abstractmethod
    def render(self, frame_idx: int, time_pos: float) -> Image.Image: ...
```

Compositing (`renderers/frame_renderer.py` l.253-278) : `Image.alpha_composite` séquentiel sur les couches triées par `z_index`, sortie `np.array(rgb, dtype=np.uint8)` shape `(H, W, 3)`. **Toute couche doit produire une PIL.Image RGBA finale par frame** — pas de surface OpenGL partagée, pas de FBO commun, pas de blending GPU custom.

Couches existantes (`frame_renderer.py` l.117-234) : `VideoBackgroundLayer`, `WaveformLayer`, `DynamicsLayer`, `VJingLayer` (z=4, 5174 lignes, ~45 effets), `TextLayer`, `IntroOverlayLayer`.

### 3.3 Système de shaders GPU (`plugins/video_exporter/layers/gpu_shaders.py`)

- **Version GLSL** : **330 core** (vertex + tous les fragments).
- **Vertex shader unique** : fullscreen quad via TRIANGLE_STRIP, 4 sommets `(-1,-1)…(1,1)`, UV `(0,0)…(1,1)`.
- **Uniforms audio standard** (tous les fragments) :
  ```glsl
  uniform float time;       // secondes
  uniform float energy;     // 0-1 (RMS global)
  uniform float bass;       // 0-1 (20-250 Hz)
  uniform float mid;        // 0-1 (250-4000 Hz)
  uniform vec2  resolution; // (width, height)
  uniform float intensity;  // 0-1
  uniform vec3  palette[5]; // 5 RGB 0-1
  ```
  `treble` est passé en Python mais non consommé par les 5 shaders actuels.
- **5 effets GPU** : `plasma`, `fractal` (Julia 64 iter), `metaballs` (5 boules), `wormhole`, `voronoi`. Code intégré en constantes Python.
- **Contexte ModernGL** :
  - `moderngl.create_standalone_context()` (offscreen, sans fenêtre).
  - `framebuffer` avec `texture((w, h), 4)` (RGBA).
  - Render path : set uniforms → `fbo.use()` → `clear(0,0,0,0)` → `vao.render(TRIANGLE_STRIP)` → `fbo.read(components=4)` → `Image.frombytes("RGBA", ...).transpose(FLIP_TOP_BOTTOM)`.
  - Round-trip GPU → CPU → PIL à chaque frame.
- **Thread-safety** :
  - Verrou global `_gpu_lock = threading.Lock()`.
  - **Contexte thread-affine** (seul le thread créateur peut l'utiliser, via `_creator_thread_id`).
  - Singleton `_gpu_renderer` recréé si dimensions changent.
- **Fallback CPU** : si `moderngl` absent (ARM64), chaque shader a une version Python pure dans `vjing_layer.py` (ex. `_render_plasma` l.2558).

### 3.4 VJingLayer (couche reine)

- **Z_index** : 4. Héritage `BaseVisualLayer`.
- **Données audio injectées en `_precompute`** : `audio` (N,), `energy`, `bass_energy`, `mid_energy`, `treble_energy` (`total_frames,`), `fft_data` (`total_frames × 32`), `beats` (indices de frame), `_beats_set` (lookup O(1)). FFT one-shot via `np.fft.rfft` puis masque fréquentiel + `irfft` + RMS par frame (volontairement sans `scipy.signal.filtfilt` à cause d'un SIGBUS macOS ARM en thread).
- **Contexte par frame** :
  ```python
  ctx = {"energy", "bass", "mid", "treble", "fft": NDArray(32), "is_beat": bool}
  ```
- **Pipeline en 3 passes** : generators (avec crossfade temporel), un seul post-processing actif par cycle (désactivé si `energy < 0.3 * max(energy)`), final-pass appliqué inconditionnellement (typ. `bloom`).
- **44 effets** (cf. `/tmp/jukebox_exploration.md` §C.8) : rythmiques, spectraux, particules, géométriques, naturels, classiques, GPU shaders (plasma/fractal/wormhole/voronoi/metaballs), post-processing (chromatic/pixelate/feedback/timestretch/glitch/scanlines/shockwave/halftone), final-pass (bloom).
- **GPU pre-rendering** (`prerender_gpu_frames`, l.652-724) : pattern clé pour contourner la non-thread-safety OpenGL. Avant les workers parallèles, le thread principal rend séquentiellement toutes les frames GPU dans un cache `dict[frame_idx, dict[effect_name, Image]]`. Après pre-render, `_gpu_renderer = None` libère le contexte.

### 3.5 Pipeline d'export et accès audio

- `VideoExportWorker` (QThread) orchestre : `librosa.load(sr=22050, mono=True)` → `FrameRenderer` → `prerender_gpu()` (si workers parallèles) → `FFmpegEncoder.start()` → `ThreadPoolExecutor(max_workers=min(cpu_count, 8))` → écriture séquentielle ordonnée → `encoder.finish()`.
- Constante `AUDIO_SAMPLE_RATE = 22050 Hz`. `samples_per_frame ≈ 735` à 30 fps.
- Mode live (`vj/vjing_playground.py`) : 22050 Hz, blocs 2048 (~93 ms), ring buffer 4 blocs, beat detection adaptatif, auto-gain, 32 bandes FFT identiques à l'export.

### 3.6 Points d'extension disponibles pour une `MilkDropLayer`

- **Fichier cible** : `plugins/video_exporter/layers/milkdrop_layer.py` (sibling de `vjing_layer.py`).
- **Enregistrement** : étendre `FrameRenderer._init_layers()` (l.117-234) avec un bloc `if layers_config.get("milkdrop", False):`, étendre `VideoExporterPlugin._synced_settings` (`plugin.py` l.135-150) et `get_settings_schema()` (l.193-283).
- **Z_index recommandé** : 4 (remplacement de `VJingLayer`, qui sera désactivée), ou 1 (couche de fond derrière VJ).
- **Interface obligatoire** : `render(frame_idx, time_pos) → PIL.Image RGBA (width × height)`, `__init__` acceptant `width, height, fps, audio, sr, duration`, **safe en multi-thread** (car appelée depuis `ThreadPoolExecutor`).
- **Modèle de pre-render** : copier exactement `VJingLayer.prerender_gpu_frames` (l.652-724) — un contexte OpenGL dans le thread principal, frames cachées en RAM, workers CPU font juste de l'`alpha_composite`.
- **Données audio à fournir à projectM** : PCM brut `self.audio[start:end]` (~735 samples par frame à 22050 Hz / 30 fps) via `projectm_pcm_add_float`, ou interpolation de `self.fft_data[frame_idx]` (32 bandes) vers 512/1024 bins si projectM l'exige. `is_beat` peut piloter des hard-cuts de presets.

---

## 4. Options d'intégration

### Option A : `MilkDropLayer` via projectM + ctypes

**Description** : utiliser `libprojectM.dylib` / `.so` / `.dll` via `ctypes.CDLL`, exploiter la C API stable de projectM v4 (ABI forward-compatible sur 4.x). projectM v4 expose `projectm_opengl_render_frame_fbo(handle, fbo_id)` qui rend directement dans le FBO ModernGL spécifié — la capture se fait ensuite via `fbo.read(components=4)` → `Image.frombytes("RGBA")`, identique au flow déjà en place dans `gpu_shaders.py` l.503-506. Outil possible : `ctypesgen` (`https://github.com/ctypesgen/ctypesgen`) pour auto-générer le wrapper depuis `projectM-4/projectM.h`.

> **Vérifié dans le source projectM v4** (`ProjectMCWrapper.cpp` l.344-354, `ProjectM.cpp`, `Framebuffer.cpp`) : projectM v4 n'crée PAS son propre contexte OpenGL — il utilise le contexte courant au moment de `projectm_create()`. Il expose deux fonctions : `projectm_opengl_render_frame(handle)` (rend vers FBO 0) et `projectm_opengl_render_frame_fbo(handle, fbo_id)` (rend vers le FBO spécifié). Il ne sauvegarde ni ne restaure le FBO précédent (`GL_FRAMEBUFFER_BINDING` absent de tout le code). Après l'appel, le `GL_DRAW_FRAMEBUFFER` reste bindé sur `fbo_id` — état correct pour le `fbo.read()` qui suit.

**Pattern d'intégration vérifié :**

```python
# Dans MilkDropLayer.prerender_gpu_frames()
lib.projectm_pcm_add_float(self._handle, pcm_chunk, len(pcm_chunk))
self._fbo.use()                                          # bind notre FBO ModernGL
lib.projectm_opengl_render_frame_fbo(self._handle, self._fbo.glo)
#                                                  ^^^^^^^^^^^^
#                          .glo = OpenGL object ID du FBO ModernGL (GLuint)
data = self._fbo.read(components=4)                      # lecture synchrone
img = Image.frombytes("RGBA", (self.width, self.height), data).transpose(FLIP_TOP_BOTTOM)
self._frame_cache[frame_idx] = img
```

**Avantages** :

- Compatibilité maximale avec les presets `.milk` originaux (warp + composite shaders, EEL2 via projectm-eval, FFT/beat detection intégrés).
- Rendu GPU natif via OpenGL, très performant (typ. > 60 fps temps réel).
- **9 795 presets** Cream of the Crop disponibles immédiatement (curatés par ISOSCELES).
- Licence **LGPL-2.1** compatible avec une app Python distribuée tant que projectM reste en shared lib (pas de link statique).
- C API pure depuis v4.0.0 → wrapping ctypes/CFFI/pybind11 sans toucher au C++.
- Pas de conflit de contexte OpenGL : projectM utilise le contexte ModernGL existant, `projectm_opengl_render_frame_fbo` rend directement dans notre FBO de capture.

**Inconvénients** :

- Compilation de projectM (C++ avec CMake) requise, ou `brew install projectm` sur macOS (à vérifier).
- Pas de `pip install` — dépendance système (libprojectM doit être installée hors `uv sync`).
- Empreinte mémoire du pre-render : 1080p × 30 fps × 30 s ≈ **7.5 GB en RAM** sans cache disque.
- projectM ne restaure pas le `GL_DRAW_FRAMEBUFFER` après rendu → rebind explicite nécessaire avant le prochain appel ModernGL (une ligne : `self._fbo.use()` au début du cycle suivant, déjà prévu par l'architecture).

**Faisabilité** : **Moyenne** (2-3 semaines).

---

### Option B : Transpilation `.milk` → GLSL 330 (ModernGL natif)

**Description** : parser les fichiers `.milk`, extraire les sections warp shader et composite shader, transpiler la syntaxe HLSL-like vers GLSL 330 (s'inspirer de `milkdrop-shader-converter` de butterchurn), exécuter dans l'infrastructure ModernGL existante. Pour les équations EEL2 (preset init, per-frame, per-vertex), implémenter un interpréteur Python ou réutiliser `eel-wasm` via un wrapper.

**Avantages** :

- Zéro dépendance C++ externe — installation 100 % `pip` / `uv sync`.
- Intégration parfaite avec l'infrastructure ModernGL existante (`gpu_shaders.py` partage déjà GLSL 330 core, uniforms audio standard `bass`/`mid`/`energy`).
- Contrôle total du pipeline (debugging, instrumentation, mix avec d'autres couches Jukebox).
- Compatible ARM64 sans recompilation native.

**Inconvénients** :

- **Compatibilité partielle seulement** : `milkdrop-shader-converter` (butterchurn) prouve la faisabilité mais a nécessité un effort conséquent et reste imparfait sur les presets exotiques.
- Équations per-frame / per-vertex en EEL2 (syntaxe C-like avec `if(cond, then, else)` ternaire) nécessitent un interpréteur custom ou un wrapper sur `eel-wasm` (dépendance WASM runtime).
- Effort significatif pour gérer le warp persistant frame-to-frame (FBO ping-pong) — réalisable mais coûteux.
- Risque de divergence visuelle avec les versions de référence (perte de fidélité artistique).

**Faisabilité** : **Faible à moyenne** (fragile, 4-6 semaines pour un sous-ensemble fonctionnel, plusieurs mois pour parité complète).

---

### Option C : projectM en subprocess headless (EGL / OSMesa)

**Description** : lancer projectM dans un processus séparé avec rendu headless (EGL sans display sur Linux, OSMesa en software rendering portable), capturer les frames via shared memory (`multiprocessing.shared_memory`) ou pipe Unix, les injecter dans le pipeline Jukebox comme `PIL.Image`. Synchronisation par timestamps.

**Avantages** :

- Isolation complète : aucun conflit de contexte OpenGL avec ModernGL.
- Presets originaux 100 % compatibles (projectM standard).
- Crash de projectM n'impacte pas le worker Jukebox.

**Inconvénients** :

- Latence IPC (shared memory ou pipe) + sérialisation des frames RGB(A).
- Complexité de setup headless OpenGL : EGL non disponible sur macOS, OSMesa désactive l'accélération GPU (rendu CPU lent).
- Synchronisation audio complexe : injecter le PCM dans le subprocess frame par frame avec contrôle de cadence.
- Surface d'attaque élargie (lifecycle process, gestion des erreurs IPC, signaux POSIX).

**Faisabilité** : **Faible** (architecture complexe, peu adaptée à macOS).

---

## 5. Recommandation

### Option recommandée : Option A (projectM + ctypes), approche progressive

**Justification dans le contexte Jukebox** :

- L'infrastructure ModernGL existante utilise déjà **GLSL 330 core avec offscreen rendering** (`create_standalone_context` + FBO/texture RGBA). Le partage ou la sérialisation de contexte OpenGL avec projectM est réalisable via le verrou `_gpu_lock` déjà en place.
- Le pattern `BaseVisualLayer → PIL.Image RGBA → FrameRenderer.alpha_composite` est parfaitement adapté : `projectm_opengl_render_frame_fbo(handle, fbo.glo)` rend dans notre FBO ModernGL, `fbo.read(components=4)` → `Image.frombytes("RGBA", ...).transpose(FLIP_TOP_BOTTOM)` — flux identique à `gpu_shaders.py` l.503-506, vérifié dans le source projectM v4.
- Les uniforms audio Jukebox (`bass`, `mid`, `treble`, `energy`, `fft_data`, `_beats_set`) correspondent exactement aux entrées PCM/FFT attendues par projectM (`projectm_pcm_add_float` + détection interne FFT/beat).
- **Licence LGPL-2.1** : compatible avec Jukebox tant que libprojectM reste en shared lib (linkage dynamique via ctypes).
- Le **modèle pre-render** (`prerender_gpu_frames` de `VJingLayer`, l.652-724) est directement transposable : un seul contexte OpenGL dans le thread principal, frames cachées en RAM, workers `ThreadPoolExecutor` font uniquement de l'`alpha_composite`. C'est exactement ce que projectM exige (state-machine GLSL non thread-safe).
- C API pure et stable depuis v4.0.0 → ctypes minimal sans recompilation à chaque version mineure.

### Plan d'implémentation progressif

1. **Phase 0 — Build / installation projectM sur macOS**
   - Tester `brew install projectm` (vérifier disponibilité et version 4.1.x).
   - Fallback : compilation depuis source (`cmake`, `make`, dépendances GLM + OpenGL system).
   - Vérifier ABI : `nm -D libprojectM.dylib | grep projectm_` pour confirmer la C API.

2. **Phase 1 — Prototype ctypes headless minimal**
   - Wrapper `ctypes.CDLL` sur les fonctions clés : `projectm_create`, `projectm_destroy`, `projectm_load_preset_file`, `projectm_pcm_add_float`, `projectm_opengl_render_frame_fbo`, `projectm_set_window_size`.
   - Utiliser le contexte ModernGL standalone existant (`create_standalone_context()`) — projectM s'y attachera via `projectm_create()` appelé après.
   - Charger un preset Cream of the Crop, rendre 1 frame via `projectm_opengl_render_frame_fbo(handle, fbo.glo)`, capturer via `fbo.read()`, dumper en PNG.

3. **Phase 2 — `MilkDropLayer(BaseVisualLayer)` intégrée dans `FrameRenderer`**
   - Implémenter `_precompute` (init projectM lazy) et `prerender_gpu_frames(self) -> int`.
   - Cache `_frame_cache: dict[int, Image.Image]`. `render(frame_idx, time_pos)` lookup cache ou fallback transparent.
   - Injection audio : `samples_per_frame = sr // fps` (~735 à 22050 Hz / 30 fps), push via `projectm_pcm_add_float` avant chaque frame.
   - Sérialisation via `_gpu_lock` de `gpu_shaders.py` : projectM et VJingLayer partagent le même contexte OpenGL, `prerender_gpu_frames` de chaque couche est appelé séquentiellement dans le thread principal — aucun conflit possible.

4. **Phase 3 — UI de sélection de presets**
   - Étendre `VideoExporterPlugin._synced_settings` (`plugin.py` l.135-150) avec `SyncedSetting("milkdrop_enabled", bool)`, `SyncedSetting("milkdrop_preset_dir", str)`, `SyncedSetting("milkdrop_preset_duration", float, default=8.0)`, `SyncedSetting("milkdrop_hard_cut_on_beat", bool, default=True)`.
   - Étendre `get_settings_schema()` (l.193-283) pour exposer dans `conf_manager`.
   - Picker de répertoire de presets dans le widget d'export.

5. **Phase 4 — Mode live dans `vjing_playground`**
   - `MicrophoneSource` (22050 Hz, blocs 2048) → push PCM vers projectM frame par frame.
   - Live `MilkDropLayer` analogue à `LiveVJingLayer` (skip pré-calcul lourd).
   - Excellent terrain de jeu pour valider l'intégration avant de toucher au pipeline d'export.

---

## 6. Risques et dépendances

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| **Conflit contexte OpenGL projectM ↔ ModernGL** | Faible | Faible | **Vérifié dans le source v4** : projectM utilise le contexte courant (pas le sien propre) et expose `projectm_opengl_render_frame_fbo(handle, fbo_id)` pour rendre dans le FBO ModernGL. `prerender_gpu_frames` est séquentiel dans le thread principal → aucun conflit possible. Seul point d'attention : projectM ne restaure pas le `GL_DRAW_FRAMEBUFFER` → rebind `fbo.use()` nécessaire avant le prochain rendu ModernGL (une ligne). |
| **Compilation projectM complexe sur macOS** (CMake, dépendances OpenGL system) | Moyenne | Moyen | Tester `brew install projectm` en priorité ; fallback compilation depuis source documentée dans `https://github.com/projectM-visualizer/projectm/wiki/Building-libprojectM` |
| **pym (bindings Python) trop immature** | Élevée | Faible | Ne pas utiliser pym ; ctypes direct sur libprojectM (C API v4 stable) ou ctypesgen pour auto-générer |
| **Performance insuffisante pour export 30 fps** | Faible | Élevé | Profiler le pre-render (typ. > 60 fps temps réel attendu sur GPU décent) ; envisager résolution réduite (720p) pour presets lourds ; cache disque si export > 60 s |
| **Compatibilité presets MilkDrop 1 vs 2** | Moyenne | Moyen | projectM gère les deux formats ; documenter quelles features sont gérées (warp + composite shaders, custom waves/shapes) |
| **Licence LGPL-2.1 vs distribution Jukebox** | Faible | Faible | Compatible en linkage dynamique (shared lib via ctypes) ; documenter dans le README de Jukebox |
| **Empreinte mémoire pre-render** (1080p × 30 fps × 30 s ≈ 7.5 GB RAM) | Moyenne | Moyen | Cache disque pour exports longs ; mode streaming (rendre par chunk N frames, vider le cache) ; limiter à 5-15 s pour loops |
| **ARM64 désactivé pour moderngl** (commentaires `pyproject.toml` l.38-39) | Moyenne | Moyen | Vérifier que `moderngl` fonctionne sur Apple Silicon (le fallback CPU est déjà actif en pratique) ; sinon projectM doit avoir son propre contexte OpenGL system |
| **Crash projectM (SIGSEGV) en thread Python** | Moyenne | Élevé | Confiner projectM au thread principal du worker (pattern `prerender_gpu_frames`) ; jamais appeler depuis `ThreadPoolExecutor` |
| **EEL2 vs projectm-eval** (rejet d'erreurs de syntaxe) | Faible | Faible | projectm-eval intégré dans projectM v4 ; documenter les presets cassés et les exclure du pack par défaut |

---

## 7. Ressources

### Documentation MilkDrop

- Site officiel MilkDrop : `https://www.geisswerks.com/milkdrop/`
- Guide d'authoring presets : `https://www.geisswerks.com/milkdrop/milkdrop_preset_authoring.html`
- Wikipedia MilkDrop : `https://en.wikipedia.org/wiki/MilkDrop`
- Sources Nullsoft (BSD 3-Clause) : `https://sourceforge.net/projects/milkdrop2/`

### projectM

- Repo principal : `https://github.com/projectM-visualizer/projectm`
- Site : `https://projectm-visualizer.org/`
- Release v4.0.0 (mars 2023, C API) : `https://github.com/projectM-visualizer/projectm/releases/tag/v4.0.0`
- Release v4.1.6 (nov. 2025) : `https://github.com/projectM-visualizer/projectm/releases/tag/v4.1.6`
- Wiki Building libprojectM : `https://github.com/projectM-visualizer/projectm/wiki/Building-libprojectM`
- projectm-eval (MIT) : `https://github.com/projectM-visualizer/projectm-eval`
- SourceForge legacy : `https://sourceforge.net/projects/projectm/`

### Bindings Python et alternatives

- pym (pre-alpha, à éviter) : `https://github.com/walshbp/pym`
- ctypesgen (auto-wrap C API) : `https://github.com/ctypesgen/ctypesgen`

### butterchurn / WebGL

- butterchurn (MIT) : `https://github.com/jberg/butterchurn`
- milkdrop-shader-converter : `https://github.com/jberg/milkdrop-shader-converter`
- milkdrop-eel-parser : `https://github.com/jberg/milkdrop-eel-parser`
- eel-wasm : `https://github.com/captbaritone/eel-wasm`

### Packs de presets

- Cream of the Crop (9 795 presets, défaut projectM 2022+) : `https://github.com/projectM-visualizer/presets-cream-of-the-crop`
- projectM Classic (~4 200 presets) : `https://github.com/projectM-visualizer/presets-projectm-classic`

### Forks et portages connexes

- foo_vis_projectM (foobar2000) : `https://github.com/djdron/foo_vis_projectM`
- foo_vis_milk2 (DirectX 11) : `https://github.com/jecassis/foo_vis_milk2`
- MilkDrop3 (fork communautaire) : `https://github.com/milkdrop2077/MilkDrop3`
- milkdrop2-musikcube : `https://github.com/clangen/milkdrop2-musikcube`
- projectm-android-tv : `https://github.com/johnneerdael/projectm-android-tv`
- Project-M Emscripten WASM : `https://github.com/ford442/Project-M`

### Article de contexte

- LWN sur l'ouverture du source MilkDrop : `https://lwn.net/Articles/750152/`

### Code Jukebox de référence

| Aspect | Chemin | Lignes |
|---|---|---|
| Interface couche | `plugins/video_exporter/layers/base.py` | 1-121 |
| Compositing | `plugins/video_exporter/renderers/frame_renderer.py` | 117-278 |
| Shaders GPU | `plugins/video_exporter/layers/gpu_shaders.py` | 1-550 |
| VJ effets (core) | `plugins/video_exporter/layers/vjing_layer.py` | 276-1238 |
| VJ pre-render GPU | `plugins/video_exporter/layers/vjing_layer.py` | 652-766 |
| Worker export | `plugins/video_exporter/export_worker.py` | 49-305 |
| FFmpeg encoder | `plugins/video_exporter/renderers/ffmpeg_encoder.py` | 91-285 |
| Plugin video_exporter | `plugins/video_exporter/plugin.py` | 1-283 |
| VJ playground (live) | `vj/vjing_playground.py` | 115-274 |
| Dépendances | `pyproject.toml` | 9-40 |

---

*Rapport généré le 2026-05-11 — branche `feat/milkdrop-exploration`.*
