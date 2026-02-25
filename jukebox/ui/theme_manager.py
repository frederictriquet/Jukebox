"""Theme management for the application."""

from PySide6.QtWidgets import QApplication


class ThemeManager:
    """Manage application themes and styles."""

    THEMES = {
        # @hardcoded-ok: theme colors defined inline in stylesheet
        "dark": """
            QMainWindow {
                background-color: #1e1e1e;
            }
            QWidget {
                background-color: #2d2d2d;
                color: #ffffff;
            }
            QPushButton {
                background-color: #3d3d3d;
                border: 1px solid #555555;
                padding: 5px 10px;
                border-radius: 3px;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
            }
            QPushButton:pressed {
                background-color: #2d2d2d;
            }
            QLineEdit {
                background-color: #3d3d3d;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 3px;
                color: #ffffff;
            }
            QLineEdit:focus {
                border: 1px solid #0066FF;
            }
            QListWidget {
                background-color: #2d2d2d;
                border: 1px solid #555555;
                color: #ffffff;
            }
            QListWidget::item:selected {
                background-color: #0066FF;
            }
            QListWidget::item:hover {
                background-color: #3d3d3d;
            }
            QSlider::groove:horizontal {
                background: #3d3d3d;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #0066FF;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #3388FF;
            }
            QMenuBar {
                background-color: #2d2d2d;
                color: #ffffff;
            }
            QMenuBar::item:selected {
                background-color: #3d3d3d;
            }
            QMenu {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #555555;
            }
            QMenu::item:selected {
                background-color: #0066FF;
            }
            QToolBar {
                background-color: #2d2d2d;
                border: none;
                spacing: 5px;
            }
            QDockWidget {
                color: #ffffff;
            }
            QDockWidget::title {
                background-color: #3d3d3d;
                padding: 5px;
            }
        """,
        # @hardcoded-ok: theme colors defined inline in stylesheet
        "light": """
            QMainWindow {
                background-color: #ffffff;
            }
            QWidget {
                background-color: #f5f5f5;
                color: #000000;
            }
            QPushButton {
                background-color: #e0e0e0;
                border: 1px solid #cccccc;
                padding: 5px 10px;
                border-radius: 3px;
                color: #000000;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            QPushButton:pressed {
                background-color: #c0c0c0;
            }
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                padding: 5px;
                border-radius: 3px;
                color: #000000;
            }
            QLineEdit:focus {
                border: 1px solid #0066FF;
            }
            QListWidget {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                color: #000000;
            }
            QListWidget::item:selected {
                background-color: #0066FF;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background-color: #e8e8e8;
            }
            QSlider::groove:horizontal {
                background: #cccccc;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #0066FF;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #3388FF;
            }
            QMenuBar {
                background-color: #f0f0f0;
                color: #000000;
            }
            QMenuBar::item:selected {
                background-color: #e0e0e0;
            }
            QMenu {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
            }
            QMenu::item:selected {
                background-color: #0066FF;
                color: #ffffff;
            }
            QToolBar {
                background-color: #f0f0f0;
                border: none;
                spacing: 5px;
            }
            QDockWidget {
                color: #000000;
            }
            QDockWidget::title {
                background-color: #e0e0e0;
                padding: 5px;
            }
        """,
    }

    @staticmethod
    def apply_theme(theme_name: str) -> bool:
        """Apply a theme to the application.

        Args:
            theme_name: Name of theme ("dark" or "light")

        Returns:
            True if theme was applied, False if theme not found
        """
        if theme_name not in ThemeManager.THEMES:
            return False

        app = QApplication.instance()
        if app and isinstance(app, QApplication):
            app.setStyleSheet(ThemeManager.THEMES[theme_name])
            return True

        return False

    @staticmethod
    def get_available_themes() -> list[str]:
        """Get list of available theme names.

        Returns:
            List of theme names
        """
        return list(ThemeManager.THEMES.keys())
