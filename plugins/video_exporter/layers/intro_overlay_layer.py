"""Intro overlay layer for playing a video once on top of other layers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image

from plugins.video_exporter.layers.base import BaseVisualLayer

if TYPE_CHECKING:
    from numpy.typing import NDArray


class IntroOverlayLayer(BaseVisualLayer):
    """Intro overlay layer that plays a video file once on top of other layers.

    Thread-safe: All frames are pre-loaded during initialization.
    """

    z_index = 100  # Highest z-index, renders last (on top of everything)

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
        video_path: str = "",
        chroma_key_threshold: int = 30,
        **kwargs: Any,
    ) -> None:
        """Initialize intro overlay layer.

        Args:
            width: Frame width.
            height: Frame height.
            fps: Frames per second.
            audio: Audio samples.
            sr: Sample rate.
            duration: Duration in seconds.
            video_path: Path to the intro video file.
            chroma_key_threshold: Brightness threshold for black chroma key (0-255).
                                  Pixels darker than this become transparent.
            **kwargs: Additional parameters.
        """
        self.video_path = Path(video_path).expanduser() if video_path else None
        self.chroma_key_threshold = chroma_key_threshold
        # Pre-loaded frames for the intro video (thread-safe access)
        self.all_frames: list[Image.Image] = []
        self.video_duration_frames = 0

        super().__init__(width, height, fps, audio, sr, duration, **kwargs)

    def _precompute(self) -> None:
        """Load the intro video and pre-cache all frames."""
        if not self.video_path:
            logging.info("[Intro Overlay] No video path specified")
            return

        if not self.video_path.exists():
            logging.warning(f"[Intro Overlay] Video file not found: {self.video_path}")
            return

        if self.video_path.suffix.lower() not in self.VIDEO_EXTENSIONS:
            logging.warning(
                f"[Intro Overlay] Unsupported video format: {self.video_path.suffix}"
            )
            return

        logging.info(f"[Intro Overlay] Loading video: {self.video_path}")

        # Pre-load all frames from the video
        self._preload_video_frames()

    def _preload_video_frames(self) -> None:
        """Pre-load all frames from the intro video."""
        try:
            import cv2
        except ImportError:
            logging.warning("[Intro Overlay] OpenCV not available, cannot load video")
            return

        try:
            cap = cv2.VideoCapture(str(self.video_path))

            # Get video properties
            video_fps = cap.get(cv2.CAP_PROP_FPS)
            total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            logging.info(
                f"[Intro Overlay] Video info: {video_width}x{video_height} @ {video_fps}fps, "
                f"{total_video_frames} frames"
            )

            # Determine frame sampling strategy
            # If video FPS differs from export FPS, we need to resample
            frame_ratio = video_fps / self.fps if video_fps > 0 else 1.0

            frame_idx = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Sample frames to match export FPS
                target_frame = int(frame_idx / frame_ratio)
                if target_frame >= len(self.all_frames):
                    # Convert BGR to RGBA
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)

                    # Resize to match output dimensions while preserving aspect ratio
                    frame = self._resize_with_aspect_ratio(frame, self.width, self.height)

                    # Apply chroma key: make dark pixels transparent
                    frame = self._apply_chroma_key(frame)

                    # Convert to PIL Image
                    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGRA2RGBA))
                    self.all_frames.append(img)

                frame_idx += 1

            cap.release()

            self.video_duration_frames = len(self.all_frames)
            video_duration_sec = self.video_duration_frames / self.fps

            logging.info(
                f"[Intro Overlay] Pre-loaded {self.video_duration_frames} frames "
                f"({video_duration_sec:.2f}s at {self.fps}fps)"
            )

        except Exception as e:
            logging.error(f"[Intro Overlay] Error loading video: {e}")

    def _resize_with_aspect_ratio(
        self, frame: np.ndarray, target_width: int, target_height: int
    ) -> np.ndarray:
        """Resize frame to fit target dimensions while preserving aspect ratio.

        The frame is centered with transparent padding if needed.

        Args:
            frame: Input frame (BGRA).
            target_width: Target width.
            target_height: Target height.

        Returns:
            Resized frame with transparent background.
        """
        import cv2

        h, w = frame.shape[:2]
        aspect = w / h
        target_aspect = target_width / target_height

        if aspect > target_aspect:
            # Video is wider than target - fit to width
            new_width = target_width
            new_height = int(target_width / aspect)
        else:
            # Video is taller than target - fit to height
            new_height = target_height
            new_width = int(target_height * aspect)

        # Resize the frame
        resized = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)

        # Create transparent canvas
        canvas = np.zeros((target_height, target_width, 4), dtype=np.uint8)

        # Center the resized frame
        x_offset = (target_width - new_width) // 2
        y_offset = (target_height - new_height) // 2

        canvas[y_offset : y_offset + new_height, x_offset : x_offset + new_width] = resized

        return canvas

    def _apply_chroma_key(self, frame: np.ndarray) -> np.ndarray:
        """Apply chroma key to make dark/black pixels transparent.

        Args:
            frame: Input frame (BGRA).

        Returns:
            Frame with dark pixels made transparent.
        """
        # Calculate brightness (max of RGB channels)
        brightness = np.max(frame[:, :, :3], axis=2)

        # Create alpha mask: transparent for dark pixels, opaque for bright pixels
        # Use smooth transition for better blending
        alpha = np.clip(
            (brightness.astype(float) - self.chroma_key_threshold) * 255
            / max(1, 255 - self.chroma_key_threshold),
            0,
            255,
        ).astype(np.uint8)

        # Apply alpha to frame
        frame[:, :, 3] = alpha

        return frame

    def render(self, frame_idx: int, _time_pos: float) -> Image.Image:
        """Render intro overlay frame.

        Thread-safe: Only reads from pre-loaded frames.

        Args:
            frame_idx: Frame index.
            time_pos: Time position in seconds.

        Returns:
            RGBA image with video frame, or transparent if video has ended.
        """
        if not self.all_frames:
            # No video loaded
            return self.create_transparent_image()

        if frame_idx >= self.video_duration_frames:
            # Video has ended, return transparent frame
            return self.create_transparent_image()

        # Get frame from pre-loaded frames
        frame = self.all_frames[frame_idx].copy()

        # Ensure RGBA mode
        if frame.mode != "RGBA":
            frame = frame.convert("RGBA")

        return frame
