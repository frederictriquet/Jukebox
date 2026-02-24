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
    coarse_step: float = Field(gt=0, default=1.0)  # Seconds for Ctrl+Arrow
    fine_step: float = Field(gt=0, default=0.1)  # Seconds for Shift+Arrow


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
    hashtags: list[str] = []


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


class VJingEffectMappingConfig(BaseModel):
    """Configuration for VJing effect mapping by genre letter."""

    letter: str
    effects: list[str] = []  # List of effects for this genre letter

    # Support legacy single effect format
    effect: str | None = None  # Deprecated: use effects instead

    def get_effects(self) -> list[str]:
        """Get effects list, supporting both old and new format."""
        if self.effects:
            return self.effects
        if self.effect:
            return [self.effect]
        return []


class VJingPresetConfig(BaseModel):
    """Configuration for a VJing effects preset."""

    name: str  # Display name
    effects: list[str]  # List of effects in this preset
    description: str = ""  # Optional description


class VideoExporterConfig(BaseModel):
    """Video exporter configuration."""

    default_resolution: str = "1080p"  # 1080p, 720p, square_1080, square_720, vertical
    default_fps: int = Field(ge=15, le=60, default=30)
    output_directory: str = "~/Videos/Jukebox"
    video_clips_folder: str = ""
    intro_video_path: str = ""  # Overlay video that plays once on top
    # Layer defaults
    waveform_enabled: bool = True
    text_enabled: bool = True
    dynamics_enabled: bool = True
    vjing_enabled: bool = False
    video_background_enabled: bool = False
    # Waveform layer settings
    waveform_height_ratio: float = Field(ge=0.1, le=0.8, default=0.3)
    waveform_bass_color: str = "#0066FF"  # Blue
    waveform_mid_color: str = "#00FF00"  # Green
    waveform_treble_color: str = "#FFFFFF"  # White
    waveform_cursor_color: str = "#FFFFFF"  # White
    # VJing effect mappings
    vjing_mappings: list[VJingEffectMappingConfig] = [
        VJingEffectMappingConfig(letter="E", effect="strobe"),
        VJingEffectMappingConfig(letter="T", effect="glitch"),
        VJingEffectMappingConfig(letter="H", effect="fire"),
        VJingEffectMappingConfig(letter="R", effect="vinyl"),
        VJingEffectMappingConfig(letter="J", effect="neon"),
        VJingEffectMappingConfig(letter="C", effect="particles"),
        VJingEffectMappingConfig(letter="A", effect="wave"),
    ]
    # VJing presets (predefined effect combinations)
    vjing_presets: list[VJingPresetConfig] = []
    vjing_default_preset: str = ""  # Empty = use genre mappings
    # VJing simultaneous effects (how many effects are visible at once)
    vjing_simultaneous_effects: int = Field(ge=1, le=10, default=1)


class CueMakerConfig(BaseModel):
    """Cue Maker plugin configuration."""

    shazamix_db_path: Path = Field(default_factory=lambda: Path.home() / ".jukebox" / "jukebox.db")
    mix_directory: Path = Field(default_factory=lambda: Path.home() / "Music")
    segment_duration: float = Field(gt=0, default=60.0)
    overlap: float = Field(ge=0, default=15.0)
    max_workers: int = Field(ge=1, default=4)


class DirectoryNavigatorConfig(BaseModel):
    """Directory Navigator plugin configuration."""

    default_directory: str = "NORMALIZED"


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
    video_exporter: VideoExporterConfig = Field(default_factory=VideoExporterConfig)
    cue_maker: CueMakerConfig = Field(default_factory=CueMakerConfig)
    directory_navigator: DirectoryNavigatorConfig = Field(default_factory=DirectoryNavigatorConfig)
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
