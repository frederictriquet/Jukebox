"""Intro overlay layer for playing a video once on top of other layers."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image

from plugins.video_exporter.layers.base import BaseVisualLayer

if TYPE_CHECKING:
    from numpy.typing import NDArray


class IntroOverlayLayer(BaseVisualLayer):
    """Intro overlay layer that plays a video file once on top of other layers.

    Les frames sont décodées à la demande via cv2.VideoCapture (seeking) — aucune
    pré-allocation RAM. Thread-safe via un verrou sur le VideoCapture.
    """

    z_index = 100

    VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    def __init__(
        self,
        width: int,
        height: int,
        fps: int,
        audio: NDArray[np.floating],
        sr: int,
        duration: float,
        video_path: str = "",
        chroma_key_threshold: int = 30,
        fade_out_duration: float = 1.0,
        **kwargs: Any,
    ) -> None:
        self.video_path = Path(video_path).expanduser() if video_path else None
        self.chroma_key_threshold = chroma_key_threshold
        self.fade_out_duration = fade_out_duration
        self.video_duration_frames = 0
        self.fade_out_frames = 0
        self._frame_ratio: float = 1.0
        self._cap: Any = None
        self._cap_lock = threading.Lock()

        super().__init__(width, height, fps, audio, sr, duration, **kwargs)

    def _precompute(self) -> None:
        """Valide la vidéo et lit ses métadonnées sans charger les pixels."""
        if not self.video_path:
            logging.info("[Intro Overlay] Aucun chemin vidéo spécifié")
            return

        if not self.video_path.exists():
            raise FileNotFoundError(f"Vidéo d'intro introuvable : {self.video_path}")

        if self.video_path.suffix.lower() not in self.VIDEO_EXTENSIONS:
            raise ValueError(
                f"Format vidéo non supporté pour l'intro : {self.video_path.suffix}"
            )

        try:
            import cv2
        except ImportError as e:
            raise ImportError(
                "OpenCV (cv2) est requis pour la vidéo d'intro. "
                "Installe-le avec : uv sync --extra video"
            ) from e

        cap = cv2.VideoCapture(str(self.video_path))
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        logging.info(
            "[Intro Overlay] Vidéo : %dx%d @ %.2ffps, %d frames",
            video_width, video_height, video_fps, total_video_frames,
        )

        self._frame_ratio = video_fps / self.fps if video_fps > 0 else 1.0
        self.video_duration_frames = int(total_video_frames / self._frame_ratio)
        self.fade_out_frames = int(self.fade_out_duration * self.fps)

        # Garder le VideoCapture ouvert pour le seeking en render()
        self._cap = cap

        logging.info(
            "[Intro Overlay] Prêt — %d frames de sortie (%.2fs), fade-out: %d frames",
            self.video_duration_frames,
            self.video_duration_frames / self.fps,
            self.fade_out_frames,
        )

    def _read_video_frame(self, video_frame_idx: int) -> np.ndarray | None:
        """Seek et lit une frame brute depuis le VideoCapture (thread-safe)."""
        import cv2

        with self._cap_lock:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, video_frame_idx)
            ret, frame = self._cap.read()

        if not ret:
            return None

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
        frame = self._resize_with_aspect_ratio(frame, self.width, self.height)
        frame = self._apply_chroma_key(frame)
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2RGBA)

    def render(self, frame_idx: int, time_pos: float) -> Image.Image:  # noqa: ARG002
        """Décode et retourne la frame de la vidéo d'intro pour frame_idx."""
        if self._cap is None or frame_idx >= self.video_duration_frames:
            return self.create_transparent_image()

        video_frame_idx = int(frame_idx * self._frame_ratio)
        raw = self._read_video_frame(video_frame_idx)
        if raw is None:
            return self.create_transparent_image()

        img = Image.fromarray(raw, "RGBA")

        if self.fade_out_frames > 0:
            fade_start = self.video_duration_frames - self.fade_out_frames
            if frame_idx >= fade_start:
                alpha_multiplier = 1.0 - (frame_idx - fade_start) / self.fade_out_frames
                data = np.array(img)
                data[:, :, 3] = (data[:, :, 3] * alpha_multiplier).astype(np.uint8)
                img = Image.fromarray(data, "RGBA")

        return img

    def __del__(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                logging.debug("[Intro Overlay] Erreur lors de la libération du VideoCapture")
            self._cap = None

    def _resize_with_aspect_ratio(
        self, frame: np.ndarray, target_width: int, target_height: int
    ) -> np.ndarray:
        """Resize en préservant le ratio, centré sur fond transparent."""
        import cv2

        h, w = frame.shape[:2]
        aspect = w / h
        target_aspect = target_width / target_height

        if aspect > target_aspect:
            new_width = target_width
            new_height = int(target_width / aspect)
        else:
            new_height = target_height
            new_width = int(target_height * aspect)

        resized = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)

        canvas = np.zeros((target_height, target_width, 4), dtype=np.uint8)
        x_offset = (target_width - new_width) // 2
        y_offset = (target_height - new_height) // 2
        canvas[y_offset : y_offset + new_height, x_offset : x_offset + new_width] = resized
        return canvas

    def _apply_chroma_key(self, frame: np.ndarray) -> np.ndarray:
        """Rend transparents les pixels sombres (chroma key noir)."""
        brightness = np.max(frame[:, :, :3], axis=2)
        alpha = np.clip(
            (brightness.astype(float) - self.chroma_key_threshold) * 255
            / max(1, 255 - self.chroma_key_threshold),
            0,
            255,
        ).astype(np.uint8)
        frame[:, :, 3] = alpha
        return frame
