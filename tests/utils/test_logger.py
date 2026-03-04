"""Tests for logging setup utilities."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jukebox.core.config import LoggingConfig
from jukebox.utils.logger import setup_logging


class TestSetupLogging:
    """Tests for setup_logging."""

    def test_setup_logging_debug_does_not_raise(self, tmp_path: Path) -> None:
        """setup_logging with DEBUG level runs without error."""
        config = LoggingConfig(level="DEBUG", file=str(tmp_path / "test.log"))
        with patch("logging.basicConfig"):
            setup_logging(config)  # Should not raise

    def test_setup_logging_info_does_not_raise(self, tmp_path: Path) -> None:
        """setup_logging with INFO level runs without error."""
        config = LoggingConfig(level="INFO", file=str(tmp_path / "test.log"))
        with patch("logging.basicConfig"):
            setup_logging(config)  # Should not raise

    def test_setup_logging_warning_does_not_raise(self, tmp_path: Path) -> None:
        """setup_logging with WARNING level runs without error."""
        config = LoggingConfig(level="WARNING", file=str(tmp_path / "test.log"))
        with patch("logging.basicConfig"):
            setup_logging(config)  # Should not raise

    def test_setup_logging_calls_basic_config(self, tmp_path: Path) -> None:
        """setup_logging calls logging.basicConfig exactly once."""
        config = LoggingConfig(level="INFO", file=str(tmp_path / "test.log"))

        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging(config)

        mock_basic_config.assert_called_once()

    def test_setup_logging_passes_correct_level(self, tmp_path: Path) -> None:
        """setup_logging passes the resolved integer level to basicConfig."""
        config = LoggingConfig(level="DEBUG", file=str(tmp_path / "test.log"))

        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging(config)

        call_kwargs = mock_basic_config.call_args.kwargs
        assert call_kwargs["level"] == logging.DEBUG

    def test_setup_logging_passes_info_level(self, tmp_path: Path) -> None:
        """setup_logging passes INFO integer level to basicConfig."""
        config = LoggingConfig(level="INFO", file=str(tmp_path / "test.log"))

        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging(config)

        call_kwargs = mock_basic_config.call_args.kwargs
        assert call_kwargs["level"] == logging.INFO

    def test_setup_logging_passes_warning_level(self, tmp_path: Path) -> None:
        """setup_logging passes WARNING integer level to basicConfig."""
        config = LoggingConfig(level="WARNING", file=str(tmp_path / "test.log"))

        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging(config)

        call_kwargs = mock_basic_config.call_args.kwargs
        assert call_kwargs["level"] == logging.WARNING

    def test_setup_logging_includes_file_handler(self, tmp_path: Path) -> None:
        """setup_logging passes a FileHandler pointing at config.file."""
        log_path = tmp_path / "test.log"
        config = LoggingConfig(level="INFO", file=str(log_path))

        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging(config)

        call_kwargs = mock_basic_config.call_args.kwargs
        handlers = call_kwargs["handlers"]
        file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1
        assert file_handlers[0].baseFilename == str(log_path)

    def test_setup_logging_includes_stream_handler(self, tmp_path: Path) -> None:
        """setup_logging passes a StreamHandler in the handlers list."""
        config = LoggingConfig(level="INFO", file=str(tmp_path / "test.log"))

        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging(config)

        call_kwargs = mock_basic_config.call_args.kwargs
        handlers = call_kwargs["handlers"]
        stream_handlers = [h for h in handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream_handlers) >= 1

    def test_setup_logging_creates_log_file(self, tmp_path: Path) -> None:
        """setup_logging creates the log file on disk when not mocked."""
        log_path = tmp_path / "real.log"
        config = LoggingConfig(level="WARNING", file=str(log_path))

        # Call without mocking to verify file creation; reset root logger afterwards
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        try:
            setup_logging(config)
            assert log_path.exists()
        finally:
            # Restore original handlers to avoid polluting other tests
            for handler in root_logger.handlers[:]:
                if handler not in original_handlers:
                    handler.close()
                    root_logger.removeHandler(handler)
            root_logger.handlers = original_handlers
