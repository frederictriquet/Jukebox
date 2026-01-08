"""Logging utilities."""

import logging

from jukebox.core.config import LoggingConfig


def setup_logging(config: LoggingConfig) -> None:
    """Setup application logging.

    Args:
        config: Logging configuration
    """
    logging.basicConfig(
        level=getattr(logging, config.level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(config.file), logging.StreamHandler()],
    )
