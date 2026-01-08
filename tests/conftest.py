"""Pytest configuration and fixtures."""

import pytest
from PySide6.QtWidgets import QApplication

# Register pytest plugin for VLC mocking
pytest_plugins = ["tests.pytest_vlc_mock"]


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # Don't quit app during tests to avoid issues
