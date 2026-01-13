"""Configuration manager plugin - UI for managing plugin settings."""

import json
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class ConfManagerPlugin:
    """Plugin configuration manager with GUI."""

    name = "conf_manager"
    version = "1.0.0"
    description = "Configuration manager for plugins"
    modes = ["jukebox", "curating"]  # Active in all modes

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None
        self.conf_dialog: ConfigDialog | None = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

    def register_ui(self, ui_builder: Any) -> None:
        """Register configuration menu."""
        # Add menu item
        menu = ui_builder.get_or_create_menu("&Settings")
        ui_builder.add_menu_action(menu, "Plugin &Configuration...", self._show_config_dialog)

    def register_shortcuts(self, shortcut_manager: Any) -> None:
        """No shortcuts for this plugin."""
        pass

    def _show_config_dialog(self) -> None:
        """Show plugin configuration dialog."""
        if not self.conf_dialog:
            self.conf_dialog = ConfigDialog(self.context)

        self.conf_dialog.load_settings()
        self.conf_dialog.exec()

    def activate(self, mode: str) -> None:
        """Activate plugin for this mode."""
        logging.debug(f"[Conf Manager] Activated for {mode} mode")

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for this mode."""
        logging.debug(f"[Conf Manager] Deactivated for {mode} mode")

    def shutdown(self) -> None:
        """Cleanup on application exit."""
        if self.conf_dialog:
            self.conf_dialog.close()


class DirectoryInput(QWidget):
    """Widget for selecting a directory."""

    def __init__(self, parent: Any = None):
        """Initialize widget."""
        super().__init__(parent)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.line_edit = QLineEdit()
        layout.addWidget(self.line_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        layout.addWidget(browse_btn)

        self.setLayout(layout)

    def _browse(self) -> None:
        """Open directory browser."""
        current_dir = self.line_edit.text() or str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Select Directory", current_dir)
        if directory:
            self.line_edit.setText(directory)

    def text(self) -> str:
        """Get current text."""
        return self.line_edit.text()

    def setText(self, text: str) -> None:
        """Set text."""
        self.line_edit.setText(text)


class ShortcutInput(QLineEdit):
    """Widget for capturing keyboard shortcuts."""

    def __init__(self, parent: Any = None):
        """Initialize widget."""
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Press keys...")
        self._current_keys: list[Qt.Key] = []
        self._modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Capture key press."""
        # Get modifiers and key
        modifiers = event.modifiers()
        key = event.key()

        # Ignore standalone modifiers
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ):
            return

        # Build shortcut string using QKeySequence
        # Combine modifiers (already int value) with key
        key_combination = int(modifiers.value) | int(key)
        key_sequence = QKeySequence(key_combination)
        self.setText(key_sequence.toString())

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        """Clear on click."""
        self.clear()
        self.setPlaceholderText("Press keys...")
        super().mousePressEvent(event)


class ConfigDialog(QDialog):
    """Configuration dialog for plugins."""

    def __init__(self, context: Any):
        """Initialize dialog."""
        super().__init__()
        self.context = context
        self.setWindowTitle("Plugin Configuration")
        self.setMinimumSize(600, 400)

        # Apply dark theme styling
        if context.config.ui.theme == "dark":
            self.setStyleSheet(
                """
                QDialog {
                    background-color: #2b2b2b;
                    color: #ffffff;
                }
                QTabWidget::pane {
                    border: 1px solid #444444;
                    background-color: #2b2b2b;
                }
                QTabBar::tab {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    padding: 8px 20px;
                    border: 1px solid #444444;
                }
                QTabBar::tab:selected {
                    background-color: #2b2b2b;
                    border-bottom-color: #2b2b2b;
                }
                QLineEdit, QSpinBox {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    border: 1px solid #555555;
                    padding: 4px;
                }
                QPushButton {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    border: 1px solid #555555;
                    padding: 6px 16px;
                }
                QPushButton:hover {
                    background-color: #4c4c4c;
                }
                QPushButton:disabled {
                    color: #888888;
                }
                QLabel {
                    color: #ffffff;
                }
                """
            )

        # Main layout
        layout = QVBoxLayout()

        # Tab widget for different plugins
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Buttons
        button_layout = QVBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_settings)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Build plugin tabs
        self._build_plugin_tabs()

    def _build_plugin_tabs(self) -> None:
        """Build configuration tabs for each plugin dynamically."""
        # Get all plugins from plugin manager
        if not hasattr(self.context, "app") or not hasattr(self.context.app, "plugin_manager"):
            return

        plugin_manager = self.context.app.plugin_manager

        # Iterate through all plugins
        for plugin_name, plugin in plugin_manager.plugins.items():
            # Check if plugin has settings schema
            if not hasattr(plugin, "get_settings_schema"):
                continue

            schema = plugin.get_settings_schema()
            if not schema:
                continue

            # Build tab for this plugin
            self._add_dynamic_tab(plugin_name, plugin, schema)

    def _add_dynamic_tab(self, plugin_name: str, plugin: Any, schema: dict[str, Any]) -> None:
        """Build a tab dynamically from plugin settings schema.

        Args:
            plugin_name: Name of the plugin
            plugin: Plugin instance
            schema: Settings schema dict with format:
                {
                    "setting_key": {
                        "label": "Display Label",
                        "type": "directory" | "shortcut" | "int" | "float" | "string",
                        "default": default_value,
                        "min": min_value (for int/float),
                        "max": max_value (for int/float),
                        "suffix": " seconds" (for int/float)
                    }
                }
        """
        widget = QWidget()
        layout = QVBoxLayout()

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        form = QFormLayout()

        # Store input widgets for this plugin
        if not hasattr(self, "_plugin_inputs"):
            self._plugin_inputs = {}
        self._plugin_inputs[plugin_name] = {}

        # Create input widgets based on schema
        for setting_key, setting_config in schema.items():
            label = setting_config.get("label", setting_key)
            setting_type = setting_config.get("type", "string")

            # Create appropriate widget based on type
            if setting_type == "directory":
                input_widget = DirectoryInput()
            elif setting_type == "shortcut":
                input_widget = ShortcutInput()
            elif setting_type == "int":
                input_widget = QSpinBox()
                input_widget.setRange(
                    setting_config.get("min", 0), setting_config.get("max", 1000)
                )
                if "suffix" in setting_config:
                    input_widget.setSuffix(setting_config["suffix"])
            elif setting_type == "float":
                # Use QSpinBox with decimals for simplicity
                input_widget = QSpinBox()
                input_widget.setRange(
                    int(setting_config.get("min", 0) * 100),
                    int(setting_config.get("max", 100) * 100),
                )
                input_widget.setSuffix(setting_config.get("suffix", ""))
            else:  # string
                input_widget = QLineEdit()
                if "placeholder" in setting_config:
                    input_widget.setPlaceholderText(setting_config["placeholder"])

            # Store widget reference
            self._plugin_inputs[plugin_name][setting_key] = input_widget

            # Add to form
            form.addRow(f"{label}:", input_widget)

        scroll_content.setLayout(form)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        widget.setLayout(layout)
        # Use plugin's description or name as tab title
        tab_title = getattr(plugin, "description", plugin_name).title()
        self.tabs.addTab(widget, tab_title)

    def _add_file_manager_tab_old(self) -> None:
        """Add file manager configuration tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        form = QFormLayout()

        # Trash directory (with file browser)
        self.trash_dir_input = DirectoryInput()
        form.addRow("Trash Directory:", self.trash_dir_input)

        # Trash key (with shortcut capture)
        self.trash_key_input = ShortcutInput()
        form.addRow("Trash Shortcut:", self.trash_key_input)

        # Note about destinations
        info_label = QPushButton("Destinations are configured in config.yaml")
        info_label.setEnabled(False)
        form.addRow(info_label)

        scroll_content.setLayout(form)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        widget.setLayout(layout)
        self.tabs.addTab(widget, "File Manager")

    def _add_genre_editor_tab(self) -> None:
        """Add genre editor configuration tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Info
        info_label = QPushButton("Genre codes and shortcuts are configured in config.yaml")
        info_label.setEnabled(False)
        layout.addWidget(info_label)

        widget.setLayout(layout)
        self.tabs.addTab(widget, "Genre Editor")

    def _add_playback_navigation_tab(self) -> None:
        """Add playback navigation configuration tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        form = QFormLayout()

        # Seek amount
        self.seek_amount_input = QSpinBox()
        self.seek_amount_input.setRange(1, 60)
        self.seek_amount_input.setSuffix(" seconds")
        form.addRow("Seek Amount:", self.seek_amount_input)

        # Rapid press threshold
        self.rapid_press_input = QSpinBox()
        self.rapid_press_input.setRange(100, 2000)
        self.rapid_press_input.setSuffix(" ms")
        form.addRow("Rapid Press Threshold:", self.rapid_press_input)

        # Max seek multiplier
        self.max_seek_mult_input = QSpinBox()
        self.max_seek_mult_input.setRange(1, 10)
        form.addRow("Max Seek Multiplier:", self.max_seek_mult_input)

        layout.addLayout(form)
        layout.addStretch()

        widget.setLayout(layout)
        self.tabs.addTab(widget, "Playback Navigation")

    def _add_waveform_tab(self) -> None:
        """Add waveform visualizer configuration tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        form = QFormLayout()

        # Chunk duration
        self.chunk_duration_input = QSpinBox()
        self.chunk_duration_input.setRange(1, 60)
        self.chunk_duration_input.setSuffix(" seconds")
        form.addRow("Chunk Duration:", self.chunk_duration_input)

        # Height
        self.waveform_height_input = QSpinBox()
        self.waveform_height_input.setRange(20, 200)
        self.waveform_height_input.setSuffix(" px")
        form.addRow("Waveform Height:", self.waveform_height_input)

        # Colors (read-only for now)
        bass_color_input = QLineEdit()
        bass_color_input.setReadOnly(True)
        bass_color_input.setPlaceholderText("Configured in config.yaml")
        form.addRow("Bass Color:", bass_color_input)

        layout.addLayout(form)
        layout.addStretch()

        widget.setLayout(layout)
        self.tabs.addTab(widget, "Waveform")

    def load_settings(self) -> None:
        """Load settings from database for all plugins."""
        if not hasattr(self, "_plugin_inputs"):
            return

        plugin_manager = self.context.app.plugin_manager

        # Load settings for each plugin
        for plugin_name, inputs in self._plugin_inputs.items():
            plugin = plugin_manager.plugins.get(plugin_name)
            if not plugin or not hasattr(plugin, "get_settings_schema"):
                continue

            schema = plugin.get_settings_schema()

            for setting_key, input_widget in inputs.items():
                setting_config = schema.get(setting_key, {})
                default_value = setting_config.get("default", "")

                # Get value from database or use default
                db_value = self._get_setting(plugin_name, setting_key)
                value = db_value if db_value is not None else str(default_value)

                # Set value based on widget type
                if isinstance(input_widget, (DirectoryInput, ShortcutInput)):
                    input_widget.setText(value)
                elif isinstance(input_widget, QSpinBox):
                    input_widget.setValue(int(float(value)) if value else 0)
                elif isinstance(input_widget, QLineEdit):
                    input_widget.setText(value)

    def _get_setting(self, plugin_name: str, setting_key: str) -> str | None:
        """Get setting from database."""
        result = self.context.database.conn.execute(
            "SELECT setting_value FROM plugin_settings WHERE plugin_name = ? AND setting_key = ?",
            (plugin_name, setting_key),
        ).fetchone()

        return result["setting_value"] if result else None

    def _save_settings(self) -> None:
        """Save settings to database for all plugins."""
        if not hasattr(self, "_plugin_inputs"):
            return

        db = self.context.database

        # Save settings for each plugin
        for plugin_name, inputs in self._plugin_inputs.items():
            for setting_key, input_widget in inputs.items():
                # Get value from widget
                if isinstance(input_widget, (DirectoryInput, ShortcutInput, QLineEdit)):
                    value = input_widget.text()
                elif isinstance(input_widget, QSpinBox):
                    value = str(input_widget.value())
                else:
                    continue

                # Save to database
                self._set_setting(plugin_name, setting_key, value)

        db.conn.commit()

        # Emit event to notify plugins that settings changed
        self.context.emit("plugin_settings_changed")

        self.accept()

    def _set_setting(self, plugin_name: str, setting_key: str, setting_value: str) -> None:
        """Set setting in database."""
        self.context.database.conn.execute(
            """
            INSERT OR REPLACE INTO plugin_settings (plugin_name, setting_key, setting_value, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """,
            (plugin_name, setting_key, setting_value),
        )
