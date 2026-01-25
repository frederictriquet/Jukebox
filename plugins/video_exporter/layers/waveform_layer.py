"""Waveform visualization layer with animated cursor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image, ImageDraw

from plugins.video_exporter.layers.base import BaseVisualLayer

if TYPE_CHECKING:
    from numpy.typing import NDArray


class WaveformLayer(BaseVisualLayer):
    """Animated waveform visualization with 3-band coloring and cursor."""

    z_index = 2

    # Default colors (similar to waveform_visualizer plugin)
    DEFAULT_BASS_COLOR = (0, 102, 255, 255)  # Blue
    DEFAULT_MID_COLOR = (0, 255, 0, 255)  # Green
    DEFAULT_TREBLE_COLOR = (255, 255, 255, 255)  # White
    DEFAULT_CURSOR_COLOR = (255, 255, 255, 200)  # White semi-transparent

    def __init__(
        self,
        width: int,
        height: int,
        fps: int,
        audio: NDArray[np.floating],
        sr: int,
        duration: float,
        waveform_height_ratio: float = 0.3,
        bass_color: str | None = None,
        mid_color: str | None = None,
        treble_color: str | None = None,
        cursor_color: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize waveform layer.

        Args:
            width: Frame width.
            height: Frame height.
            fps: Frames per second.
            audio: Audio samples.
            sr: Sample rate.
            duration: Duration in seconds.
            waveform_height_ratio: Height of waveform as ratio of frame height.
            bass_color: Hex color for bass frequencies.
            mid_color: Hex color for mid frequencies.
            treble_color: Hex color for treble frequencies.
            cursor_color: Hex color for cursor.
            **kwargs: Additional parameters.
        """
        self.waveform_height_ratio = waveform_height_ratio
        # Parse colors from hex or use defaults
        self.bass_color = self._parse_color(bass_color, self.DEFAULT_BASS_COLOR)
        self.mid_color = self._parse_color(mid_color, self.DEFAULT_MID_COLOR)
        self.treble_color = self._parse_color(treble_color, self.DEFAULT_TREBLE_COLOR)
        self.cursor_color = self._parse_color(cursor_color, self.DEFAULT_CURSOR_COLOR, alpha=200)
        super().__init__(width, height, fps, audio, sr, duration, **kwargs)

    @staticmethod
    def _parse_color(
        hex_color: str | None,
        default: tuple[int, int, int, int],
        alpha: int = 255,
    ) -> tuple[int, int, int, int]:
        """Parse hex color to RGBA tuple.

        Args:
            hex_color: Hex color string (e.g., "#0066FF").
            default: Default RGBA tuple if hex_color is None or invalid.
            alpha: Alpha value (0-255).

        Returns:
            RGBA color tuple.
        """
        if not hex_color:
            return default
        try:
            hex_color = hex_color.lstrip("#")
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return (r, g, b, alpha)
        except (ValueError, IndexError):
            return default

    def _precompute(self) -> None:
        """Pre-compute waveform data for all frames."""
        # Import scipy for filtering
        try:
            from scipy import signal
        except ImportError:
            # Fallback without filtering
            self._use_filtering = False
            self._compute_simple_waveform()
            return

        self._use_filtering = True

        # Design filters
        nyquist = self.sr / 2

        # Bass filter: 20-250 Hz
        bass_low = 20 / nyquist
        bass_high = 250 / nyquist
        self.bass_b, self.bass_a = signal.butter(4, [bass_low, bass_high], btype="band")

        # Mid filter: 250-4000 Hz
        mid_low = 250 / nyquist
        mid_high = min(4000 / nyquist, 0.99)
        self.mid_b, self.mid_a = signal.butter(4, [mid_low, mid_high], btype="band")

        # Treble filter: 4000+ Hz
        treble_low = min(4000 / nyquist, 0.99)
        self.treble_b, self.treble_a = signal.butter(4, treble_low, btype="high")

        # Apply filters
        self.bass_audio = signal.filtfilt(self.bass_b, self.bass_a, self.audio)
        self.mid_audio = signal.filtfilt(self.mid_b, self.mid_a, self.audio)
        self.treble_audio = signal.filtfilt(self.treble_b, self.treble_a, self.audio)

        # Compute waveform display data (envelope)
        self._compute_waveform_envelope()

    def _compute_simple_waveform(self) -> None:
        """Compute simple waveform without filtering."""
        samples_per_pixel = len(self.audio) / self.width
        self.waveform_data = []

        for x in range(self.width):
            start = int(x * samples_per_pixel)
            end = int((x + 1) * samples_per_pixel)
            chunk = self.audio[start:end]
            max_val = np.max(np.abs(chunk)) if len(chunk) > 0 else 0.0
            self.waveform_data.append(max_val)

        self.waveform_data = np.array(self.waveform_data)

    def _compute_waveform_envelope(self) -> None:
        """Compute envelope for each frequency band."""
        samples_per_pixel = len(self.audio) / self.width

        self.bass_envelope = []
        self.mid_envelope = []
        self.treble_envelope = []

        for x in range(self.width):
            start = int(x * samples_per_pixel)
            end = int((x + 1) * samples_per_pixel)

            bass_chunk = self.bass_audio[start:end]
            mid_chunk = self.mid_audio[start:end]
            treble_chunk = self.treble_audio[start:end]

            if len(bass_chunk) > 0:
                self.bass_envelope.append(np.max(np.abs(bass_chunk)))
                self.mid_envelope.append(np.max(np.abs(mid_chunk)))
                self.treble_envelope.append(np.max(np.abs(treble_chunk)))
            else:
                self.bass_envelope.append(0.0)
                self.mid_envelope.append(0.0)
                self.treble_envelope.append(0.0)

        # Normalize
        max_bass = max(self.bass_envelope) if max(self.bass_envelope) > 0 else 1.0
        max_mid = max(self.mid_envelope) if max(self.mid_envelope) > 0 else 1.0
        max_treble = max(self.treble_envelope) if max(self.treble_envelope) > 0 else 1.0

        self.bass_envelope = np.array(self.bass_envelope) / max_bass
        self.mid_envelope = np.array(self.mid_envelope) / max_mid
        self.treble_envelope = np.array(self.treble_envelope) / max_treble

    def render(self, frame_idx: int, time_pos: float) -> Image.Image:
        """Render waveform with cursor for the current frame.

        Args:
            frame_idx: Frame index.
            time_pos: Time position in seconds.

        Returns:
            RGBA image with waveform visualization.
        """
        img = self.create_transparent_image()
        draw = ImageDraw.Draw(img)

        # Calculate waveform area
        waveform_height = int(self.height * self.waveform_height_ratio)
        y_center = self.height - waveform_height // 2 - 20  # Bottom area

        # Calculate cursor position
        cursor_x = int((time_pos / self.duration) * self.width)

        if self._use_filtering:
            # Draw 3-band waveform
            self._draw_band(draw, self.bass_envelope, y_center, waveform_height, self.bass_color)
            self._draw_band(
                draw, self.mid_envelope, y_center, waveform_height * 0.7, self.mid_color
            )
            self._draw_band(
                draw, self.treble_envelope, y_center, waveform_height * 0.4, self.treble_color
            )
        else:
            # Draw simple waveform
            self._draw_band(draw, self.waveform_data, y_center, waveform_height, self.mid_color)

        # Draw cursor
        draw.line(
            [
                (cursor_x, y_center - waveform_height // 2),
                (cursor_x, y_center + waveform_height // 2),
            ],
            fill=self.cursor_color,
            width=2,
        )

        # Draw played section with highlight
        if cursor_x > 0:
            highlight = Image.new("RGBA", (cursor_x, waveform_height), (255, 255, 255, 30))
            img.paste(
                highlight,
                (0, y_center - waveform_height // 2),
                highlight,
            )

        return img

    def _draw_band(
        self,
        draw: ImageDraw.ImageDraw,
        envelope: NDArray,
        y_center: int,
        max_height: float,
        color: tuple[int, int, int, int],
    ) -> None:
        """Draw a frequency band on the waveform.

        Args:
            draw: ImageDraw object.
            envelope: Envelope data array.
            y_center: Y center position.
            max_height: Maximum height in pixels.
            color: RGBA color tuple.
        """
        half_height = max_height / 2

        for x, amplitude in enumerate(envelope):
            if x >= self.width:
                break

            bar_height = int(amplitude * half_height)
            if bar_height > 0:
                draw.line(
                    [(x, y_center - bar_height), (x, y_center + bar_height)],
                    fill=color,
                    width=1,
                )
