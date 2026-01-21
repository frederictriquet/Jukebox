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
    mode: str = "jukebox"
    waveform_cache_size: int = Field(ge=10, le=10000, default=500)


class ShortcutsConfig(BaseModel):
    """Keyboard shortcuts configuration."""

    play_pause: str = "Space"
    pause: str = "Ctrl+P"
    stop: str = "Ctrl+S"
    volume_up: str = "Ctrl+Up"
    volume_down: str = "Ctrl+Down"
    quit: str = "Ctrl+Q"
    focus_search: str = "Ctrl+F"
    seek_forward: str = "Right"
    seek_backward: str = "Left"
    next_track: str = "Down"
    previous_track: str = "Up"
    skip_to_next: str = "Return"
    jump_20: str = ","
    jump_40: str = ";"
    jump_60: str = ":"
    jump_80: str = "="


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    file: str = "jukebox.log"


class PlaybackNavigationConfig(BaseModel):
    """Playback navigation configuration."""

    seek_amount: float = Field(gt=0, default=10.0)
    rapid_press_threshold: float = Field(gt=0, default=0.5)
    max_seek_multiplier: int = Field(ge=1, default=5)


class LoopPlayerConfig(BaseModel):
    """Loop player configuration."""

    duration: float = Field(gt=0, default=30.0)


class WaveformConfig(BaseModel):
    """Waveform visualization configuration."""

    bass_color: str = "#0066FF"
    mid_color: str = "#00FF00"
    treble_color: str = "#FFFFFF"
    cursor_color: str = "#FFFFFF"
    height: int = 120
    chunk_duration: float = Field(gt=0, default=10.0)


class AudioAnalysisConfig(BaseModel):
    """Audio analysis configuration."""

    enable_ml_features: bool = False  # Extract comprehensive ML features (slower)


class MetadataFieldConfig(BaseModel):
    """Configuration for a single metadata field."""

    tag: str
    label: str
    width: int | None = None


class MetadataEditorConfig(BaseModel):
    """Metadata editor configuration."""

    fields: list[MetadataFieldConfig] = [
        MetadataFieldConfig(tag="artist", label="Artist"),
        MetadataFieldConfig(tag="title", label="Title"),
        MetadataFieldConfig(tag="album", label="Album"),
        MetadataFieldConfig(tag="albumartist", label="Album Artist"),
        MetadataFieldConfig(tag="genre", label="Genre"),
        MetadataFieldConfig(tag="date", label="Year", width=80),
    ]


class GenreCodeConfig(BaseModel):
    """Configuration for a single genre code."""

    key: str
    code: str
    name: str


class GenreEditorConfig(BaseModel):
    """Genre editor configuration."""

    codes: list[GenreCodeConfig] = [
        GenreCodeConfig(key="D", code="D", name="Deep"),
        GenreCodeConfig(key="C", code="C", name="Classic"),
        GenreCodeConfig(key="P", code="P", name="Power"),
    ]
    rating_key: str = "*"


class FileManagerDestinationConfig(BaseModel):
    """Configuration for a file manager destination."""

    name: str
    path: str
    key: str


class FileManagerConfig(BaseModel):
    """File manager configuration."""

    destinations: list[FileManagerDestinationConfig] = []
    trash_directory: str = ""
    trash_key: str = "Delete"


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
    jukebox_mode: list[str] | None = None
    curating_mode: list[str] | None = None


class JukeboxConfig(BaseModel):
    """Main application configuration."""

    audio: AudioConfig
    ui: UIConfig
    shortcuts: ShortcutsConfig = Field(default_factory=ShortcutsConfig)
    playback_navigation: PlaybackNavigationConfig = Field(default_factory=PlaybackNavigationConfig)
    loop_player: LoopPlayerConfig = Field(default_factory=LoopPlayerConfig)
    waveform: WaveformConfig = Field(default_factory=WaveformConfig)
    audio_analysis: AudioAnalysisConfig = Field(default_factory=AudioAnalysisConfig)
    metadata_editor: MetadataEditorConfig = Field(default_factory=MetadataEditorConfig)
    genre_editor: GenreEditorConfig = Field(default_factory=GenreEditorConfig)
    file_manager: FileManagerConfig = Field(default_factory=FileManagerConfig)
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
