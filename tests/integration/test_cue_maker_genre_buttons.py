"""Integration test: Genre buttons visibility in cue_maker mode.

This test verifies that:
1. Genre filter buttons appear in toolbar in jukebox mode
2. Genre filter buttons are hidden in toolbar in cue_maker mode
3. Genre filter buttons can be created independently for drawer in cue_maker mode
"""

from unittest.mock import Mock

from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QToolBar

from plugins.search_and_filter import SearchAndFilterPlugin


def _find_genre_buttons_in_widget(widget: QWidget, depth: int = 0, max_depth: int = 10) -> list:
    """Recursively find all genre filter buttons in a widget tree.

    Genre buttons have a text that is a single letter (A-Z) and are QPushButton instances.
    """
    buttons = []

    if depth > max_depth:
        return buttons

    # Check if this widget is a genre button
    from PySide6.QtWidgets import QPushButton

    if isinstance(widget, QPushButton):
        text = widget.text()
        # Genre button: single letter, typically A-W
        if len(text) == 1 and text.isalpha() and text.isupper():
            buttons.append(widget)

    # Recurse into children
    for child in widget.children():
        if isinstance(child, QWidget):
            buttons.extend(_find_genre_buttons_in_widget(child, depth + 1, max_depth))

    return buttons


def test_genre_buttons_visibility_in_modes(qapp) -> None:  # type: ignore
    """Test that genre buttons visibility toggles correctly with mode changes."""
    # Create main window with toolbar
    main_window = QMainWindow()
    plugin_toolbar = QToolBar("Plugins")
    main_window.addToolBar(plugin_toolbar)

    central = QWidget()
    central_layout = QVBoxLayout(central)
    main_window.setCentralWidget(central)

    # Show window so widgets become visible
    main_window.show()

    # Initialize search_and_filter plugin
    search_filter_plugin = SearchAndFilterPlugin()

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
    mock_app = Mock()
    mock_app.main_window = main_window
    mock_context.app = mock_app

    search_filter_plugin.context = mock_context

    # Create toolbar buttons
    search_filter_plugin._create_toolbar_buttons()
    plugin_toolbar.addWidget(search_filter_plugin.toolbar_container)

    # --- JUKEBOX MODE ---
    print("\n→ Testing JUKEBOX mode...")
    search_filter_plugin.activate("jukebox")

    # Verify buttons are visible in toolbar
    buttons_in_toolbar = _find_genre_buttons_in_widget(search_filter_plugin.toolbar_container)
    print(f"  Buttons in toolbar: {len(buttons_in_toolbar)}")
    print(f"  Toolbar container visible: {search_filter_plugin.toolbar_container.isVisible()}")

    assert len(buttons_in_toolbar) == 4, f"Expected 4 genre buttons in toolbar, found {len(buttons_in_toolbar)}"
    assert (
        search_filter_plugin.toolbar_container.isVisible()
    ), "Toolbar buttons should be visible in jukebox mode"

    # --- CUE_MAKER MODE ---
    print("\n→ Testing CUE_MAKER mode...")
    search_filter_plugin.activate("cue_maker")

    # Verify toolbar buttons are hidden
    print(f"  Toolbar container visible: {search_filter_plugin.toolbar_container.isVisible()}")
    assert (
        not search_filter_plugin.toolbar_container.isVisible()
    ), "❌ Toolbar buttons should be HIDDEN in cue_maker mode!"

    # Create separate drawer buttons
    drawer_buttons = search_filter_plugin.get_button_container()
    buttons_in_drawer = _find_genre_buttons_in_widget(drawer_buttons)
    print(f"  Buttons in drawer container: {len(buttons_in_drawer)}")

    assert len(buttons_in_drawer) == 4, f"Expected 4 buttons in drawer, found {len(buttons_in_drawer)}"
    assert (
        drawer_buttons is not search_filter_plugin.toolbar_container
    ), "Drawer buttons should be a separate widget instance"

    print(f"\n✅ PASS: Toolbar buttons properly hidden in cue_maker mode")
    print(f"✅ PASS: Drawer buttons created independently")


def test_genre_buttons_reappear_in_jukebox_mode(qapp) -> None:  # type: ignore
    """Test that toolbar buttons reappear when switching back to jukebox mode."""
    # Setup
    main_window = QMainWindow()
    plugin_toolbar = QToolBar("Plugins")
    main_window.addToolBar(plugin_toolbar)

    central = QWidget()
    central_layout = QVBoxLayout(central)
    main_window.setCentralWidget(central)

    main_window.show()

    search_filter_plugin = SearchAndFilterPlugin()

    class CodeConfig:
        def __init__(self, code: str, name: str):
            self.code = code
            self.name = name

    mock_context = Mock()
    mock_config = Mock()
    mock_config.genre_editor.codes = [CodeConfig("H", "House")]
    mock_context.config = mock_config
    mock_app = Mock()
    mock_app.main_window = main_window
    mock_context.app = mock_app

    search_filter_plugin.context = mock_context
    search_filter_plugin._create_toolbar_buttons()
    plugin_toolbar.addWidget(search_filter_plugin.toolbar_container)

    # Jukebox mode - buttons visible
    search_filter_plugin.activate("jukebox")
    assert search_filter_plugin.toolbar_container.isVisible(), "Should be visible in jukebox"

    # Cue maker mode - buttons hidden
    search_filter_plugin.activate("cue_maker")
    assert not search_filter_plugin.toolbar_container.isVisible(), "Should be hidden in cue_maker"

    # Back to jukebox - buttons visible again
    search_filter_plugin.activate("jukebox")
    assert (
        search_filter_plugin.toolbar_container.isVisible()
    ), "Should be visible again in jukebox"

    print("✅ PASS: Toolbar buttons properly toggle on mode switches")
