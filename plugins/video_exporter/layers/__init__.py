"""Visual layers for video export."""

from plugins.video_exporter.layers.base import BaseVisualLayer
from plugins.video_exporter.layers.dynamics_layer import DynamicsLayer
from plugins.video_exporter.layers.text_layer import TextLayer
from plugins.video_exporter.layers.video_layer import VideoBackgroundLayer
from plugins.video_exporter.layers.vjing_layer import VJingLayer
from plugins.video_exporter.layers.waveform_layer import WaveformLayer

LAYER_REGISTRY: dict[str, type[BaseVisualLayer]] = {
    "video_background": VideoBackgroundLayer,
    "waveform": WaveformLayer,
    "dynamics": DynamicsLayer,
    "vjing": VJingLayer,
    "text": TextLayer,
}

__all__ = [
    "BaseVisualLayer",
    "VideoBackgroundLayer",
    "WaveformLayer",
    "DynamicsLayer",
    "VJingLayer",
    "TextLayer",
    "LAYER_REGISTRY",
]
