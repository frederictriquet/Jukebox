"""Tests for UI builder."""

from jukebox.ui.ui_builder import UIBuilder


class TestUIBuilder:
    """Test UIBuilder."""

    def test_initialization(self, qapp):  # type: ignore
        """Test UIBuilder initializes."""

        class MockWindow:
            def menuBar(self):  # type: ignore # noqa: N802
                from PySide6.QtWidgets import QMenuBar

                return QMenuBar()

        ui_builder = UIBuilder(MockWindow())

        assert ui_builder is not None
        assert ui_builder.main_window is not None

    def test_add_menu(self, qapp):  # type: ignore
        """Test adding menu."""
        from PySide6.QtWidgets import QMainWindow

        window = QMainWindow()
        ui_builder = UIBuilder(window)
        menu = ui_builder.add_menu("Test")

        assert menu is not None
