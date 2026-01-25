"""Video background layer for playing video clips behind the visualization."""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image

from plugins.video_exporter.layers.base import BaseVisualLayer

if TYPE_CHECKING:
    from numpy.typing import NDArray


class VideoBackgroundLayer(BaseVisualLayer):
    """Video background layer that plays video clips from a folder.

    Thread-safe: All frames are pre-loaded during initialization.
    """

    z_index = 0  # Lowest z-index, renders first (background)

    # Supported video formats
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    def __init__(
        self,
        width: int,
        height: int,
        fps: int,
        audio: NDArray[np.floating],
        sr: int,
        duration: float,
        video_folder: str = "",
        opacity: float = 0.5,
        blend_mode: str = "normal",
        **kwargs: Any,
    ) -> None:
        """Initialize video background layer.

        Args:
            width: Frame width.
            height: Frame height.
            fps: Frames per second.
            audio: Audio samples.
            sr: Sample rate.
            duration: Duration in seconds.
            video_folder: Path to folder containing video clips.
            opacity: Opacity of the video background (0.0 to 1.0).
            blend_mode: Blend mode (normal, multiply, screen).
            **kwargs: Additional parameters.
        """
        self.video_folder = Path(video_folder).expanduser() if video_folder else None
        self.opacity = opacity
        self.blend_mode = blend_mode
        self.video_clips: list[Path] = []
        # Pre-loaded frames for the entire duration (thread-safe access)
        self.all_frames: list[Image.Image] = []

        super().__init__(width, height, fps, audio, sr, duration, **kwargs)

    def _precompute(self) -> None:
        """Load video clips from folder and pre-cache all needed frames."""
        if not self.video_folder or not self.video_folder.exists():
            logging.warning(f"[Video Layer] Video folder not found: {self.video_folder}")
            return

        # Find all video files
        for ext in self.VIDEO_EXTENSIONS:
            self.video_clips.extend(self.video_folder.glob(f"*{ext}"))
            self.video_clips.extend(self.video_folder.glob(f"*{ext.upper()}"))

        if not self.video_clips:
            logging.warning(f"[Video Layer] No video clips found in {self.video_folder}")
            return

        # Shuffle clips for variety
        random.shuffle(self.video_clips)

        logging.info(f"[Video Layer] Found {len(self.video_clips)} video clips")

        # Pre-load all frames needed for the entire duration
        self._preload_all_frames()

    def _preload_all_frames(self) -> None:
        """Pre-load all frames needed for the export duration."""
        try:
            import cv2
        except ImportError:
            logging.warning("[Video Layer] OpenCV not available, using static images")
            self._load_as_images()
            return

        clip_idx = 0
        frames_loaded = 0

        while frames_loaded < self.total_frames and clip_idx < len(self.video_clips) * 3:
            clip_path = self.video_clips[clip_idx % len(self.video_clips)]
            logging.info(f"[Video Layer] Loading clip: {clip_path}")

            try:
                cap = cv2.VideoCapture(str(clip_path))

                while frames_loaded < self.total_frames:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    # Convert BGR to RGB
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                    # Resize to match output dimensions
                    frame = cv2.resize(frame, (self.width, self.height))

                    # Convert to PIL Image and store
                    img = Image.fromarray(frame)
                    self.all_frames.append(img)
                    frames_loaded += 1

                cap.release()

            except Exception as e:
                logging.error(f"[Video Layer] Error loading video {clip_path}: {e}")

            clip_idx += 1

        logging.info(
            f"[Video Layer] Pre-loaded {len(self.all_frames)} frames "
            f"for {self.total_frames} total needed"
        )

    def _load_as_images(self) -> None:
        """Fallback: Load image files from the folder."""
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}

        for ext in image_extensions:
            for img_path in self.video_folder.glob(f"*{ext}"):
                try:
                    img = Image.open(img_path)
                    img = img.convert("RGB")
                    img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)
                    self.all_frames.append(img)
                except Exception as e:
                    logging.warning(f"[Video Layer] Could not load image {img_path}: {e}")

        # If we don't have enough images, repeat them
        if self.all_frames and len(self.all_frames) < self.total_frames:
            original_count = len(self.all_frames)
            while len(self.all_frames) < self.total_frames:
                self.all_frames.append(self.all_frames[len(self.all_frames) % original_count])

    def render(self, frame_idx: int, time_pos: float) -> Image.Image:
        """Render video background frame.

        Thread-safe: Only reads from pre-loaded frames.

        Args:
            frame_idx: Frame index.
            time_pos: Time position in seconds.

        Returns:
            RGBA image with video frame.
        """
        if not self.all_frames:
            # Return transparent frame if no video loaded
            return self.create_transparent_image()

        # Get frame (loop if needed)
        actual_idx = frame_idx % len(self.all_frames)
        frame = self.all_frames[actual_idx].copy()

        # Convert to RGBA
        if frame.mode != "RGBA":
            frame = frame.convert("RGBA")

        # Apply opacity
        if self.opacity < 1.0:
            alpha = int(255 * self.opacity)
            # Create alpha mask
            r, g, b, a = frame.split()
            a = a.point(lambda x: min(x, alpha))
            frame = Image.merge("RGBA", (r, g, b, a))

        return frame

    def _apply_blend(self, background: Image.Image, foreground: Image.Image) -> Image.Image:
        """Apply blend mode to combine images.

        Args:
            background: Background image.
            foreground: Foreground image.

        Returns:
            Blended image.
        """
        if self.blend_mode == "normal":
            return Image.alpha_composite(background, foreground)

        elif self.blend_mode == "multiply":
            bg_arr = np.array(background, dtype=float) / 255
            fg_arr = np.array(foreground, dtype=float) / 255
            result = (bg_arr * fg_arr * 255).astype(np.uint8)
            return Image.fromarray(result, mode="RGBA")

        elif self.blend_mode == "screen":
            bg_arr = np.array(background, dtype=float) / 255
            fg_arr = np.array(foreground, dtype=float) / 255
            result = (1 - (1 - bg_arr) * (1 - fg_arr)) * 255
            return Image.fromarray(result.astype(np.uint8), mode="RGBA")

        return Image.alpha_composite(background, foreground)
