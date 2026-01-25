"""Protocol definitions for plugin type hints.

Using Protocol (structural subtyping) allows plugins to have proper
type hints without creating circular imports or tight coupling.
"""

from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QWidget

# ============================================================================
# Database Protocols
# ============================================================================


class TrackRepositoryProtocol(Protocol):
    """Protocol for track repository operations."""

    def add(self, track_data: dict[str, Any], mode: str = "jukebox") -> int: ...
    def search(self, query: str, limit: int = 100, mode: str | None = None) -> list[Any]: ...
    def get_all(self, limit: int | None = None, mode: str | None = None) -> list[Any]: ...
    def get_by_id(self, track_id: int) -> Any | None: ...
    def get_by_filepath(self, filepath: str | Path) -> Any | None: ...
    def delete(self, track_id: int) -> bool: ...
    def delete_by_filepath(self, filepath: str | Path) -> bool: ...
    def update_metadata(self, track_id: int, metadata: dict[str, Any]) -> bool: ...
    def update_filepath(
        self, track_id: int, new_filepath: str | Path, new_filename: str | None = None
    ) -> bool: ...
    def update_mode(self, track_id: int, mode: str) -> bool: ...
    def record_play(self, track_id: int, duration: float, completed: bool) -> None: ...


class WaveformRepositoryProtocol(Protocol):
    """Protocol for waveform repository operations."""

    def get(self, track_id: int) -> bytes | None: ...
    def save(self, track_id: int, waveform_data: bytes) -> None: ...
    def delete(self, track_id: int) -> None: ...
    def get_tracks_without_waveform(
        self, mode: str | None = None, limit: int | None = None
    ) -> list[Any]: ...


class AnalysisRepositoryProtocol(Protocol):
    """Protocol for analysis repository operations."""

    def get(self, track_id: int) -> Any | None: ...
    def save(self, track_id: int, analysis: dict[str, Any]) -> None: ...
    def delete(self, track_id: int) -> None: ...
    def exists(self, track_id: int) -> bool: ...
    def get_tracks_without_analysis(
        self, mode: str | None = None, limit: int | None = None
    ) -> list[Any]: ...


class SettingsRepositoryProtocol(Protocol):
    """Protocol for plugin settings repository operations."""

    def get(self, plugin_name: str, key: str) -> str | None: ...
    def save(self, plugin_name: str, key: str, value: str) -> None: ...


@runtime_checkable
class DatabaseProtocol(Protocol):
    """Protocol for database operations used by plugins."""

    @property
    def tracks(self) -> TrackRepositoryProtocol: ...

    @property
    def waveforms(self) -> WaveformRepositoryProtocol: ...

    @property
    def analysis(self) -> AnalysisRepositoryProtocol: ...

    @property
    def settings(self) -> SettingsRepositoryProtocol: ...

    def transaction(self) -> Generator[None, None, None]: ...


# ============================================================================
# Event Bus Protocol
# ============================================================================


@runtime_checkable
class EventBusProtocol(Protocol):
    """Protocol for event bus operations."""

    def emit(self, event: str, **data: Any) -> None: ...
    def subscribe(self, event: str, callback: Callable[..., None]) -> None: ...
    def unsubscribe(self, event: str, callback: Callable[..., None]) -> bool: ...


# ============================================================================
# Audio Player Protocol
# ============================================================================


@runtime_checkable
class AudioPlayerProtocol(Protocol):
    """Protocol for audio player operations used by plugins."""

    @property
    def current_file(self) -> Path | None: ...

    def load(self, filepath: Path) -> bool: ...
    def play(self) -> None: ...
    def pause(self) -> None: ...
    def stop(self) -> None: ...
    def set_volume(self, volume: int) -> None: ...
    def get_volume(self) -> int: ...
    def set_position(self, position: float) -> None: ...
    def get_position(self) -> float: ...
    def is_playing(self) -> bool: ...
    def unload(self) -> None: ...


# ============================================================================
# Shortcut Manager Protocol
# ============================================================================


@runtime_checkable
class ShortcutManagerProtocol(Protocol):
    """Protocol for shortcut manager operations."""

    def register(
        self, key_sequence: str, callback: Callable[[], None], plugin_name: str | None = None
    ) -> QShortcut: ...
    def unregister(self, key_sequence: str) -> bool: ...
    def is_registered(self, key_sequence: str) -> bool: ...
    def enable_for_plugin(self, plugin_name: str) -> None: ...
    def disable_for_plugin(self, plugin_name: str) -> None: ...


# ============================================================================
# Config Protocols
# ============================================================================


class WaveformConfigProtocol(Protocol):
    """Protocol for waveform configuration."""

    chunk_duration: float


class AudioAnalysisConfigProtocol(Protocol):
    """Protocol for audio analysis configuration."""

    tempo_range: tuple[int, int]


class FileManagerConfigProtocol(Protocol):
    """Protocol for file manager configuration."""

    trash_directory: str
    destinations: list[Any]


class UIConfigProtocol(Protocol):
    """Protocol for UI configuration."""

    theme: str
    mode: str
    waveform_cache_size: int


class LoopPlayerConfigProtocol(Protocol):
    """Protocol for loop player configuration."""

    duration: float
    coarse_step: float
    fine_step: float


class MetadataEditorConfigProtocol(Protocol):
    """Protocol for metadata editor configuration."""

    fields: list[Any]


class GenreEditorConfigProtocol(Protocol):
    """Protocol for genre editor configuration."""

    codes: list[Any]


class VideoExporterConfigProtocol(Protocol):
    """Protocol for video exporter configuration."""

    default_resolution: str
    default_fps: int
    output_directory: str
    video_clips_folder: str
    waveform_enabled: bool
    text_enabled: bool
    dynamics_enabled: bool
    vjing_enabled: bool
    video_background_enabled: bool
    vjing_mappings: list[Any]


class ShortcutsConfigProtocol(Protocol):
    """Protocol for shortcuts configuration."""

    seek_forward: str
    seek_backward: str


@runtime_checkable
class JukeboxConfigProtocol(Protocol):
    """Protocol for application configuration used by plugins."""

    waveform: WaveformConfigProtocol
    audio_analysis: AudioAnalysisConfigProtocol
    file_manager: FileManagerConfigProtocol
    ui: UIConfigProtocol
    loop_player: LoopPlayerConfigProtocol
    metadata_editor: MetadataEditorConfigProtocol
    genre_editor: GenreEditorConfigProtocol
    shortcuts: ShortcutsConfigProtocol
    video_exporter: VideoExporterConfigProtocol


# ============================================================================
# UI Builder Protocol
# ============================================================================


class MenuProtocol(Protocol):
    """Protocol for menu objects."""

    def addAction(self, text: str) -> Any: ...  # noqa: N802 (Qt method name)


@runtime_checkable
class UIBuilderProtocol(Protocol):
    """Protocol for UI builder operations."""

    main_window: Any  # MainWindow instance

    def add_menu(self, name: str) -> MenuProtocol: ...
    def get_or_create_menu(self, name: str) -> MenuProtocol: ...
    def add_menu_action(
        self,
        menu: MenuProtocol,
        text: str,
        callback: Callable[[], None],
        shortcut: str | None = None,
    ) -> Any: ...
    def add_menu_separator(self, menu: MenuProtocol) -> None: ...
    def add_toolbar_widget(self, widget: QWidget) -> None: ...
    def add_sidebar_widget(self, widget: QWidget, title: str) -> None: ...
    def add_bottom_widget(self, widget: QWidget) -> None: ...
    def insert_widget_in_layout(self, layout: Any, index: int, widget: QWidget) -> None: ...
    def get_main_layout(self) -> Any: ...

    # Track context menu actions
    def add_track_context_action(
        self,
        text: str,
        callback: Callable[[dict[str, Any]], None],
        icon: str | None = None,
        separator_before: bool = False,
    ) -> Any: ...
    def get_track_context_actions(self) -> list[Any]: ...
    def clear_track_context_actions(self) -> None: ...


# ============================================================================
# Plugin Context Protocol (combines all the above)
# ============================================================================


@runtime_checkable
class PluginContextProtocol(Protocol):
    """Protocol for the plugin context provided to all plugins.

    This defines the interface that plugins can rely on for accessing
    application services.
    """

    app: Any  # MainWindow instance (for advanced plugin access)
    database: DatabaseProtocol
    player: AudioPlayerProtocol
    config: JukeboxConfigProtocol
    event_bus: EventBusProtocol | None

    def emit(self, event: str, **data: Any) -> None: ...
    def subscribe(self, event: str, callback: Callable[..., None]) -> None: ...
