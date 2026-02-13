"""Text overlay layer for artist and title display."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from plugins.video_exporter.layers.base import BaseVisualLayer

if TYPE_CHECKING:
    from numpy.typing import NDArray


class TextLayer(BaseVisualLayer):
    """Text overlay layer displaying artist and title with animations."""

    z_index = 5

    # Default styling
    DEFAULT_FONT_SIZE = 48
    TITLE_COLOR = (255, 255, 255, 255)  # White
    ARTIST_COLOR = (200, 200, 200, 255)  # Light gray
    SHADOW_COLOR = (0, 0, 0, 128)  # Semi-transparent black

    def __init__(
        self,
        width: int,
        height: int,
        fps: int,
        audio: NDArray[np.floating],
        sr: int,
        duration: float,
        artist: str = "Unknown",
        title: str = "Unknown",
        font_size: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize text layer.

        Args:
            width: Frame width.
            height: Frame height.
            fps: Frames per second.
            audio: Audio samples.
            sr: Sample rate.
            duration: Duration in seconds.
            artist: Artist name.
            title: Track title.
            font_size: Font size (auto-scaled if None).
            **kwargs: Additional parameters.
        """
        self.artist = artist
        self.title = title

        # Auto-scale font size based on resolution
        if font_size is None:
            self.font_size = max(24, min(72, width // 25))
        else:
            self.font_size = font_size

        # Animation timing
        self.fade_in_duration = 1.0  # seconds
        self.fade_out_start = duration - 1.0  # Start fade out 1s before end

        super().__init__(width, height, fps, audio, sr, duration, **kwargs)

    def _precompute(self) -> None:
        """Pre-load fonts."""
        # Try to load a nice font, fallback to default
        try:
            # Try common system fonts
            font_paths = [
                "/System/Library/Fonts/Helvetica.ttc",  # macOS
                "/System/Library/Fonts/SFNSDisplay.ttf",  # macOS San Francisco
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
                "C:\\Windows\\Fonts\\arial.ttf",  # Windows
            ]

            self.title_font = None
            self.artist_font = None

            for font_path in font_paths:
                try:
                    self.title_font = ImageFont.truetype(font_path, self.font_size)
                    self.artist_font = ImageFont.truetype(font_path, int(self.font_size * 0.7))
                    break
                except OSError:
                    continue

            if self.title_font is None:
                # Use default font
                self.title_font = ImageFont.load_default()
                self.artist_font = ImageFont.load_default()

        except Exception:
            self.title_font = ImageFont.load_default()
            self.artist_font = ImageFont.load_default()

    def render(self, frame_idx: int, time_pos: float) -> Image.Image:
        """Render text overlay for the current frame.

        Args:
            frame_idx: Frame index.
            time_pos: Time position in seconds.

        Returns:
            RGBA image with text overlay.
        """
        img = self.create_transparent_image()
        draw = ImageDraw.Draw(img)

        # Calculate fade alpha
        alpha = self._calculate_alpha(time_pos)

        # Apply subtle bounce animation at start
        y_offset = self._calculate_bounce(time_pos)

        # Calculate text positions
        margin = 40
        text_y = margin + y_offset

        # Get text bounding boxes
        title_bbox = draw.textbbox((0, 0), self.title, font=self.title_font)
        title_height = title_bbox[3] - title_bbox[1]

        # Position text (top-left with margin)
        title_x = margin
        artist_x = margin
        artist_y = text_y + title_height + 10

        # Apply alpha to colors
        title_color = (*self.TITLE_COLOR[:3], int(self.TITLE_COLOR[3] * alpha))
        artist_color = (*self.ARTIST_COLOR[:3], int(self.ARTIST_COLOR[3] * alpha))
        shadow_color = (*self.SHADOW_COLOR[:3], int(self.SHADOW_COLOR[3] * alpha))

        # Draw shadow (offset by 2 pixels)
        shadow_offset = 2
        draw.text(
            (title_x + shadow_offset, text_y + shadow_offset),
            self.title,
            font=self.title_font,
            fill=shadow_color,
        )
        draw.text(
            (artist_x + shadow_offset, artist_y + shadow_offset),
            self.artist,
            font=self.artist_font,
            fill=shadow_color,
        )

        # Draw text
        draw.text((title_x, text_y), self.title, font=self.title_font, fill=title_color)
        draw.text((artist_x, artist_y), self.artist, font=self.artist_font, fill=artist_color)

        return img

    def _calculate_alpha(self, time_pos: float) -> float:
        """Calculate fade alpha based on time position.

        Args:
            time_pos: Time position in seconds.

        Returns:
            Alpha value (0.0 to 1.0).
        """
        # Fade in
        if time_pos < self.fade_in_duration:
            return time_pos / self.fade_in_duration

        # Fade out
        if time_pos > self.fade_out_start:
            remaining = self.duration - time_pos
            return max(0.0, remaining / (self.duration - self.fade_out_start))

        # Full opacity
        return 1.0

    def _calculate_bounce(self, time_pos: float) -> int:
        """Calculate bounce animation offset.

        Args:
            time_pos: Time position in seconds.

        Returns:
            Y offset in pixels.
        """
        if time_pos > self.fade_in_duration:
            return 0

        # Ease-out bounce
        progress = time_pos / self.fade_in_duration
        # Start from -20 pixels, settle at 0
        bounce = -20 * (1 - progress) * math.cos(progress * math.pi * 2)
        return int(bounce * (1 - progress))
