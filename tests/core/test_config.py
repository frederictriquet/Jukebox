"""Tests for configuration module."""

from pathlib import Path

import pytest

from jukebox.core.config import (
    AudioConfig,
    JukeboxConfig,
    LoggingConfig,
    UIConfig,
    load_config,
)


class TestAudioConfig:
    """Test AudioConfig validation."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = AudioConfig()
        assert config.default_volume == 70
        assert "mp3" in config.supported_formats
        assert "flac" in config.supported_formats

    def test_volume_validation_too_high(self) -> None:
        """Test volume validation rejects values > 100."""
        with pytest.raises(ValueError):
            AudioConfig(default_volume=150)

    def test_volume_validation_negative(self) -> None:
        """Test volume validation rejects negative values."""
        with pytest.raises(ValueError):
            AudioConfig(default_volume=-10)

    def test_valid_volume(self) -> None:
        """Test valid volume values."""
        config = AudioConfig(default_volume=50)
        assert config.default_volume == 50


class TestUIConfig:
    """Test UIConfig validation."""

    def test_default_values(self) -> None:
        """Test default UI configuration values."""
        config = UIConfig()
        assert config.window_title == "Jukebox"
        assert config.window_width == 1024
        assert config.window_height == 768
        assert config.theme == "dark"

    def test_window_size_validation(self) -> None:
        """Test window size validation."""
        with pytest.raises(ValueError):
            UIConfig(window_width=400)  # < 640

        with pytest.raises(ValueError):
            UIConfig(window_height=300)  # < 480


class TestLoggingConfig:
    """Test LoggingConfig."""

    def test_default_values(self) -> None:
        """Test default logging configuration values."""
        config = LoggingConfig()
        assert config.level == "INFO"
        assert config.file == "jukebox.log"


class TestJukeboxConfig:
    """Test full configuration."""

    def test_full_config(self) -> None:
        """Test complete configuration."""
        config = JukeboxConfig(
            audio=AudioConfig(),
            ui=UIConfig(),
            logging=LoggingConfig(),
        )

        assert config.audio.default_volume == 70
        assert config.ui.window_title == "Jukebox"
        assert config.logging.level == "INFO"


class TestLoadConfig:
    """Test configuration loading."""

    def test_load_config_success(self) -> None:
        """Test loading configuration from default location."""
        # This will use the actual config.yaml file
        config = load_config()

        assert isinstance(config, JukeboxConfig)
        assert isinstance(config.audio, AudioConfig)
        assert isinstance(config.ui, UIConfig)
        assert isinstance(config.logging, LoggingConfig)

    def test_load_config_missing_file(self, tmp_path: Path) -> None:
        """Test loading configuration from missing file."""
        nonexistent = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError):
            load_config(nonexistent)
