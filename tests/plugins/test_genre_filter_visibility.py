"""Test that genre filter buttons are properly hidden/shown in different modes."""
from unittest.mock import Mock

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QToolBar, QWidget

from plugins.genre_filter import GenreFilterPlugin


def test_genre_buttons_hidden_in_cue_maker_mode(qapp) -> None:  # type: ignore
    """Test that genre filter toolbar buttons are hidden in cue_maker mode."""
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

    # Now the container should be visible (it has a visible parent)
    assert genre_plugin.container.isVisible(), "Container should be visible when added to toolbar"

    # Activate in jukebox mode
    genre_plugin.activate("jukebox")
    assert genre_plugin.container.isVisible(), "Should be visible in jukebox mode"
    assert genre_plugin.container.parent() == toolbar, "Should be in toolbar in jukebox mode"

    # Activate in cue_maker mode - THIS IS THE KEY TEST
    genre_plugin.activate("cue_maker")
    print(f"After activate('cue_maker'): container.parent() = {genre_plugin.container.parent()}")
    print(f"After activate('cue_maker'): container.isVisible() = {genre_plugin.container.isVisible()}")
    assert (
        genre_plugin.container.parent() is None
    ), "Should be REMOVED from toolbar in cue_maker mode"

    # Switch back to jukebox
    genre_plugin.activate("jukebox")
    assert (
        genre_plugin.container.parent() == toolbar
    ), "Should be back in toolbar in jukebox mode"
    assert (
        genre_plugin.container.isVisible()
    ), "Should be visible again in jukebox mode"


def test_genre_buttons_hidden_in_curating_mode(qapp) -> None:  # type: ignore
    """Test that genre filter buttons are hidden in curating mode."""
    genre_plugin = GenreFilterPlugin()
    mock_context = Mock()
    mock_config = Mock()

    class CodeConfig:
        def __init__(self, code: str, name: str):
            self.code = code
            self.name = name

    mock_config.genre_editor.codes = [CodeConfig("H", "House")]
    mock_context.config = mock_config
    genre_plugin.context = mock_context

    genre_plugin._create_container()

    # Add to visible parent
    toolbar = QWidget()
    toolbar_layout = QHBoxLayout(toolbar)
    toolbar_layout.addWidget(genre_plugin.container)
    toolbar.show()

    # Activate in jukebox mode
    genre_plugin.activate("jukebox")
    assert genre_plugin.container.isVisible()

    # Deactivate (curating mode is not in modes list, so deactivate is called)
    genre_plugin.deactivate("jukebox")
    assert not genre_plugin.container.isVisible()
