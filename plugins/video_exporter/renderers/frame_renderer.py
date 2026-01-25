"""Frame renderer for compositing visual layers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from plugins.video_exporter.layers.base import BaseVisualLayer


class FrameRenderer:
    """Compositor for rendering frames from multiple visual layers."""

    def __init__(
        self,
        width: int,
        height: int,
        fps: int,
        audio: NDArray[np.floating],
        sr: int,
        duration: float,
        layers_config: dict[str, bool],
        track_metadata: dict[str, Any],
        video_clips_folder: str = "",
        vjing_mappings: dict[str, str] | None = None,
        waveform_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize frame renderer.

        Args:
            width: Frame width in pixels.
            height: Frame height in pixels.
            fps: Frames per second.
            audio: Audio samples as numpy array.
            sr: Sample rate.
            duration: Duration in seconds.
            layers_config: Dictionary of layer_name -> enabled.
            track_metadata: Track metadata dictionary.
            video_clips_folder: Path to folder with video clips for background.
            vjing_mappings: Genre letter to effect mapping.
            waveform_config: Waveform layer configuration (height_ratio, colors).
        """
        self.width = width
        self.height = height
        self.fps = fps
        self.audio = audio
        self.sr = sr
        self.duration = duration
        self.track_metadata = track_metadata
        self.video_clips_folder = video_clips_folder
        self.vjing_mappings = vjing_mappings or {}
        self.waveform_config = waveform_config or {}

        # Initialize enabled layers
        self.layers: list[BaseVisualLayer] = []
        self._init_layers(layers_config)

        logging.info(f"[Frame Renderer] Initialized with {len(self.layers)} layers")

    def _get_metadata(self, key: str, default: str = "") -> str:
        """Get metadata value safely from sqlite3.Row or dict.

        Args:
            key: Metadata key to retrieve.
            default: Default value if key not found.

        Returns:
            Metadata value or default.
        """
        try:
            value = self.track_metadata[key]
            return value if value else default
        except (KeyError, IndexError, TypeError):
            return default

    def _init_layers(self, layers_config: dict[str, bool]) -> None:
        """Initialize visual layers based on configuration.

        Args:
            layers_config: Dictionary of layer_name -> enabled.
        """
        # Common kwargs for all layers
        common_kwargs = {
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "audio": self.audio,
            "sr": self.sr,
            "duration": self.duration,
        }

        # Import layers lazily
        if layers_config.get("video_background", False) and self.video_clips_folder:
            try:
                from plugins.video_exporter.layers.video_layer import VideoBackgroundLayer

                layer = VideoBackgroundLayer(
                    **common_kwargs,
                    video_folder=self.video_clips_folder,
                )
                self.layers.append(layer)
                logging.info("[Frame Renderer] Video background layer enabled")
            except Exception as e:
                logging.warning(f"[Frame Renderer] Failed to init video layer: {e}")

        if layers_config.get("waveform", False):
            try:
                from plugins.video_exporter.layers.waveform_layer import WaveformLayer

                layer = WaveformLayer(
                    **common_kwargs,
                    waveform_height_ratio=self.waveform_config.get("height_ratio", 0.3),
                    bass_color=self.waveform_config.get("bass_color"),
                    mid_color=self.waveform_config.get("mid_color"),
                    treble_color=self.waveform_config.get("treble_color"),
                    cursor_color=self.waveform_config.get("cursor_color"),
                )
                self.layers.append(layer)
                logging.info("[Frame Renderer] Waveform layer enabled")
            except Exception as e:
                logging.warning(f"[Frame Renderer] Failed to init waveform layer: {e}")

        if layers_config.get("dynamics", False):
            try:
                from plugins.video_exporter.layers.dynamics_layer import DynamicsLayer

                layer = DynamicsLayer(**common_kwargs)
                self.layers.append(layer)
                logging.info("[Frame Renderer] Dynamics layer enabled")
            except Exception as e:
                logging.warning(f"[Frame Renderer] Failed to init dynamics layer: {e}")

        if layers_config.get("vjing", False):
            try:
                from plugins.video_exporter.layers.vjing_layer import VJingLayer

                # Get genre from metadata
                genre = self._get_metadata("genre", "")
                logging.info(
                    f"[Frame Renderer] VJing: genre='{genre}', mappings={self.vjing_mappings}"
                )
                layer = VJingLayer(
                    **common_kwargs,
                    genre=genre,
                    effect_mappings=self.vjing_mappings,
                )
                self.layers.append(layer)
                logging.info("[Frame Renderer] VJing layer enabled")
            except Exception as e:
                logging.warning(f"[Frame Renderer] Failed to init vjing layer: {e}")

        if layers_config.get("text", False):
            try:
                from plugins.video_exporter.layers.text_layer import TextLayer

                layer = TextLayer(
                    **common_kwargs,
                    artist=self._get_metadata("artist", "Unknown"),
                    title=self._get_metadata("title", "Unknown"),
                )
                self.layers.append(layer)
                logging.info("[Frame Renderer] Text layer enabled")
            except Exception as e:
                logging.warning(f"[Frame Renderer] Failed to init text layer: {e}")

        # Sort by z-index
        self.layers.sort(key=lambda layer: layer.z_index)

    def render_frame(self, frame_idx: int, time_pos: float) -> NDArray[np.uint8]:
        """Render a single frame by compositing all layers.

        Args:
            frame_idx: Frame index.
            time_pos: Time position in seconds.

        Returns:
            RGB frame as numpy array (height, width, 3).
        """
        # Start with black background
        composite = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 255))

        # Render and composite each layer
        for layer in self.layers:
            try:
                layer_image = layer.render(frame_idx, time_pos)
                if layer_image.mode != "RGBA":
                    layer_image = layer_image.convert("RGBA")
                composite = Image.alpha_composite(composite, layer_image)
            except Exception as e:
                logging.warning(f"[Frame Renderer] Layer {layer.__class__.__name__} failed: {e}")

        # Convert to RGB numpy array
        rgb = composite.convert("RGB")
        return np.array(rgb, dtype=np.uint8)
