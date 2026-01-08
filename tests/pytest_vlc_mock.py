"""Pytest plugin to mock VLC before any imports."""

import sys


def pytest_configure(config):
    """Configure pytest - mock VLC module before any test imports."""
    if "vlc" not in sys.modules:
        from tests.mocks.mock_vlc import mock_vlc_module

        sys.modules["vlc"] = mock_vlc_module()
