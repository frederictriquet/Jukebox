"""MilkDrop visualization layer via libprojectM v4."""

from __future__ import annotations

import ctypes
import logging
import random
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

try:
    import moderngl
except ImportError:
    moderngl = None  # type: ignore[assignment]

from plugins.video_exporter.layers.base import BaseVisualLayer
from plugins.video_exporter.layers.gpu_shaders import (
    _gpu_lock,
    _is_gl_context_valid,
    get_shared_gl_context,
)

# Search paths for the libprojectM library (macOS and Linux)
_LIBPROJECTM_SEARCH_PATHS = [
    # macOS — dash convention (cmake install from sources)
    "/usr/local/lib/libprojectM-4.dylib",
    "/usr/local/lib/libprojectM-4.4.dylib",
    "/opt/homebrew/lib/libprojectM-4.dylib",
    "/opt/homebrew/lib/libprojectM-4.4.dylib",
    # macOS — dot convention (older packages)
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
    """MilkDrop visualization layer via projectM v4."""

    # Z-index below VJingLayer (z=4)
    z_index: int = 3

    # Many presets in large public packs (e.g. "cream of the crop") include
    # intentional fade-to-black or decay-to-black cycles, designed to be seen
    # for a few seconds within minutes of continuous play. On a short export
    # clip that same cycle can dominate the whole clip. Mean pixel value (0-255)
    # below which a frame counts as "dark".
    _DARK_BRIGHTNESS_THRESHOLD: float = 8.0
    # How long a preset is allowed to stay dark before it's force-cut early.
    _DARK_STREAK_SECONDS: float = 1.5

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
        self._texture_path: str = kwargs.get("texture_path", "")
        self._preset_duration: float = float(kwargs.get("preset_duration", 8.0))
        self._hard_cut_on_beat: bool = bool(kwargs.get("hard_cut_on_beat", True))
        self._rng_seed: int = int(kwargs.get("rng_seed", 0))

        # Cache of pre-rendered frames (frame_idx → RGBA Image)
        self._frame_cache: dict[int, Image.Image] = {}

        # OpenGL / projectM resources (initialized on demand via _init_gl)
        self._handle: ctypes.c_void_p | None = None
        self._lib: ctypes.CDLL | None = None
        self._fbo: object | None = None
        self._ctx: object | None = None
        self._presets: list[str] = []
        # Not all libprojectM v4 builds expose this (added in a later minor
        # version); set by _setup_ctypes(), checked before use in _init_gl().
        self._has_texture_search_api: bool = False
        # Preset rotation state for on-demand rendering
        self._live_preset_idx: int = 0
        self._live_frames_since_cut: int = 0
        # Consecutive dark frames rendered so far (see _DARK_BRIGHTNESS_THRESHOLD).
        self._dark_frame_streak: int = 0

        self._lib = self._load_library()
        self._setup_ctypes()

    @staticmethod
    def _load_library() -> ctypes.CDLL:
        """Load libprojectM from the known paths.

        Raises:
            RuntimeError: library not found or v4 API missing.
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
        """Define the ctypes signatures of the projectM functions used."""
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

        # channels: 1 = PROJECTM_MONO, 2 = PROJECTM_STEREO
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

        self._has_texture_search_api = hasattr(self._lib, "projectm_set_texture_search_paths")
        if self._has_texture_search_api:
            self._lib.projectm_set_texture_search_paths.restype = None
            self._lib.projectm_set_texture_search_paths.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_char_p),
                ctypes.c_size_t,
            ]
        else:
            logger.warning(
                "[MilkDropLayer] projectm_set_texture_search_paths absente de cette "
                "libprojectM — les presets utilisant des textures sprite externes "
                "s'afficheront sans elles (fallback texture zéro)."
            )

    @staticmethod
    def _dir_and_textures_subfolder(directory: str) -> list[str]:
        """Return [directory] plus its "textures" subfolder (any casing), if present.

        Matched by lowercased name rather than trying "textures"/"Textures" as
        two literal candidates: on a case-insensitive filesystem (macOS/APFS
        default) those resolve to the same directory and would be added twice.
        """
        if not directory:
            return []

        path = Path(directory)
        if not path.exists():
            return []
        base_dir = path if path.is_dir() else path.parent

        paths = [str(base_dir)]
        for entry in sorted(base_dir.iterdir()):
            if entry.is_dir() and entry.name.lower() == "textures":
                paths.append(str(entry))
                break
        return paths

    @classmethod
    def _texture_search_paths(cls, preset_path: str, texture_path: str = "") -> list[str]:
        """Directories where projectM should look up sprite textures used by presets.

        Most preset packs (e.g. "cream of the crop") ship without textures —
        pairing them with the official texture pack
        (github.com/projectM-visualizer/presets-milkdrop-texture-pack) is the
        documented way to make texture-dependent presets render correctly
        instead of falling back to a black/zero texture. `texture_path` is an
        explicit pointer to such a pack; `preset_path` is also searched since
        some packs bundle their own textures alongside the .milk files.
        """
        paths: list[str] = []
        for directory in (preset_path, texture_path):
            for candidate in cls._dir_and_textures_subfolder(directory):
                if candidate not in paths:
                    paths.append(candidate)
        return paths

    def _collect_presets(self) -> list[str]:
        """Collect the list of available .milk files."""
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
            all_presets = sorted(str(p) for p in preset_path.rglob("*.milk"))
            # Exclude transition presets (black, non-visual)
            presets = [p for p in all_presets if "transition" not in p.lower()]
            if not presets:
                presets = all_presets  # fallback if everything was transitions
            if not presets:
                logger.warning(
                    "[MilkDropLayer] Aucun fichier .milk trouvé dans : %s", self._preset_path
                )
                return presets
            # Deterministic shuffle by seed: each track sees a different order
            rng = random.Random(self._rng_seed)  # noqa: S311
            rng.shuffle(presets)
            logger.info(
                "[MilkDropLayer] %d presets mélangés (seed=%d)", len(presets), self._rng_seed
            )
            return presets

        logger.warning(
            "[MilkDropLayer] preset_path n'est ni un fichier .milk ni un répertoire : %s",
            self._preset_path,
        )
        return []

    def _precompute_beats(self) -> list[int]:
        """Compute the frame indices corresponding to the beats."""
        try:
            import librosa
        except ImportError:
            logger.warning("[MilkDropLayer] librosa absent — détection de beats désactivée")
            return []

        hop_length = 512  # default value of librosa.beat.beat_track
        samples_per_frame = max(1, self.sr // self.fps)
        # beat_track returns indices in units of hop_length, not in samples
        _, beat_hop_frames = librosa.beat.beat_track(
            y=self.audio, sr=self.sr, hop_length=hop_length
        )
        return [int((int(h) * hop_length) // samples_per_frame) for h in beat_hop_frames]

    def _init_gl(self) -> None:
        """Create (or recreate) the OpenGL context, FBO and projectM handle.

        Must be called from inside _gpu_lock.
        Destroys the previous resources if they exist.
        """
        logger.debug("[MilkDropLayer] _init_gl: destruction ressources précédentes")
        if self._handle is not None and self._lib is not None:
            self._lib.projectm_destroy(self._handle)
            self._handle = None
        if self._fbo is not None:
            try:
                self._fbo.release()  # type: ignore[attr-defined]
            except Exception:
                logger.debug("[MilkDropLayer] FBO stale (contexte déjà libéré), release ignoré")
            self._fbo = None

        self._presets = self._collect_presets()
        logger.debug("[MilkDropLayer] _init_gl: get_shared_gl_context()")
        self._ctx = get_shared_gl_context()
        logger.info("[MilkDropLayer] _init_gl: ctx type=%s", type(self._ctx).__name__)

        # Create color texture
        logger.debug("[MilkDropLayer] _init_gl: création texture %dx%d", self.width, self.height)
        texture = self._ctx.texture((self.width, self.height), 4)  # type: ignore[union-attr]
        # Add a depth buffer: some complex MilkDrop presets need it
        depth_attachment = self._ctx.depth_renderbuffer((self.width, self.height))  # type: ignore[union-attr]

        self._fbo = self._ctx.framebuffer(  # type: ignore[union-attr]
            color_attachments=[texture], depth_attachment=depth_attachment
        )
        logger.debug("[MilkDropLayer] _init_gl: FBO créé")

        self._handle = self._lib.projectm_create(None, self.width, self.height)  # type: ignore[union-attr]
        self._lib.projectm_set_window_size(self._handle, self.width, self.height)  # type: ignore[union-attr]

        if self._has_texture_search_api:
            texture_paths = self._texture_search_paths(self._preset_path, self._texture_path)
            if texture_paths:
                encoded = [p.encode("utf-8") for p in texture_paths]
                paths_array = (ctypes.c_char_p * len(encoded))(*encoded)
                self._lib.projectm_set_texture_search_paths(  # type: ignore[union-attr]
                    self._handle, paths_array, len(encoded)
                )
                logger.debug("[MilkDropLayer] Texture search paths: %s", texture_paths)

        if self._presets:
            logger.info("[MilkDropLayer] Chargement du premier preset : %s", self._presets[0])
            self._lib.projectm_load_preset_file(  # type: ignore[union-attr]
                self._handle, self._presets[0].encode(), False
            )

        self._fbo.use()  # type: ignore[union-attr]
        self._ctx.clear(0.0, 0.0, 0.0, 1.0)  # type: ignore[union-attr]
        self._live_preset_idx = 0
        self._live_frames_since_cut = 0
        self._dark_frame_streak = 0
        logger.debug("[MilkDropLayer] _init_gl: terminé")

    @staticmethod
    def _mean_brightness(image: Image.Image) -> float:
        """Mean pixel value (0-255) across RGB channels, used for the dark-streak check."""
        return float(np.asarray(image.convert("RGB"), dtype=np.uint8).mean())

    def _register_frame_brightness(self, mean_brightness: float) -> None:
        """Update the consecutive-dark-frames streak from one rendered frame."""
        if mean_brightness < self._DARK_BRIGHTNESS_THRESHOLD:
            self._dark_frame_streak += 1
        else:
            self._dark_frame_streak = 0

    def _dark_streak_exceeded(self, frames_since_cut: int) -> bool:
        """Whether the current preset has been dark long enough to force an early cut.

        Requires at least 1 second since the last cut too, so a preset that
        starts dark isn't judged before it has a chance to develop.
        """
        streak_limit = int(self._DARK_STREAK_SECONDS * self.fps)
        return frames_since_cut >= self.fps and self._dark_frame_streak >= streak_limit

    def _render_one_frame(self, frame_idx: int) -> Image.Image:
        """Render a single MilkDrop frame and return the RGBA image.

        Must be called from a context that already holds _gpu_lock.

        Args:
            frame_idx: Frame index used to synchronize the audio.

        Returns:
            RGBA PIL Image corresponding to the rendered frame.
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
        # OpenGL origin is bottom-left → vertical flip
        return Image.fromarray(np.flipud(data), "RGBA")

    def _do_warmup(self) -> None:
        """Run the projectM warmup loop (without acquiring _gpu_lock).

        Must be called from a context that already holds _gpu_lock.
        Initializes projectM's internal state with the start of the audio so
        that the visualization is already alive on the very first rendered frame.
        """
        if self._lib is None or self._handle is None or self._fbo is None:
            return

        samples_per_frame = max(1, self.sr // self.fps)
        # Reduced warmup: Transition presets are excluded from the list,
        # the shuffle guarantees a visual preset right from the start.
        warmup_count = 500
        warmup_audio_len = min(len(self.audio), int(3.0 * self.sr))
        if warmup_audio_len == 0:
            logger.warning("[MilkDropLayer] Audio de warmup vide !")
            return

        # Boost audio to excite the shaders during warmup
        warmup_audio = self.audio[:warmup_audio_len].copy()
        max_amp = np.max(np.abs(warmup_audio))
        if max_amp > 0:
            warmup_audio = np.clip(warmup_audio * (2.0 / max_amp), -1.0, 1.0)

        logger.info(
            "[MilkDropLayer] Démarrage chauffe intensive (%d frames, max_amp=%.4f)...",
            warmup_count,
            max_amp,
        )

        frames_per_preset = max(1, int(self._preset_duration * self.fps))

        for wi in range(warmup_count):
            # Preset cycle: advance the way render() would do live
            if self._presets and wi > 0 and wi % frames_per_preset == 0:
                self._live_preset_idx = (self._live_preset_idx + 1) % len(self._presets)
                self._lib.projectm_load_preset_file(
                    self._handle, self._presets[self._live_preset_idx].encode(), True
                )
                self._live_frames_since_cut = 0

            # Loop over the first 3 seconds
            w_start = (wi * samples_per_frame) % warmup_audio_len
            w_end = min(w_start + samples_per_frame, warmup_audio_len)

            pcm_w = np.zeros(samples_per_frame, dtype=np.float32)
            if w_end > w_start:
                pcm_w[: w_end - w_start] = warmup_audio[w_start:w_end].astype(np.float32)

            pcm_w_ptr = pcm_w.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            self._lib.projectm_pcm_add_float(self._handle, pcm_w_ptr, samples_per_frame, 1)

            self._fbo.use()  # type: ignore[attr-defined]
            self._lib.projectm_opengl_render_frame_fbo(
                self._handle, ctypes.c_uint(self._fbo.glo)  # type: ignore[attr-defined]
            )

            self._live_frames_since_cut += 1

            # Periodic flush
            if wi % 100 == 0:
                self._fbo.read(components=1)  # type: ignore[attr-defined]

        if self._ctx:
            self._ctx.finish()  # type: ignore[attr-defined]

        logger.info("[MilkDropLayer] Chauffe terminée")

    def warmup_gpu_frames(self) -> None:
        """Warm up projectM without pre-computing the full cache.

        Call from the main thread before the preview so that the MilkDrop
        effects are visible from the very first displayed frame.
        """
        if moderngl is None:
            raise RuntimeError("moderngl absent — installer avec : uv sync --extra video")

        with _gpu_lock:
            if self._handle is None:
                self._init_gl()
            self._do_warmup()
        logger.info("[MilkDropLayer] Warmup preview terminé")

    def prerender_gpu_frames(self) -> int:
        """Pre-render all MilkDrop frames and store them in the cache.

        Export-only: call from the main thread before the ThreadPoolExecutor.
        For the preview, do not call — render() uses on-demand rendering.

        Returns:
            Number of frames pre-rendered and cached.
        """
        if moderngl is None:
            raise RuntimeError("moderngl absent — installer avec : uv sync --extra video")

        total_frames = int(self.duration * self.fps)
        beats_set = set(self._precompute_beats())

        with _gpu_lock:
            # Clean reinitialization to guarantee deterministic rendering
            self._init_gl()

            # Pre-warmup via the shared method (without re-acquiring the lock)
            # _do_warmup() updates _live_preset_idx and _live_frames_since_cut
            self._do_warmup()

            # Continue from the state left by the warmup rather than
            # restarting from preset 0 (which is in ! Transition/)
            preset_idx = self._live_preset_idx
            frames_since_cut = self._live_frames_since_cut

            # Hard cut allowed only after 50% of the minimum preset duration
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
                    self._dark_frame_streak = 0
                elif self._presets and frames_since_cut >= int(self._preset_duration * self.fps):
                    preset_idx = (preset_idx + 1) % len(self._presets)
                    self._lib.projectm_load_preset_file(  # type: ignore[union-attr]
                        self._handle, self._presets[preset_idx].encode(), True
                    )
                    frames_since_cut = 0
                    self._dark_frame_streak = 0
                elif self._presets and self._dark_streak_exceeded(frames_since_cut):
                    preset_idx = (preset_idx + 1) % len(self._presets)
                    self._lib.projectm_load_preset_file(  # type: ignore[union-attr]
                        self._handle, self._presets[preset_idx].encode(), False
                    )
                    logger.info(
                        "[MilkDropLayer] Preset trop sombre depuis %.1fs, changement anticipé -> %s",
                        self._DARK_STREAK_SECONDS,
                        self._presets[preset_idx],
                    )
                    frames_since_cut = 0
                    self._dark_frame_streak = 0

                self._frame_cache[frame_idx] = self._render_one_frame(frame_idx)
                frames_since_cut += 1
                self._register_frame_brightness(self._mean_brightness(self._frame_cache[frame_idx]))

                if frame_idx > 0 and frame_idx % self.fps == 0:
                    logger.debug(
                        "[MilkDropLayer] Pré-rendu : %d/%d frames", frame_idx, total_frames
                    )

        logger.info(
            "[MilkDropLayer] Pré-rendu terminé : %d frames mises en cache", len(self._frame_cache)
        )
        return len(self._frame_cache)

    def render(self, frame_idx: int, time_pos: float) -> Image.Image:  # noqa: ARG002
        """Return the cached frame, or render on demand for the preview.

        Args:
            frame_idx: Frame index (0 to total_frames-1).
            time_pos: Time position in seconds.

        Returns:
            PIL Image in RGBA mode.
        """
        cached = self._frame_cache.get(frame_idx)
        if cached is not None:
            return cached

        # On-demand rendering — preview mode (no pre-rendering)
        with _gpu_lock:
            # Check the GL context validity inside the lock.
            # On macOS/CGL, the context created on the warmup thread becomes
            # InvalidObject when that thread terminates. We recreate it here on the
            # current thread (main thread) to guarantee functional rendering.
            if self._handle is None or not _is_gl_context_valid(self._ctx) or self._fbo is None:
                self._init_gl()

            # Preset rotation by duration (crossfade), or early if stuck too dark
            if self._presets and (
                self._live_frames_since_cut >= int(self._preset_duration * self.fps)
                or self._dark_streak_exceeded(self._live_frames_since_cut)
            ):
                self._live_preset_idx = (self._live_preset_idx + 1) % len(self._presets)
                self._lib.projectm_load_preset_file(  # type: ignore[union-attr]
                    self._handle, self._presets[self._live_preset_idx].encode(), True
                )
                self._live_frames_since_cut = 0
                self._dark_frame_streak = 0

            img = self._render_one_frame(frame_idx)

        self._live_frames_since_cut += 1
        self._register_frame_brightness(self._mean_brightness(img))
        return img

    def shutdown(self) -> None:
        """Release the projectM resources."""
        with _gpu_lock:
            if self._handle is not None and self._lib is not None:
                self._lib.projectm_destroy(self._handle)
                self._handle = None
            if self._fbo is not None:
                self._fbo.release()  # type: ignore[attr-defined]
                self._fbo = None
        logger.info("[MilkDropLayer] shutdown")
