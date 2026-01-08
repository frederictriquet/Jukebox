"""Pytest configuration and fixtures."""

import sys

import pytest
from PySide6.QtWidgets import QApplication


# Mock VLC module before any imports
@pytest.fixture(scope="session", autouse=True)
def mock_vlc():
    """Mock VLC module for tests without VLC installed."""
    if "vlc" not in sys.modules:
        from tests.mocks.mock_vlc import mock_vlc_module

        sys.modules["vlc"] = mock_vlc_module()
    return sys.modules["vlc"]


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # Don't quit app during tests to avoid issues
