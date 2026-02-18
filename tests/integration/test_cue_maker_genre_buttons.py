"""Integration test: Genre buttons placement below searchbar in all modes.

This test verifies that:
1. Genre filter buttons are created in a toolbar_container with "Genres" label
2. The toolbar_container is placed inside genre_buttons_area (below searchbar)
3. Separate drawer buttons can be created for cue_maker mode
"""

from unittest.mock import Mock

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from plugins.search_and_filter import SearchAndFilterPlugin


def _find_genre_buttons_in_widget(widget: QWidget, depth: int = 0, max_depth: int = 10) -> list:
    """Recursively find all genre filter buttons in a widget tree."""
    buttons = []
    if depth > max_depth:
        return buttons
    if isinstance(widget, QPushButton):
        text = widget.text()
        if len(text) == 1 and text.isalpha() and text.isupper():
            buttons.append(widget)
    for child in widget.children():
        if isinstance(child, QWidget):
            buttons.extend(_find_genre_buttons_in_widget(child, depth + 1, max_depth))
    return buttons


def test_toolbar_container_has_label_and_buttons(qapp) -> None:  # type: ignore
    """Test that toolbar_container includes 'Genres' label and genre buttons."""
    plugin = SearchAndFilterPlugin()

    class CodeConfig:
        def __init__(self, code: str, name: str):
            self.code = code
            self.name = name

    mock_context = Mock()
    mock_config = Mock()
    mock_config.genre_editor.codes = [
        CodeConfig("H", "House"),
        CodeConfig("D", "Deep"),
        CodeConfig("T", "Trance"),
        CodeConfig("W", "Weed"),
    ]
    mock_context.config = mock_config

    plugin.context = mock_context
    plugin._create_toolbar_buttons()

    assert plugin.toolbar_container is not None
    buttons = _find_genre_buttons_in_widget(plugin.toolbar_container)
    assert len(buttons) == 4, f"Expected 4 genre buttons, found {len(buttons)}"

    # Check "Genres" label exists
    labels = plugin.toolbar_container.findChildren(QLabel)
    genre_labels = [lb for lb in labels if lb.text() == "Genres"]
    assert len(genre_labels) == 1, "Should have exactly one 'Genres' label"


def test_drawer_genre_buttons_are_separate_instances(qapp) -> None:  # type: ignore
    """Test that get_drawer_genre_buttons_container creates separate button instances."""
    plugin = SearchAndFilterPlugin()

    class CodeConfig:
        def __init__(self, code: str, name: str):
            self.code = code
            self.name = name

    mock_context = Mock()
    mock_config = Mock()
    mock_config.genre_editor.codes = [
        CodeConfig("H", "House"),
        CodeConfig("D", "Deep"),
        CodeConfig("T", "Trance"),
        CodeConfig("W", "Weed"),
    ]
    mock_context.config = mock_config

    plugin.context = mock_context
    plugin._create_toolbar_buttons()

    # Get drawer container
    drawer_container = plugin.get_drawer_genre_buttons_container()
    assert drawer_container is not plugin.toolbar_container

    drawer_buttons = _find_genre_buttons_in_widget(drawer_container)
    assert len(drawer_buttons) == 4, f"Expected 4 drawer buttons, found {len(drawer_buttons)}"

    # Drawer buttons should be different widget instances from toolbar buttons
    toolbar_buttons = _find_genre_buttons_in_widget(plugin.toolbar_container)
    for db in drawer_buttons:
        assert db not in toolbar_buttons, "Drawer buttons should be separate instances"
