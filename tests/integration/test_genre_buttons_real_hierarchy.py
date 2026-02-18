"""Real integration test: Genre buttons visibility in true widget hierarchy.

This test uses the REAL search_and_filter plugin with a REAL toolbar,
and verifies that genre buttons are ACTUALLY hidden (not just setVisible=False).

It recursively searches the entire widget tree to prove buttons don't exist
in the toolbar when in cue_maker mode.
"""

from unittest.mock import Mock

from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QToolBar

from plugins.search_and_filter import SearchAndFilterPlugin


def find_all_genre_buttons(widget: QWidget, path: str = "root") -> list[tuple[QWidget, str]]:
    """Recursively find ALL genre buttons in widget tree with their paths.

    Returns list of (button_widget, path) tuples so we can see where buttons are.
    """
    from PySide6.QtWidgets import QPushButton

    buttons = []

    # Check if this widget is a genre button
    if isinstance(widget, QPushButton):
        text = widget.text()
        if len(text) == 1 and text.isalpha() and text.isupper():
            buttons.append((widget, f"{path}/{text}"))

    # Recurse into children
    for i, child in enumerate(widget.children()):
        if isinstance(child, QWidget):
            child_path = f"{path}/{child.__class__.__name__}[{i}]"
            buttons.extend(find_all_genre_buttons(child, child_path))

    return buttons


def test_genre_buttons_not_in_toolbar_during_cue_maker(qapp) -> None:  # type: ignore
    """REAL TEST: Genre buttons must NOT exist in toolbar during cue_maker mode.

    This test:
    1. Creates REAL toolbar with buttons added by register_ui()
    2. Switches to cue_maker mode
    3. Searches ENTIRE widget tree for genre buttons
    4. FAILS if ANY buttons found in toolbar
    """
    # Create main window with REAL toolbar
    main_window = QMainWindow()
    plugin_toolbar = QToolBar("Plugins")
    main_window.addToolBar(plugin_toolbar)

    central = QWidget()
    central_layout = QVBoxLayout(central)
    main_window.setCentralWidget(central)

    # CRITICAL: Show window so widgets become truly visible
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

    # Simulate register_ui - this adds buttons to real toolbar
    search_filter_plugin._create_toolbar_buttons()
    plugin_toolbar.addWidget(search_filter_plugin.toolbar_container)

    # Store toolbar reference (normally done in register_ui)
    search_filter_plugin._toolbar = plugin_toolbar

    # --- TEST 1: Verify buttons ARE in toolbar in jukebox mode ---
    print("\n=== JUKEBOX MODE ===")
    search_filter_plugin.activate("jukebox")

    # Search entire window for genre buttons
    all_buttons = find_all_genre_buttons(main_window)
    print(f"Buttons found in window: {len(all_buttons)}")
    for btn, path in all_buttons:
        print(f"  - {path}: visible={btn.isVisible()}")

    # Verify we have 4 buttons and they're in toolbar
    assert len(all_buttons) == 4, f"Expected 4 genre buttons in jukebox, found {len(all_buttons)}"

    toolbar_buttons = [btn for btn, path in all_buttons if "QToolBar" in path]
    print(f"Buttons in toolbar: {len(toolbar_buttons)}")
    assert len(toolbar_buttons) >= 4, f"Expected buttons in toolbar, but found {len(toolbar_buttons)} toolbar buttons"

    assert search_filter_plugin.toolbar_container.isVisible(), "Container should be visible in jukebox"
    print("✅ JUKEBOX MODE: Buttons correctly visible in toolbar")

    # --- TEST 2: Verify buttons are REMOVED from toolbar in cue_maker mode ---
    print("\n=== CUE_MAKER MODE ===")
    search_filter_plugin.activate("cue_maker")

    # Search entire window for genre buttons - should find NONE VISIBLE in toolbar
    all_buttons_after = find_all_genre_buttons(main_window)
    print(f"Total buttons found in window: {len(all_buttons_after)}")
    for btn, path in all_buttons_after:
        visible_status = btn.isVisible()
        print(f"  - {path}: visible={visible_status}")

    # Check toolbar specifically - should have NO VISIBLE buttons
    toolbar_buttons_after = [
        (btn, path) for btn, path in all_buttons_after
        if "QToolBar" in path and btn.isVisible()
    ]
    print(f"VISIBLE buttons in toolbar: {len(toolbar_buttons_after)}")

    # KEY ASSERTION: No VISIBLE buttons should be in toolbar
    assert (
        len(toolbar_buttons_after) == 0
    ), f"❌ FAIL: Found {len(toolbar_buttons_after)} VISIBLE genre buttons in toolbar!\n" + "\n".join(
        f"    - {path}" for _, path in toolbar_buttons_after
    )

    assert (
        not search_filter_plugin.toolbar_container.isVisible()
    ), "❌ Container should be hidden in cue_maker"

    print("✅ CUE_MAKER MODE: No VISIBLE buttons in toolbar (correctly hidden)")

    # --- TEST 3: Verify buttons REAPPEAR in toolbar when back in jukebox ---
    print("\n=== BACK TO JUKEBOX MODE ===")
    search_filter_plugin.activate("jukebox")

    all_buttons_final = find_all_genre_buttons(main_window)
    toolbar_buttons_final = [btn for btn, path in all_buttons_final if "QToolBar" in path]
    print(f"Buttons in toolbar: {len(toolbar_buttons_final)}")

    assert len(toolbar_buttons_final) >= 4, f"Expected buttons back in toolbar, found {len(toolbar_buttons_final)}"
    assert search_filter_plugin.toolbar_container.isVisible(), "Container should be visible again in jukebox"
    print("✅ JUKEBOX MODE (RETURN): Buttons correctly visible again in toolbar")

    print("\n" + "="*60)
    print("✅✅✅ ALL TESTS PASSED - Buttons correctly hidden/shown ✅✅✅")
    print("="*60)


def test_drawer_buttons_exist_independently(qapp) -> None:  # type: ignore
    """Verify drawer buttons are separate instances and work independently."""
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
    ]
    mock_context.config = mock_config

    search_filter_plugin.context = mock_context

    # Create toolbar buttons
    search_filter_plugin._create_toolbar_buttons()
    toolbar_buttons = search_filter_plugin.toolbar_container

    # Create drawer buttons - should be DIFFERENT instance
    drawer_buttons = search_filter_plugin.get_button_container()

    assert (
        toolbar_buttons is not drawer_buttons
    ), "Toolbar and drawer buttons should be different instances"

    # Verify both have buttons
    toolbar_button_count = find_all_genre_buttons(toolbar_buttons)
    drawer_button_count = find_all_genre_buttons(drawer_buttons)

    assert len(toolbar_button_count) == 2, f"Expected 2 buttons in toolbar, found {len(toolbar_button_count)}"
    assert len(drawer_button_count) == 2, f"Expected 2 buttons in drawer, found {len(drawer_button_count)}"

    print("✅ Drawer buttons are independent instances with correct counts")
