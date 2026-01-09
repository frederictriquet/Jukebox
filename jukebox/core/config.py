"""Configuration management using Pydantic and YAML."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class AudioConfig(BaseModel):
    """Audio configuration."""

    default_volume: int = Field(ge=0, le=100, default=70)
    supported_formats: list[str] = ["mp3", "flac", "aiff", "aif", "wav"]
    music_directory: Path = Field(default_factory=lambda: Path.home() / "Music")


class UIConfig(BaseModel):
    """UI configuration."""

    window_title: str = "Jukebox"
    window_width: int = Field(ge=640, default=1024)
    window_height: int = Field(ge=480, default=768)
    theme: str = "dark"


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    file: str = "jukebox.log"


class WaveformConfig(BaseModel):
    """Waveform visualization configuration."""

    bass_color: str = "#0066FF"
    mid_color: str = "#00FF00"
    treble_color: str = "#FFFFFF"
    cursor_color: str = "#FFFFFF"
    height: int = 120


class PluginsConfig(BaseModel):
    """Plugins configuration."""

    enabled: list[str] = [
        "stats_plugin",
        "playlists_plugin",
        "duplicate_finder",
        "recommendations",
        "file_curator",
        "waveform_visualizer",
    ]


class JukeboxConfig(BaseModel):
    """Main application configuration."""

    audio: AudioConfig
    ui: UIConfig
    waveform: WaveformConfig = Field(default_factory=WaveformConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    logging: LoggingConfig


def load_config(config_path: Path | None = None) -> JukeboxConfig:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config file. If None, uses default location.

    Returns:
        JukeboxConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config file is invalid
    """
    if config_path is None:
        # Try multiple locations
        possible_paths = [
            Path(__file__).parent.parent.parent / "config" / "config.yaml",
            Path.home() / ".config" / "jukebox" / "config.yaml",
            Path.home() / ".jukebox" / "config.yaml",
        ]

        for path in possible_paths:
            if path.exists():
                config_path = path
                break
        else:
            # Use default from package
            config_path = possible_paths[0]

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    return JukeboxConfig(**data)
