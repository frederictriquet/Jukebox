"""Couche de visualisation MilkDrop via libprojectM v4."""

from __future__ import annotations

import ctypes
import logging
import random
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

try:
    import moderngl  # type: ignore[import-untyped]
except ImportError:
    moderngl = None  # type: ignore[assignment]

from plugins.video_exporter.layers.base import BaseVisualLayer
from plugins.video_exporter.layers.gpu_shaders import _gpu_lock, get_shared_gl_context

# Chemins de recherche de la bibliothèque libprojectM (macOS et Linux)
_LIBPROJECTM_SEARCH_PATHS = [
    # macOS — convention avec tiret (cmake install depuis les sources)
    "/usr/local/lib/libprojectM-4.dylib",
    "/usr/local/lib/libprojectM-4.4.dylib",
    "/opt/homebrew/lib/libprojectM-4.dylib",
    "/opt/homebrew/lib/libprojectM-4.4.dylib",
    # macOS — convention avec point (anciens packages)
    "/usr/local/lib/libprojectM.4.dylib",
    "/usr/local/lib/libprojectM.dylib",
    "/opt/homebrew/lib/libprojectM.4.dylib",
    "/opt/homebrew/lib/libprojectM.dylib",
    # Linux
    "/usr/lib/libprojectM.so.4",
    "/usr/local/lib/libprojectM.so.4",
    "libprojectM.so.4",
]

logger = logging.getLogger(__name__)


class MilkDropLayer(BaseVisualLayer):
    """Couche de visualisation MilkDrop via projectM v4."""

    # Z-index sous VJingLayer (z=4)
    z_index: int = 3

    def __init__(
        self,
        width: int,
        height: int,
        fps: int,
        audio: Any,
        sr: int,
        duration: float,
        **kwargs: Any,
    ) -> None:
        super().__init__(width, height, fps, audio, sr, duration, **kwargs)

        self._preset_path: str = kwargs.get("preset_path", "")
        self._preset_duration: float = float(kwargs.get("preset_duration", 8.0))
        self._hard_cut_on_beat: bool = bool(kwargs.get("hard_cut_on_beat", True))
        self._rng_seed: int = int(kwargs.get("rng_seed", 0))

        # Cache des frames pré-rendues (frame_idx → Image RGBA)
        self._frame_cache: dict[int, Image.Image] = {}

        # Ressources OpenGL / projectM (initialisées à la demande via _init_gl)
        self._handle: ctypes.c_void_p | None = None
        self._lib: ctypes.CDLL | None = None
        self._fbo: object | None = None
        self._ctx: object | None = None
        self._presets: list[str] = []
        # État de rotation de preset pour le rendu à la demande
        self._live_preset_idx: int = 0
        self._live_frames_since_cut: int = 0

        self._lib = self._load_library()
        self._setup_ctypes()

    @staticmethod
    def _load_library() -> ctypes.CDLL:
        """Charge libprojectM depuis les chemins connus.

        Raises:
            RuntimeError: bibliothèque introuvable ou API v4 absente.
        """
        for path in _LIBPROJECTM_SEARCH_PATHS:
            try:
                lib = ctypes.CDLL(path)
            except OSError:
                continue

            fn = lib.projectm_opengl_render_frame_fbo
            fn_addr = ctypes.cast(fn, ctypes.c_void_p).value
            if fn_addr is None or fn_addr == 0:
                raise RuntimeError(
                    f"libprojectM trouvée à {path} mais C API v4 absente "
                    "(projectM v3 détecté — seul v4 expose une C API). "
                    "Compiler v4 : git clone https://github.com/projectM-visualizer/projectm && "
                    "cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build && "
                    "cmake --install build"
                )

            logger.info("[MilkDropLayer] libprojectM v4 chargée depuis : %s", path)
            return lib

        raise RuntimeError(
            "libprojectM introuvable dans les chemins connus. "
            "Compiler projectM v4 depuis : https://github.com/projectM-visualizer/projectm"
        )

    def _setup_ctypes(self) -> None:
        """Définit les signatures ctypes des fonctions projectM utilisées."""
        if self._lib is None:
            raise RuntimeError("libprojectM non chargée")

        self._lib.projectm_create.restype = ctypes.c_void_p
        self._lib.projectm_create.argtypes = [ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint]

        self._lib.projectm_destroy.restype = None
        self._lib.projectm_destroy.argtypes = [ctypes.c_void_p]

        self._lib.projectm_load_preset_file.restype = None
        self._lib.projectm_load_preset_file.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_bool,
        ]

        # channels : 1 = PROJECTM_MONO, 2 = PROJECTM_STEREO
        self._lib.projectm_pcm_add_float.restype = None
        self._lib.projectm_pcm_add_float.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_uint,
            ctypes.c_int,
        ]

        self._lib.projectm_opengl_render_frame_fbo.restype = None
        self._lib.projectm_opengl_render_frame_fbo.argtypes = [ctypes.c_void_p, ctypes.c_uint]

        self._lib.projectm_set_window_size.restype = None
        self._lib.projectm_set_window_size.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_uint,
        ]

        self._lib.projectm_get_preset_duration.restype = ctypes.c_double
        self._lib.projectm_get_preset_duration.argtypes = [ctypes.c_void_p]

    def _collect_presets(self) -> list[str]:
        """Collecte la liste des fichiers .milk disponibles."""
        if not self._preset_path:
            logger.warning("[MilkDropLayer] Aucun chemin de preset configuré (preset_path vide)")
            return []

        preset_path = Path(self._preset_path)

        if not preset_path.exists():
            logger.warning("[MilkDropLayer] Chemin de preset introuvable : %s", self._preset_path)
            return []

        if preset_path.is_file() and preset_path.suffix.lower() == ".milk":
            return [str(preset_path)]

        if preset_path.is_dir():
            presets = sorted(str(p) for p in preset_path.rglob("*.milk"))
            if not presets:
                logger.warning(
                    "[MilkDropLayer] Aucun fichier .milk trouvé dans : %s", self._preset_path
                )
                return presets
            # Mélange déterministe par seed : chaque track voit un ordre différent
            rng = random.Random(self._rng_seed)  # noqa: S311
            rng.shuffle(presets)
            logger.info("[MilkDropLayer] %d presets mélangés (seed=%d)", len(presets), self._rng_seed)
            return presets

        logger.warning(
            "[MilkDropLayer] preset_path n'est ni un fichier .milk ni un répertoire : %s",
            self._preset_path,
        )
        return []

    def _precompute_beats(self) -> list[int]:
        """Calcule les indices de frames correspondant aux beats."""
        try:
            import librosa  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("[MilkDropLayer] librosa absent — détection de beats désactivée")
            return []

        hop_length = 512  # valeur par défaut de librosa.beat.beat_track
        samples_per_frame = max(1, self.sr // self.fps)
        # beat_track retourne des indices en unités de hop_length, pas en samples
        _, beat_hop_frames = librosa.beat.beat_track(y=self.audio, sr=self.sr, hop_length=hop_length)
        return [int((int(h) * hop_length) // samples_per_frame) for h in beat_hop_frames]

    def _init_gl(self) -> None:
        """Crée (ou recrée) le contexte OpenGL, FBO et handle projectM.

        Doit être appelée depuis l'intérieur de _gpu_lock.
        Détruit les ressources précédentes si elles existent.
        """
        if self._handle is not None and self._lib is not None:
            self._lib.projectm_destroy(self._handle)  # type: ignore[union-attr]
            self._handle = None
        if self._fbo is not None:
            self._fbo.release()  # type: ignore[union-attr]
            self._fbo = None

        self._presets = self._collect_presets()
        self._ctx = get_shared_gl_context()
        
        # Création texture couleur
        texture = self._ctx.texture((self.width, self.height), 4)  # type: ignore[union-attr]
        # Ajout d'un depth buffer : certains presets MilkDrop complexes en ont besoin
        depth_attachment = self._ctx.depth_renderbuffer((self.width, self.height))  # type: ignore[union-attr]

        self._fbo = self._ctx.framebuffer(  # type: ignore[union-attr]
            color_attachments=[texture],
            depth_attachment=depth_attachment
        )
        
        self._handle = self._lib.projectm_create(None, self.width, self.height)  # type: ignore[union-attr]
        self._lib.projectm_set_window_size(self._handle, self.width, self.height)  # type: ignore[union-attr]
        
        if self._presets:
            logger.info("[MilkDropLayer] Chargement du premier preset : %s", self._presets[0])
            self._lib.projectm_load_preset_file(  # type: ignore[union-attr]
                self._handle, self._presets[0].encode(), False
            )
            
        self._fbo.use()  # type: ignore[union-attr]
        self._ctx.clear(0.0, 0.0, 0.0, 1.0)  # type: ignore[union-attr]
        self._live_preset_idx = 0
        self._live_frames_since_cut = 0

    def _ensure_gl_ready(self) -> None:
        """Initialise le contexte GL si pas encore fait (idempotent)."""
        if self._handle is not None:
            return
        with _gpu_lock:
            if self._handle is not None:
                return
            self._init_gl()

    def _render_one_frame(self, frame_idx: int) -> Image.Image:
        """Rend un seul frame MilkDrop et retourne l'image RGBA.

        Doit être appelée depuis un contexte qui détient déjà _gpu_lock.

        Args:
            frame_idx: Index du frame pour synchroniser l'audio.

        Returns:
            Image PIL RGBA correspondant au frame rendu.
        """
        samples_per_frame = max(1, self.sr // self.fps)
        start = frame_idx * samples_per_frame
        end = min(start + samples_per_frame, len(self.audio))
        pcm = np.zeros(samples_per_frame, dtype=np.float32)
        if end > start:
            pcm[: end - start] = self.audio[start:end].astype(np.float32)
        pcm_ptr = pcm.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        self._lib.projectm_pcm_add_float(self._handle, pcm_ptr, samples_per_frame, 1)  # type: ignore[union-attr]
        self._fbo.use()  # type: ignore[union-attr]
        self._lib.projectm_opengl_render_frame_fbo(  # type: ignore[union-attr]
            self._handle, ctypes.c_uint(self._fbo.glo)  # type: ignore[union-attr]
        )
        raw = self._fbo.read(components=4, dtype="f1")  # type: ignore[union-attr]
        data = np.frombuffer(raw, dtype=np.uint8).reshape((self.height, self.width, 4))
        # OpenGL origine bas-gauche → retournement vertical
        return Image.fromarray(np.flipud(data), "RGBA")

    def _do_warmup(self) -> None:
        """Exécute la boucle de chauffe projectM (sans prendre _gpu_lock).

        Doit être appelée depuis un contexte qui détient déjà _gpu_lock.
        Initialise l'état interne de projectM avec le début de l'audio pour que
        la visualisation soit déjà vivante dès le premier frame rendu.
        """
        if self._lib is None or self._handle is None or self._fbo is None:
            return

        samples_per_frame = max(1, self.sr // self.fps)
        # Warmup intensif pour forcer la convergence visuelle.
        # On passe à 2500 frames pour être absolument sûr.
        warmup_count = 2500
        warmup_audio_len = min(len(self.audio), int(3.0 * self.sr))
        if warmup_audio_len == 0:
            logger.warning("[MilkDropLayer] Audio de warmup vide !")
            return

        # Boost audio pour exciter les shaders durant la chauffe
        warmup_audio = self.audio[:warmup_audio_len].copy()
        max_amp = np.max(np.abs(warmup_audio))
        if max_amp > 0:
            warmup_audio = np.clip(warmup_audio * (2.0 / max_amp), -1.0, 1.0)

        logger.info("[MilkDropLayer] Démarrage chauffe intensive (%d frames, max_amp=%.4f)...", warmup_count, max_amp)

        frames_per_preset = max(1, int(self._preset_duration * self.fps))

        for wi in range(warmup_count):
            # Cycle de preset : avance comme le ferait render() en live
            if self._presets and wi > 0 and wi % frames_per_preset == 0:
                self._live_preset_idx = (self._live_preset_idx + 1) % len(self._presets)
                self._lib.projectm_load_preset_file(  # type: ignore[union-attr]
                    self._handle, self._presets[self._live_preset_idx].encode(), True
                )
                self._live_frames_since_cut = 0

            # Bouclage sur les 3 premières secondes
            w_start = (wi * samples_per_frame) % warmup_audio_len
            w_end = min(w_start + samples_per_frame, warmup_audio_len)

            pcm_w = np.zeros(samples_per_frame, dtype=np.float32)
            if w_end > w_start:
                pcm_w[: w_end - w_start] = warmup_audio[w_start:w_end].astype(np.float32)

            pcm_w_ptr = pcm_w.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            self._lib.projectm_pcm_add_float(self._handle, pcm_w_ptr, samples_per_frame, 1)  # type: ignore[union-attr]

            self._fbo.use()  # type: ignore[union-attr]
            self._lib.projectm_opengl_render_frame_fbo(  # type: ignore[union-attr]
                self._handle, ctypes.c_uint(self._fbo.glo)  # type: ignore[union-attr]
            )

            self._live_frames_since_cut += 1

            # Flush périodique
            if wi % 100 == 0:
                self._fbo.read(components=1)  # type: ignore[union-attr]

        if self._ctx:
            self._ctx.finish()  # type: ignore[union-attr]
            
        logger.info("[MilkDropLayer] Chauffe terminée")

    def warmup_gpu_frames(self) -> None:
        """Chauffe projectM sans pré-calculer le cache complet.

        À appeler depuis le thread principal avant la preview pour que les
        effets MilkDrop soient visibles dès le premier frame affiché.
        """
        if moderngl is None:
            raise RuntimeError("moderngl absent — installer avec : uv sync --extra video")

        with _gpu_lock:
            if self._handle is None:
                self._init_gl()
            self._do_warmup()
        logger.info("[MilkDropLayer] Warmup preview terminé")

    def prerender_gpu_frames(self) -> int:
        """Pré-rend toutes les frames MilkDrop et les stocke dans le cache.

        Réservé à l'export : appeler depuis le thread principal avant le ThreadPoolExecutor.
        Pour le preview, ne pas appeler — render() utilise le rendu à la demande.

        Returns:
            Nombre de frames pré-rendues et mises en cache.
        """
        if moderngl is None:
            raise RuntimeError("moderngl absent — installer avec : uv sync --extra video")

        total_frames = int(self.duration * self.fps)
        beats_set = set(self._precompute_beats())

        with _gpu_lock:
            # Réinitialisation propre pour garantir un rendu déterministe
            self._init_gl()

            # Pré-chauffe via la méthode partagée (sans re-prendre le lock)
            # _do_warmup() met à jour _live_preset_idx et _live_frames_since_cut
            self._do_warmup()

            # Continuer depuis l'état laissé par le warmup plutôt que de
            # repartir du preset 0 (qui est dans ! Transition/)
            preset_idx = self._live_preset_idx
            frames_since_cut = self._live_frames_since_cut

            # Hard cut autorisé seulement après 50% de la durée de preset minimum
            min_frames_hard_cut = int(self._preset_duration * self.fps * 0.5)

            for frame_idx in range(total_frames):
                if (
                    self._presets
                    and self._hard_cut_on_beat
                    and frame_idx in beats_set
                    and frames_since_cut >= min_frames_hard_cut
                ):
                    preset_idx = (preset_idx + 1) % len(self._presets)
                    self._lib.projectm_load_preset_file(  # type: ignore[union-attr]
                        self._handle, self._presets[preset_idx].encode(), False
                    )
                    frames_since_cut = 0
                elif self._presets and frames_since_cut >= int(self._preset_duration * self.fps):
                    preset_idx = (preset_idx + 1) % len(self._presets)
                    self._lib.projectm_load_preset_file(  # type: ignore[union-attr]
                        self._handle, self._presets[preset_idx].encode(), True
                    )
                    frames_since_cut = 0

                self._frame_cache[frame_idx] = self._render_one_frame(frame_idx)
                frames_since_cut += 1

                if frame_idx > 0 and frame_idx % self.fps == 0:
                    logger.debug(
                        "[MilkDropLayer] Pré-rendu : %d/%d frames", frame_idx, total_frames
                    )

        logger.info(
            "[MilkDropLayer] Pré-rendu terminé : %d frames mises en cache", len(self._frame_cache)
        )
        return len(self._frame_cache)

    def render(self, frame_idx: int, time_pos: float) -> Image.Image:  # noqa: ARG002
        """Retourne la frame du cache, ou rend à la demande pour le preview.

        Args:
            frame_idx: Index de la frame (0 à total_frames-1).
            time_pos: Position temporelle en secondes.

        Returns:
            Image PIL en mode RGBA.
        """
        cached = self._frame_cache.get(frame_idx)
        if cached is not None:
            return cached

        # Rendu à la demande — mode preview (pas de pré-rendu)
        if self._handle is None:
            self._ensure_gl_ready()

        with _gpu_lock:
            # Rotation de preset par durée (fondu)
            if self._presets and self._live_frames_since_cut >= int(
                self._preset_duration * self.fps
            ):
                self._live_preset_idx = (self._live_preset_idx + 1) % len(self._presets)
                self._lib.projectm_load_preset_file(  # type: ignore[union-attr]
                    self._handle, self._presets[self._live_preset_idx].encode(), True
                )
                self._live_frames_since_cut = 0

            img = self._render_one_frame(frame_idx)

        self._live_frames_since_cut += 1
        return img

    def shutdown(self) -> None:
        """Libère les ressources projectM."""
        with _gpu_lock:
            if self._handle is not None and self._lib is not None:
                self._lib.projectm_destroy(self._handle)  # type: ignore[union-attr]
                self._handle = None
            if self._fbo is not None:
                self._fbo.release()  # type: ignore[union-attr]
                self._fbo = None
        logger.info("[MilkDropLayer] shutdown")
