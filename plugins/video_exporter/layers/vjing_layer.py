"""VJing effects layer based on music genre."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image, ImageDraw

from plugins.video_exporter.layers.base import BaseVisualLayer

if TYPE_CHECKING:
    from numpy.typing import NDArray


class VJingLayer(BaseVisualLayer):
    """VJing visual effects based on genre letters.

    Supports multiple effects when genre contains multiple letters.
    """

    z_index = 4

    # Default effect mappings (based on genre_editor codes)
    DEFAULT_MAPPINGS = {
        "D": "wave",  # Deep - chill, ambient
        "C": "particles",  # Classic - elegant
        "P": "strobe",  # Power - energetic
        "T": "neon",  # Trance - hypnotic
        "H": "fire",  # House - groovy, warm
        "G": "particles",  # Garden - natural
        "I": "neon",  # Ibiza - club, colorful
        "A": "wave",  # A Cappella - soft
        "W": "wave",  # Weed - chill, relaxing
        "B": "glitch",  # Banger - intense
        "R": "vinyl",  # Retro - vintage
        "L": "wave",  # Loop - repetitive
        "O": "particles",  # Organic - natural
        "N": "wave",  # Namaste - zen, calm
    }

    def __init__(
        self,
        width: int,
        height: int,
        fps: int,
        audio: NDArray[np.floating],
        sr: int,
        duration: float,
        genre: str = "",
        effect_mappings: dict[str, str] | None = None,
        intensity: float = 0.7,
        **kwargs: Any,
    ) -> None:
        """Initialize VJing layer.

        Args:
            width: Frame width.
            height: Frame height.
            fps: Frames per second.
            audio: Audio samples.
            sr: Sample rate.
            duration: Duration in seconds.
            genre: Genre string (each letter can trigger an effect).
            effect_mappings: Custom letter to effect mappings.
            intensity: Effect intensity (0.0 to 1.0).
            **kwargs: Additional parameters.
        """
        self.genre = genre
        self.intensity = intensity
        self.effect_mappings = effect_mappings or self.DEFAULT_MAPPINGS

        # Determine which effects to use based on genre (can be multiple)
        self.active_effects = self._determine_effects()

        super().__init__(width, height, fps, audio, sr, duration, **kwargs)

    def _determine_effects(self) -> list[str]:
        """Determine which effects to use based on genre.

        Returns:
            List of effect names (unique).
        """
        if not self.genre:
            return ["wave"]  # Default effect

        effects = []
        seen = set()

        # Check each letter in the genre against mappings
        for letter in self.genre.upper():
            if letter in self.effect_mappings:
                effect = self.effect_mappings[letter]
                if effect not in seen:
                    effects.append(effect)
                    seen.add(effect)

        return effects if effects else ["wave"]

    def _precompute(self) -> None:
        """Pre-compute effect-specific data."""
        # Compute energy envelope for reactive effects
        samples_per_frame = len(self.audio) / self.total_frames
        self.energy = []

        for frame_idx in range(self.total_frames):
            start = int(frame_idx * samples_per_frame)
            end = int((frame_idx + 1) * samples_per_frame)
            chunk = self.audio[start:end]
            energy = np.sqrt(np.mean(chunk**2)) if len(chunk) > 0 else 0.0
            self.energy.append(energy)

        max_energy = max(self.energy) if max(self.energy) > 0 else 1.0
        self.energy = np.array(self.energy) / max_energy

        # Effect-specific initialization for all active effects
        if "particles" in self.active_effects:
            self._init_particles()

    def _init_particles(self) -> None:
        """Initialize particle system."""
        self.particles: list[dict[str, float]] = []
        self.max_particles = 50

        for _ in range(self.max_particles):
            self._spawn_particle()

    def _spawn_particle(self) -> None:
        """Spawn a new particle."""
        self.particles.append(
            {
                "x": random.random() * self.width,
                "y": random.random() * self.height,
                "vx": (random.random() - 0.5) * 2,
                "vy": (random.random() - 0.5) * 2,
                "size": random.random() * 10 + 5,
                "color": random.choice(
                    [(255, 100, 100), (100, 255, 100), (100, 100, 255), (255, 255, 100)]
                ),
                "life": random.random() * 100,
            }
        )

    def render(self, frame_idx: int, time_pos: float) -> Image.Image:
        """Render VJing effects for the current frame.

        Args:
            frame_idx: Frame index.
            time_pos: Time position in seconds.

        Returns:
            RGBA image with VJing effects.
        """
        img = self.create_transparent_image()

        # Get current energy
        safe_frame_idx = min(frame_idx, len(self.energy) - 1)
        energy = self.energy[safe_frame_idx]

        # Render all active effects (composited together)
        for effect_name in self.active_effects:
            effect_method = getattr(self, f"_render_{effect_name}", self._render_wave)
            effect_method(img, frame_idx, time_pos, energy)

        return img

    def _render_strobe(
        self, img: Image.Image, frame_idx: int, time_pos: float, energy: float
    ) -> None:
        """Render strobe effect.

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position.
            energy: Current energy level.
        """
        # Strobe flashes on beat
        if energy > 0.6 and frame_idx % 4 < 2:
            alpha = int(150 * energy * self.intensity)
            flash = Image.new("RGBA", (self.width, self.height), (255, 255, 255, alpha))
            img.paste(flash, (0, 0), flash)

    def _render_glitch(
        self, img: Image.Image, frame_idx: int, time_pos: float, energy: float
    ) -> None:
        """Render glitch effect.

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position.
            energy: Current energy level.
        """
        draw = ImageDraw.Draw(img)

        # Draw glitch lines
        n_lines = int(10 * energy * self.intensity)
        for _ in range(n_lines):
            y = random.randint(0, self.height)
            height = random.randint(2, 20)
            offset = random.randint(-50, 50)

            # Random color channel
            colors = [(255, 0, 0, 100), (0, 255, 0, 100), (0, 0, 255, 100)]
            color = random.choice(colors)

            draw.rectangle([offset, y, self.width + offset, y + height], fill=color)

    def _render_fire(
        self, img: Image.Image, frame_idx: int, time_pos: float, energy: float
    ) -> None:
        """Render fire/heat effect.

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position.
            energy: Current energy level.
        """
        draw = ImageDraw.Draw(img)

        # Draw fire-like gradient at bottom
        fire_height = int(self.height * 0.3 * energy * self.intensity)

        for y in range(fire_height):
            progress = y / max(fire_height, 1)
            # Gradient from yellow to red to transparent
            r = 255
            g = int(255 * (1 - progress * 0.7))
            b = 0
            a = int(100 * (1 - progress))

            # Add some noise
            noise = int(math.sin(time_pos * 10 + y * 0.1) * 20)
            wave_x = noise

            draw.line(
                [(wave_x, self.height - y), (self.width + wave_x, self.height - y)],
                fill=(r, g, b, a),
            )

    def _render_vinyl(
        self, img: Image.Image, frame_idx: int, time_pos: float, energy: float
    ) -> None:
        """Render vinyl/record effect.

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position.
            energy: Current energy level.
        """
        draw = ImageDraw.Draw(img)

        # Draw rotating circles like vinyl grooves
        center = (self.width // 2, self.height // 2)
        max_radius = min(self.width, self.height) // 3
        rotation = time_pos * 2 * math.pi  # One rotation per second

        n_grooves = 10
        for i in range(n_grooves):
            radius = max_radius * (i + 1) / n_grooves
            alpha = int(50 * self.intensity)

            # Draw partial arc
            start_angle = rotation + i * 0.3
            end_angle = start_angle + math.pi

            # Approximate arc with lines
            for angle in np.linspace(start_angle, end_angle, 20):
                x = center[0] + radius * math.cos(angle)
                y = center[1] + radius * math.sin(angle)
                draw.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(200, 200, 200, alpha))

    def _render_neon(
        self, img: Image.Image, frame_idx: int, time_pos: float, energy: float
    ) -> None:
        """Render neon glow effect.

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position.
            energy: Current energy level.
        """
        draw = ImageDraw.Draw(img)

        # Draw neon shapes
        colors = [
            (255, 0, 255, 150),  # Magenta
            (0, 255, 255, 150),  # Cyan
            (255, 255, 0, 150),  # Yellow
        ]

        n_shapes = 3
        for i in range(n_shapes):
            # Pulsating size
            base_size = 100 + i * 50
            pulse = math.sin(time_pos * 2 + i) * 20 * energy
            size = int((base_size + pulse) * self.intensity)

            x = self.width // 2 + math.cos(time_pos + i * 2) * 100
            y = self.height // 2 + math.sin(time_pos * 0.5 + i) * 50

            color = colors[i % len(colors)]

            # Draw glowing shape
            for offset in range(3, 0, -1):
                alpha = color[3] // offset
                draw.ellipse(
                    [
                        x - size - offset * 5,
                        y - size - offset * 5,
                        x + size + offset * 5,
                        y + size + offset * 5,
                    ],
                    outline=(*color[:3], alpha),
                    width=2,
                )

    def _render_particles(
        self, img: Image.Image, frame_idx: int, time_pos: float, energy: float
    ) -> None:
        """Render particle effect.

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position.
            energy: Current energy level.
        """
        draw = ImageDraw.Draw(img)

        # Update and draw particles
        for particle in self.particles:
            # Update position
            particle["x"] += particle["vx"] * (1 + energy * 2)
            particle["y"] += particle["vy"] * (1 + energy * 2)
            particle["life"] -= 1

            # Wrap around
            if particle["x"] < 0:
                particle["x"] = self.width
            elif particle["x"] > self.width:
                particle["x"] = 0
            if particle["y"] < 0:
                particle["y"] = self.height
            elif particle["y"] > self.height:
                particle["y"] = 0

            # Respawn if dead
            if particle["life"] <= 0:
                particle["life"] = random.random() * 100
                particle["x"] = random.random() * self.width
                particle["y"] = random.random() * self.height

            # Draw particle
            size = int(particle["size"] * (1 + energy * 0.5) * self.intensity)
            alpha = int(150 * self.intensity * (particle["life"] / 100))
            color = (*particle["color"], alpha)

            x, y = int(particle["x"]), int(particle["y"])
            draw.ellipse([x - size, y - size, x + size, y + size], fill=color)

    def _render_wave(
        self, img: Image.Image, frame_idx: int, time_pos: float, energy: float
    ) -> None:
        """Render wave effect (default).

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position.
            energy: Current energy level.
        """
        draw = ImageDraw.Draw(img)

        # Draw flowing waves
        n_waves = 5
        for i in range(n_waves):
            points = []
            phase = time_pos * 2 + i * 0.5
            amplitude = 30 * (1 + energy) * self.intensity

            for x in range(0, self.width, 5):
                y = self.height // 2 + math.sin(x * 0.02 + phase) * amplitude
                y += math.sin(x * 0.01 - time_pos) * amplitude * 0.5
                points.append((x, int(y)))

            if len(points) >= 2:
                alpha = int(100 * self.intensity / (i + 1))
                color = (100, 200, 255, alpha)
                draw.line(points, fill=color, width=2)
