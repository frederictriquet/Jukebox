"""Test that search and filter plugin works correctly across modes."""
from unittest.mock import Mock

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QToolBar, QWidget

from plugins.search_and_filter import SearchAndFilterPlugin, GenreFilterProxyModel


def test_genre_buttons_remain_in_toolbar_all_modes(qapp) -> None:  # type: ignore
    """Test that genre filter toolbar buttons remain in toolbar across all modes.

    In the new architecture, toolbar buttons stay in the toolbar always.
    Separate drawer buttons are created for cue_maker mode.
    """
    # Setup genre_filter plugin
    search_filter_plugin = SearchAndFilterPlugin()
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

    search_filter_plugin.context = mock_context

    # Simulate register_ui: create toolbar buttons
    search_filter_plugin._create_toolbar_buttons()
    assert search_filter_plugin.toolbar_container is not None

    # Add container to real toolbar
    toolbar.addWidget(search_filter_plugin.toolbar_container)

    # Store toolbar reference (normally done in register_ui)
    search_filter_plugin._toolbar = toolbar

    main_window.show()

    # Container should be visible (it has a visible parent)
    assert search_filter_plugin.toolbar_container.isVisible(), "Container should be visible when added to toolbar"

    # Activate in jukebox mode
    search_filter_plugin.activate("jukebox")
    assert search_filter_plugin.toolbar_container.isVisible(), "Should be visible in jukebox mode"
    assert search_filter_plugin.toolbar_container.parent() == toolbar, "Should remain in toolbar in jukebox mode"

    # Activate in cue_maker mode
    search_filter_plugin.activate("cue_maker")
    # Buttons are REMOVED from toolbar in cue_maker mode (shown in drawer instead)
    assert (
        search_filter_plugin.toolbar_container.parent() is None
    ), "Toolbar buttons container should be REMOVED from toolbar in cue_maker mode"
    assert not search_filter_plugin.toolbar_container.isVisible(), "Toolbar buttons should be hidden in cue_maker mode"

    # Switch back to jukebox
    search_filter_plugin.activate("jukebox")
    assert (
        search_filter_plugin.toolbar_container.parent() == toolbar
    ), "Should be RE-ADDED to toolbar in jukebox mode"
    assert (
        search_filter_plugin.toolbar_container.isVisible()
    ), "Should be visible again in jukebox mode"


def test_genre_buttons_clear_filter_on_deactivate(qapp) -> None:  # type: ignore
    """Test that genre filter is cleared when deactivating the plugin."""
    search_filter_plugin = SearchAndFilterPlugin()
    search_filter_plugin.proxy = GenreFilterProxyModel()

    # Set up some filter state
    search_filter_plugin.proxy.set_genre_filter({"H", "D"}, {"W"})
    assert search_filter_plugin.proxy._on_genres == {"H", "D"}
    assert search_filter_plugin.proxy._off_genres == {"W"}

    # Deactivate should clear the filter
    search_filter_plugin.deactivate("jukebox")

    # Filter should be cleared
    assert search_filter_plugin.proxy._on_genres == set()
    assert search_filter_plugin.proxy._off_genres == set()
