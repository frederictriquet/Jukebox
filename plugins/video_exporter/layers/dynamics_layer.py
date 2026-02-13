"""Dynamics effects layer based on audio energy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image, ImageDraw

from plugins.video_exporter.layers.base import BaseVisualLayer

if TYPE_CHECKING:
    from numpy.typing import NDArray


class DynamicsLayer(BaseVisualLayer):
    """Dynamic visual effects based on audio energy (pulse, brightness, vignette)."""

    z_index = 3

    def __init__(
        self,
        width: int,
        height: int,
        fps: int,
        audio: NDArray[np.floating],
        sr: int,
        duration: float,
        pulse_intensity: float = 0.8,
        brightness_intensity: float = 0.6,
        vignette_intensity: float = 0.7,
        **kwargs: Any,
    ) -> None:
        """Initialize dynamics layer.

        Args:
            width: Frame width.
            height: Frame height.
            fps: Frames per second.
            audio: Audio samples.
            sr: Sample rate.
            duration: Duration in seconds.
            pulse_intensity: Intensity of pulse effect (0.0 to 1.0).
            brightness_intensity: Intensity of brightness modulation (0.0 to 1.0).
            vignette_intensity: Intensity of vignette effect (0.0 to 1.0).
            **kwargs: Additional parameters.
        """
        self.pulse_intensity = pulse_intensity
        self.brightness_intensity = brightness_intensity
        self.vignette_intensity = vignette_intensity
        super().__init__(width, height, fps, audio, sr, duration, **kwargs)

    def _precompute(self) -> None:
        """Pre-compute energy envelope and bass energy."""
        # Compute energy per frame
        samples_per_frame = len(self.audio) / self.total_frames
        self.energy_envelope = []
        self.bass_energy_envelope = []

        # Apply low-pass filter for bass energy
        try:
            from scipy import signal

            nyquist = self.sr / 2
            bass_cutoff = 150 / nyquist
            b, a = signal.butter(4, bass_cutoff, btype="low")
            bass_audio = signal.filtfilt(b, a, self.audio)
        except ImportError:
            # Fallback: use full audio for bass
            bass_audio = self.audio

        for frame_idx in range(self.total_frames):
            start = int(frame_idx * samples_per_frame)
            end = int((frame_idx + 1) * samples_per_frame)

            # Overall energy
            chunk = self.audio[start:end]
            energy = np.sqrt(np.mean(chunk**2)) if len(chunk) > 0 else 0.0
            self.energy_envelope.append(energy)

            # Bass energy
            bass_chunk = bass_audio[start:end]
            bass_energy = np.sqrt(np.mean(bass_chunk**2)) if len(bass_chunk) > 0 else 0.0
            self.bass_energy_envelope.append(bass_energy)

        # Normalize envelopes
        max_energy = max(self.energy_envelope) if max(self.energy_envelope) > 0 else 1.0
        max_bass = max(self.bass_energy_envelope) if max(self.bass_energy_envelope) > 0 else 1.0

        self.energy_envelope = np.array(self.energy_envelope) / max_energy
        self.bass_energy_envelope = np.array(self.bass_energy_envelope) / max_bass

        # Pre-compute vignette mask
        self._create_vignette_mask()

    def _create_vignette_mask(self) -> None:
        """Create a vignette mask for darkening edges."""
        # Create radial gradient
        y, x = np.ogrid[: self.height, : self.width]
        center_y, center_x = self.height / 2, self.width / 2

        # Normalize coordinates
        y_norm = (y - center_y) / (self.height / 2)
        x_norm = (x - center_x) / (self.width / 2)

        # Calculate distance from center (elliptical)
        distance = np.sqrt(x_norm**2 + y_norm**2)

        # Create smooth vignette (1.0 at center, 0.0 at edges)
        vignette = 1.0 - np.clip(distance * 0.7, 0, 1) ** 2
        self.vignette_base = (vignette * 255).astype(np.uint8)

    def render(self, frame_idx: int, time_pos: float) -> Image.Image:
        """Render dynamics effects for the current frame.

        Args:
            frame_idx: Frame index.
            time_pos: Time position in seconds.

        Returns:
            RGBA image with dynamics effects overlay.
        """
        img = self.create_transparent_image()

        # Get current energy values
        frame_idx = min(frame_idx, len(self.energy_envelope) - 1)
        energy = self.energy_envelope[frame_idx]
        bass_energy = self.bass_energy_envelope[frame_idx]

        # Apply pulse effect (radial glow on bass)
        if self.pulse_intensity > 0 and bass_energy > 0.15:
            self._apply_pulse(img, bass_energy)

        # Apply vignette that responds to energy
        if self.vignette_intensity > 0:
            self._apply_vignette(img, energy)

        # Apply brightness flash on peaks
        if self.brightness_intensity > 0 and energy > 0.5:
            self._apply_flash(img, energy)

        return img

    def _apply_pulse(self, img: Image.Image, bass_energy: float) -> None:
        """Apply radial pulse effect based on bass energy.

        Args:
            img: Image to modify in place.
            bass_energy: Normalized bass energy (0.0 to 1.0).
        """
        draw = ImageDraw.Draw(img)

        # Calculate pulse size
        max_radius = min(self.width, self.height) // 3
        pulse_radius = int(max_radius * bass_energy * self.pulse_intensity)

        if pulse_radius < 10:
            return

        # Draw concentric circles with decreasing alpha
        center = (self.width // 2, self.height // 2)
        n_circles = 8
        base_alpha = int(200 * self.pulse_intensity * bass_energy)

        for i in range(n_circles):
            radius = pulse_radius * (1 - i / n_circles)
            alpha = int(base_alpha * (1 - i / n_circles))
            if radius > 0 and alpha > 0:
                # Cyan/blue tint for the pulse
                color = (0, 200, 255, min(alpha, 255))
                draw.ellipse(
                    [
                        center[0] - radius,
                        center[1] - radius,
                        center[0] + radius,
                        center[1] + radius,
                    ],
                    outline=color,
                    width=5,
                )

    def _apply_vignette(self, img: Image.Image, energy: float) -> None:
        """Apply vignette effect that responds to energy.

        Args:
            img: Image to modify.
            energy: Normalized energy (0.0 to 1.0).
        """
        # Vignette is stronger when energy is low
        vignette_strength = self.vignette_intensity * (1 - energy * 0.5)

        if vignette_strength < 0.1:
            return

        # Create vignette overlay
        vignette_alpha = ((1 - self.vignette_base / 255.0) * 200 * vignette_strength).astype(
            np.uint8
        )
        vignette_img = Image.fromarray(
            np.stack(
                [
                    np.zeros_like(vignette_alpha),  # R
                    np.zeros_like(vignette_alpha),  # G
                    np.zeros_like(vignette_alpha),  # B
                    vignette_alpha,  # A
                ],
                axis=-1,
            ),
            mode="RGBA",
        )

        # Composite
        img.paste(vignette_img, (0, 0), vignette_img)

    def _apply_flash(self, img: Image.Image, energy: float) -> None:
        """Apply brightness flash on energy peaks.

        Args:
            img: Image to modify.
            energy: Normalized energy (0.0 to 1.0).
        """
        # Create white overlay with moderate alpha
        flash_alpha = int(120 * (energy - 0.5) / 0.5 * self.brightness_intensity)
        flash_alpha = min(flash_alpha, 100)

        if flash_alpha <= 0:
            return

        flash = Image.new("RGBA", (self.width, self.height), (255, 255, 255, flash_alpha))
        img.paste(flash, (0, 0), flash)
