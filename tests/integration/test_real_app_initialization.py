"""Test real app initialization to verify genre button visibility in cue_maker mode."""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def find_visible_genre_buttons_in_toolbar(widget, toolbar_only=True):
    """Find ALL VISIBLE genre buttons (not just those with visible=True flag)."""
    from PySide6.QtWidgets import QPushButton, QToolBar

    buttons = []

    if isinstance(widget, QPushButton):
        text = widget.text()
        if len(text) == 1 and text.isalpha() and text.isupper():
            # Check if button is actually visible (could render)
            # A button is visible if it and all its ancestors are visible
            is_visible = widget.isVisible()
            if not toolbar_only or _is_in_toolbar(widget):
                buttons.append((widget, text, is_visible))

    for child in widget.children():
        buttons.extend(find_visible_genre_buttons_in_toolbar(child, toolbar_only))

    return buttons


def _is_in_toolbar(widget):
    """Check if widget is inside a QToolBar."""
    from PySide6.QtWidgets import QToolBar
    parent = widget.parent()
    while parent:
        if isinstance(parent, QToolBar):
            return True
        parent = parent.parent()
    return False


def test_genre_buttons_hidden_in_real_cue_maker_mode(qapp) -> None:
    """Test that genre buttons are NOT visible in real cue_maker mode.

    This test initializes the app like a user would and checks if buttons
    are actually visible in the UI when in cue_maker mode.
    """
    from jukebox.ui.main_window import MainWindow
    from jukebox.core.config import load_config
    from pathlib import Path
    import tempfile

    # Create a temp config
    temp_dir = tempfile.mkdtemp()
    config_path = Path(temp_dir) / "config.yaml"

    # Write minimal config
    config_path.write_text("""
ui:
  window_title: "Jukebox Test"
  mode: "jukebox"

plugins:
  enabled:
    - search_and_filter
    - mode_switcher
    - cue_maker

database:
  path: ":memory:"

genre_editor:
  codes:
    - { code: "H", name: "House" }
    - { code: "D", name: "Deep" }
    - { code: "T", name: "Trance" }
    - { code: "W", name: "Weed" }

logging:
  level: "WARNING"
""")

    # Load config
    config = load_config(config_path)

    # Create main window
    main_window = MainWindow(config)
    main_window.show()

    # --- TEST 1: Verify buttons ARE visible in jukebox mode ---
    print("\n=== INITIAL STATE (JUKEBOX MODE) ===")
    buttons_initial = find_visible_genre_buttons_in_toolbar(main_window)
    visible_count_initial = sum(1 for _, _, is_vis in buttons_initial if is_vis)

    print(f"Genre buttons found in toolbar: {len(buttons_initial)}")
    print(f"Visible buttons: {visible_count_initial}")
    for btn, text, is_visible in buttons_initial:
        print(f"  - Button '{text}': visible={is_visible}")

    assert visible_count_initial > 0, "Expected visible genre buttons in jukebox mode!"
    print("✅ Jukebox mode: Buttons visible as expected")

    # --- TEST 2: Switch to cue_maker mode and check ---
    print("\n=== SWITCHING TO CUE_MAKER MODE ===")

    if hasattr(main_window, "mode_manager"):
        from jukebox.core.mode_manager import AppMode
        print("Switching via mode_manager...")
        main_window.mode_manager.set_mode(AppMode.CUE_MAKER)
    else:
        print("⚠️ WARNING: No mode_manager found!")

    # Give Qt time to process events
    QApplication.processEvents()

    # --- TEST 3: Check if buttons are still visible ---
    print("\n=== CHECKING STATE IN CUE_MAKER MODE ===")
    buttons_after = find_visible_genre_buttons_in_toolbar(main_window)
    visible_count_after = sum(1 for _, _, is_vis in buttons_after if is_vis)

    print(f"Genre buttons found in toolbar: {len(buttons_after)}")
    print(f"VISIBLE buttons: {visible_count_after}")
    for btn, text, is_visible in buttons_after:
        status = "VISIBLE ❌" if is_visible else "hidden ✅"
        print(f"  - Button '{text}': {status}")

    # KEY TEST: No buttons should be visible in cue_maker mode
    if visible_count_after > 0:
        visible_buttons = [(text, btn.isVisible()) for btn, text, is_vis in buttons_after if is_vis]
        print(f"\n❌ FAIL: Found {visible_count_after} VISIBLE buttons in toolbar in cue_maker mode!")
        print(f"These buttons should NOT be visible:")
        for text, _ in visible_buttons:
            print(f"  - Button '{text}'")
        raise AssertionError(
            f"Found {visible_count_after} visible genre buttons in toolbar during cue_maker mode. "
            f"They should all be hidden!"
        )

    print(f"\n✅ PASS: No visible buttons in toolbar in cue_maker mode")
    print(f"✅ All {len(buttons_after)} buttons are properly hidden")
