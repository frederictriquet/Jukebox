"""Base class for visual layers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from numpy.typing import NDArray


class BaseVisualLayer(ABC):
    """Abstract base class for visual layers in video export."""

    # Z-index for layer ordering (lower = background, higher = foreground)
    z_index: int = 0

    def __init__(
        self,
        width: int,
        height: int,
        fps: int,
        audio: NDArray[np.floating],
        sr: int,
        duration: float,
        **kwargs: Any,
    ) -> None:
        """Initialize the visual layer.

        Args:
            width: Frame width in pixels.
            height: Frame height in pixels.
            fps: Frames per second.
            audio: Audio samples as numpy array.
            sr: Sample rate.
            duration: Duration in seconds.
            **kwargs: Additional layer-specific parameters.
        """
        self.width = width
        self.height = height
        self.fps = fps
        self.audio = audio
        self.sr = sr
        self.duration = duration
        self.total_frames = int(duration * fps)

        # Pre-compute features if needed
        self._precompute()

    def _precompute(self) -> None:  # noqa: B027
        """Pre-compute features or data needed for rendering.

        Override this method in subclasses to compute features
        that are needed for all frames (e.g., spectrogram, waveform data).
        This method is intentionally not abstract to allow subclasses to skip it.
        """

    @abstractmethod
    def render(self, frame_idx: int, time_pos: float) -> Image.Image:
        """Render the layer for a specific frame.

        Args:
            frame_idx: Frame index (0 to total_frames-1).
            time_pos: Time position in seconds.

        Returns:
            PIL Image in RGBA mode.
        """
        pass

    def create_transparent_image(self) -> Image.Image:
        """Create a transparent RGBA image.

        Returns:
            Transparent PIL Image in RGBA mode.
        """
        return Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

    def get_audio_samples_at(self, time_pos: float, window_size: float = 0.1) -> NDArray:
        """Get audio samples around a specific time position.

        Args:
            time_pos: Time position in seconds.
            window_size: Window size in seconds.

        Returns:
            Audio samples as numpy array.
        """
        start_sample = int((time_pos - window_size / 2) * self.sr)
        end_sample = int((time_pos + window_size / 2) * self.sr)

        # Clamp to valid range
        start_sample = max(0, start_sample)
        end_sample = min(len(self.audio), end_sample)

        if start_sample >= end_sample:
            return np.zeros(int(window_size * self.sr))

        return self.audio[start_sample:end_sample]

    def get_energy_at(self, time_pos: float, window_size: float = 0.1) -> float:
        """Get audio energy (RMS) at a specific time position.

        Args:
            time_pos: Time position in seconds.
            window_size: Window size in seconds.

        Returns:
            RMS energy value (0.0 to 1.0 normalized).
        """
        samples = self.get_audio_samples_at(time_pos, window_size)
        if len(samples) == 0:
            return 0.0

        rms = np.sqrt(np.mean(samples**2))
        # Normalize (typical RMS values are 0.0-0.3 for music)
        return min(1.0, rms * 3.0)
