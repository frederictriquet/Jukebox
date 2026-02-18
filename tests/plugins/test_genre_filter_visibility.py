"""Test that genre filter buttons are properly hidden/shown in different modes."""
from unittest.mock import Mock

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QToolBar, QWidget

from plugins.genre_filter import GenreFilterPlugin, GenreFilterProxyModel


def test_genre_buttons_remain_in_toolbar_all_modes(qapp) -> None:  # type: ignore
    """Test that genre filter toolbar buttons remain in toolbar across all modes.

    In the new architecture, toolbar buttons stay in the toolbar always.
    Separate drawer buttons are created for cue_maker mode.
    """
    # Setup genre_filter plugin
    genre_plugin = GenreFilterPlugin()
    mock_context = Mock()
    mock_config = Mock()
    mock_app = Mock()
    mock_main_window = Mock()

    class CodeConfig:
        def __init__(self, code: str, name: str):
            self.code = code
            self.name = name

    mock_config.genre_editor.codes = [
        CodeConfig("H", "House"),
        CodeConfig("D", "Deep"),
    ]
    mock_context.config = mock_config
    mock_context.app = mock_app

    # Create real toolbar for testing
    main_window = QMainWindow()
    toolbar = QToolBar("Test Toolbar")
    main_window.addToolBar(toolbar)
    mock_main_window._plugin_toolbar = toolbar
    mock_app.main_window = mock_main_window

    genre_plugin.context = mock_context

    # Simulate register_ui: create container and add to toolbar
    genre_plugin._create_container()
    assert genre_plugin.container is not None

    # Add container to real toolbar
    toolbar.addWidget(genre_plugin.container)
    main_window.show()

    # Container should be visible (it has a visible parent)
    assert genre_plugin.container.isVisible(), "Container should be visible when added to toolbar"

    # Activate in jukebox mode
    genre_plugin.activate("jukebox")
    assert genre_plugin.container.isVisible(), "Should be visible in jukebox mode"
    assert genre_plugin.container.parent() == toolbar, "Should remain in toolbar in jukebox mode"

    # Activate in cue_maker mode
    genre_plugin.activate("cue_maker")
    # Buttons should still be in toolbar (not removed)
    assert (
        genre_plugin.container.parent() == toolbar
    ), "Toolbar buttons should remain in toolbar in cue_maker mode"
    assert genre_plugin.container.isVisible(), "Toolbar buttons should remain visible"

    # Switch back to jukebox
    genre_plugin.activate("jukebox")
    assert (
        genre_plugin.container.parent() == toolbar
    ), "Should still be in toolbar in jukebox mode"
    assert (
        genre_plugin.container.isVisible()
    ), "Should still be visible in jukebox mode"


def test_genre_buttons_clear_filter_on_deactivate(qapp) -> None:  # type: ignore
    """Test that genre filter is cleared when deactivating the plugin."""
    genre_plugin = GenreFilterPlugin()
    genre_plugin.proxy = GenreFilterProxyModel()

    # Set up some filter state
    genre_plugin.proxy.set_filter({"H", "D"}, {"W"})
    assert genre_plugin.proxy._on_genres == {"H", "D"}
    assert genre_plugin.proxy._off_genres == {"W"}

    # Deactivate should clear the filter
    genre_plugin.deactivate("jukebox")

    # Filter should be cleared
    assert genre_plugin.proxy._on_genres == set()
    assert genre_plugin.proxy._off_genres == set()
