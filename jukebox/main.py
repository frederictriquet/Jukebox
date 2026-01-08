"""Main entry point for Jukebox application."""

import sys

from PySide6.QtWidgets import QApplication

from jukebox.core.config import load_config
from jukebox.ui.main_window import MainWindow
from jukebox.utils.logger import setup_logging


def main() -> None:
    """Application entry point."""
    try:
        # Load configuration
        config = load_config()

        # Setup logging
        setup_logging(config.logging)

        # Create Qt application
        app = QApplication(sys.argv)
        app.setApplicationName(config.ui.window_title)

        # Create and show main window
        window = MainWindow(config)
        window.show()

        # Run event loop
        sys.exit(app.exec())

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Please ensure config/config.yaml exists.")
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
