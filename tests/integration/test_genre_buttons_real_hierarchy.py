"""Integration test: Genre buttons in real widget hierarchy.

Tests that:
1. Genre buttons are inside toolbar_container (not in a QToolBar)
2. toolbar_container has "Genres" label + buttons on same horizontal line
3. Drawer buttons are separate independent instances
"""

from unittest.mock import Mock

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from plugins.search_and_filter import SearchAndFilterPlugin


def find_all_genre_buttons(widget: QWidget, path: str = "root") -> list[tuple[QWidget, str]]:
    """Recursively find ALL genre buttons in widget tree with their paths."""
    buttons = []
    if isinstance(widget, QPushButton):
        text = widget.text()
        if len(text) == 1 and text.isalpha() and text.isupper():
            buttons.append((widget, f"{path}/{text}"))
    for i, child in enumerate(widget.children()):
        if isinstance(child, QWidget):
            child_path = f"{path}/{child.__class__.__name__}[{i}]"
            buttons.extend(find_all_genre_buttons(child, child_path))
    return buttons


def _make_plugin_with_codes(codes: list[tuple[str, str]]) -> SearchAndFilterPlugin:
    """Create a SearchAndFilterPlugin with mock context and given genre codes."""
    plugin = SearchAndFilterPlugin()

    class CodeConfig:
        def __init__(self, code: str, name: str):
            self.code = code
            self.name = name

    mock_context = Mock()
    mock_config = Mock()
    mock_config.genre_editor.codes = [CodeConfig(c, n) for c, n in codes]
    mock_context.config = mock_config
    plugin.context = mock_context
    return plugin


def test_toolbar_container_layout(qapp) -> None:  # type: ignore
    """Test that toolbar_container has 'Genres' label and buttons on same line."""
    plugin = _make_plugin_with_codes([
        ("H", "House"), ("D", "Deep"), ("T", "Trance"), ("W", "Weed"),
    ])
    plugin._create_toolbar_buttons()

    container = plugin.toolbar_container
    assert container is not None

    # Find genre buttons
    buttons = find_all_genre_buttons(container)
    assert len(buttons) == 4, f"Expected 4 buttons, found {len(buttons)}"

    # Find "Genres" label
    labels = container.findChildren(QLabel)
    genre_labels = [lb for lb in labels if lb.text() == "Genres"]
    assert len(genre_labels) == 1, "Should have one 'Genres' label"

    # Container should use QHBoxLayout (same line)
    from PySide6.QtWidgets import QHBoxLayout

    assert isinstance(container.layout(), QHBoxLayout), "Should use horizontal layout"


def test_toolbar_container_in_genre_buttons_area(qapp) -> None:  # type: ignore
    """Test that register_ui places toolbar_container into genre_buttons_area."""
    plugin = _make_plugin_with_codes([("H", "House"), ("D", "Deep")])

    # Simulate what main_window provides
    main_window = Mock()
    main_window.search_bar = Mock()
    main_window.search_bar.search_triggered = Mock()
    main_window.search_bar.search_triggered.connect = Mock()

    area = QWidget()
    area.setFixedHeight(0)  # Initially hidden like in _init_ui()
    main_window.genre_buttons_area = area

    track_list = Mock()
    main_window.track_list = track_list

    ui_builder = Mock()
    ui_builder.main_window = main_window

    plugin.context = Mock()
    plugin.context.config = Mock()

    class CodeConfig:
        def __init__(self, code: str, name: str):
            self.code = code
            self.name = name

    plugin.context.config.genre_editor.codes = [CodeConfig("H", "House"), CodeConfig("D", "Deep")]

    plugin.register_ui(ui_builder)

    # genre_buttons_area should now have content and height > 0
    assert area.maximumHeight() > 0, "genre_buttons_area should be visible after register_ui"
    buttons = find_all_genre_buttons(area)
    assert len(buttons) == 2, f"Expected 2 buttons in area, found {len(buttons)}"


def test_drawer_buttons_exist_independently(qapp) -> None:  # type: ignore
    """Verify drawer buttons are separate instances and work independently."""
    plugin = _make_plugin_with_codes([("H", "House"), ("D", "Deep")])
    plugin._create_toolbar_buttons()

    drawer_container = plugin.get_drawer_genre_buttons_container()
    assert drawer_container is not plugin.toolbar_container

    toolbar_btns = find_all_genre_buttons(plugin.toolbar_container)
    drawer_btns = find_all_genre_buttons(drawer_container)

    assert len(toolbar_btns) == 2
    assert len(drawer_btns) == 2

    # Different widget instances
    toolbar_widgets = {b[0] for b in toolbar_btns}
    drawer_widgets = {b[0] for b in drawer_btns}
    assert toolbar_widgets.isdisjoint(drawer_widgets), "Should be separate instances"
