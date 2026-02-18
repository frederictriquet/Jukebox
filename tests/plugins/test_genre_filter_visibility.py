"""Test that genre filter buttons are properly hidden/shown in different modes."""
from unittest.mock import Mock

from PySide6.QtWidgets import QHBoxLayout, QWidget

from plugins.genre_filter import GenreFilterPlugin


def test_genre_buttons_hidden_in_cue_maker_mode(qapp) -> None:  # type: ignore
    """Test that genre filter toolbar buttons are hidden in cue_maker mode."""
    # Setup genre_filter plugin
    genre_plugin = GenreFilterPlugin()
    mock_context = Mock()
    mock_config = Mock()

    class CodeConfig:
        def __init__(self, code: str, name: str):
            self.code = code
            self.name = name

    mock_config.genre_editor.codes = [
        CodeConfig("H", "House"),
        CodeConfig("D", "Deep"),
    ]
    mock_context.config = mock_config
    genre_plugin.context = mock_context

    # Simulate register_ui: create container and add to toolbar
    genre_plugin._create_container()
    assert genre_plugin.container is not None

    # Simulate toolbar: add container to a visible parent widget
    toolbar = QWidget()
    toolbar_layout = QHBoxLayout(toolbar)
    toolbar_layout.addWidget(genre_plugin.container)
    toolbar.show()  # Make toolbar visible

    # Now the container should be visible (it has a visible parent)
    assert genre_plugin.container.isVisible(), "Container should be visible when added to toolbar"

    # Activate in jukebox mode
    genre_plugin.activate("jukebox")
    assert genre_plugin.container.isVisible(), "Should be visible in jukebox mode"

    # Activate in cue_maker mode - THIS IS THE KEY TEST
    genre_plugin.activate("cue_maker")
    print(f"After activate('cue_maker'): container.isVisible() = {genre_plugin.container.isVisible()}")
    assert (
        not genre_plugin.container.isVisible()
    ), "Should be HIDDEN in cue_maker mode but it's still visible!"

    # Switch back to jukebox
    genre_plugin.activate("jukebox")
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
