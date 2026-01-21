"""Configuration manager plugin - UI for managing plugin settings."""

import json
import logging
from pathlib import Path
from typing import Any

from jukebox.core.event_bus import Events
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
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


class DirectoryInput(QLineEdit):
    """Widget for selecting a directory - click to browse."""

    def __init__(self, parent: Any = None):
        """Initialize widget."""
        super().__init__(parent)
        self.setPlaceholderText("Click to select directory...")
        # Set cursor to indicate it's clickable
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        """Open directory browser on click."""
        current_dir = self.text() or str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Select Directory", current_dir)
        if directory:
            self.setText(directory)
        super().mousePressEvent(event)


class ListEditor(QWidget):
    """Widget for editing a list of structured items."""

    def __init__(self, item_schema: dict[str, Any], parent: Any = None):
        """Initialize widget.

        Args:
            item_schema: Schema for each item in the list
                {
                    "field_name": {"label": "Label", "type": "string|directory|shortcut"},
                    ...
                }
        """
        super().__init__(parent)
        self.item_schema = item_schema
        self.field_names = list(item_schema.keys())

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.field_names) + 1)  # +1 for delete button
        self.table.setMinimumHeight(200)

        # Set headers
        headers = [schema["label"] for schema in item_schema.values()] + [""]
        self.table.setHorizontalHeaderLabels(headers)

        # Set column widths based on field types
        header = self.table.horizontalHeader()
        for col, (field_name, field_schema) in enumerate(item_schema.items()):
            field_type = field_schema.get("type", "string")

            if field_type == "shortcut":
                # Shortcuts are small (e.g., "Ctrl+1", "Delete")
                self.table.setColumnWidth(col, 120)
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            elif field_type == "string":
                # Names are medium
                self.table.setColumnWidth(col, 150)
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            elif field_type == "directory":
                # Paths take most space
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)

        # Delete button column: fixed size
        header.setSectionResizeMode(len(self.field_names), QHeaderView.ResizeMode.ResizeToContents)

        # Set row height
        self.table.verticalHeader().setDefaultSectionSize(35)

        layout.addWidget(self.table)

        # Add button
        add_btn = QPushButton("Add Row")
        add_btn.clicked.connect(self._add_row)
        layout.addWidget(add_btn)

        self.setLayout(layout)

    def _add_row(self, data: dict[str, str] | None = None) -> None:
        """Add a new row to the table.

        Args:
            data: Optional data to populate the row
        """
        row = self.table.rowCount()
        self.table.insertRow(row)

        # Create widgets for each column based on schema
        for col, (field_name, field_schema) in enumerate(self.item_schema.items()):
            field_type = field_schema.get("type", "string")
            value = data.get(field_name, "") if data else ""

            if field_type == "directory":
                widget = DirectoryInput()
                widget.setText(value)
            elif field_type == "shortcut":
                widget = ShortcutInput()
                widget.setText(value)
            else:  # string
                widget = QLineEdit(value)

            self.table.setCellWidget(row, col, widget)

        # Delete button in last column
        delete_btn = QPushButton("🗑")
        delete_btn.setToolTip("Delete this row")
        delete_btn.setMaximumWidth(40)
        delete_btn.setFont(delete_btn.font())  # Ensure font supports the character
        # Override the padding for this specific button
        delete_btn.setStyleSheet("padding: 4px;")
        delete_btn.clicked.connect(lambda checked, r=row: self._delete_row(r))
        self.table.setCellWidget(row, len(self.field_names), delete_btn)

    def _delete_row(self, row: int) -> None:
        """Delete a row from the table."""
        self.table.removeRow(row)
        # Update all delete button callbacks (row indices have shifted)
        for r in range(self.table.rowCount()):
            delete_btn = self.table.cellWidget(r, len(self.field_names))
            if isinstance(delete_btn, QPushButton):
                delete_btn.clicked.disconnect()
                delete_btn.clicked.connect(lambda checked, row_idx=r: self._delete_row(row_idx))

    def get_items(self) -> list[dict[str, str]]:
        """Get all items from the table.

        Returns:
            List of dicts with field_name: value
        """
        items = []
        for row in range(self.table.rowCount()):
            item = {}
            for col, field_name in enumerate(self.field_names):
                widget = self.table.cellWidget(row, col)
                if isinstance(widget, (DirectoryInput, ShortcutInput, QLineEdit)):
                    item[field_name] = widget.text()
                else:
                    item[field_name] = ""
            items.append(item)
        return items

    def set_items(self, items: list[dict[str, str]]) -> None:
        """Set items in the table.

        Args:
            items: List of dicts with field_name: value
        """
        # Clear table
        self.table.setRowCount(0)

        # Add rows
        for item in items:
            self._add_row(item)


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
        self.setMinimumSize(800, 600)

        # Apply minimal styling (works for both light and dark themes)
        # Don't hardcode colors - let Qt use the system palette
        self.setStyleSheet(
            """
            QTabBar::tab {
                padding: 8px 20px;
            }
            QLineEdit, QSpinBox {
                padding: 4px;
            }
            QPushButton {
                padding: 6px 16px;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QHeaderView::section {
                padding: 6px;
            }
            """
        )

        # Main layout
        layout = QVBoxLayout()

        # Tab widget for different plugins
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)  # Show arrows when tabs overflow
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
                        "type": "directory" | "shortcut" | "int" | "float" | "string" | "bool",
                        "default": default_value,
                        "min": min_value (for int/float),
                        "max": max_value (for int/float),
                        "suffix": " seconds" (for int/float)
                    }
                }
        """
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # Form layout for settings
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Store input widgets for this plugin
        if not hasattr(self, "_plugin_inputs"):
            self._plugin_inputs = {}
        self._plugin_inputs[plugin_name] = {}

        # Create input widgets based on schema
        for setting_key, setting_config in schema.items():
            label = setting_config.get("label", setting_key)
            setting_type = setting_config.get("type", "string")

            # Create appropriate widget based on type
            if setting_type == "list":
                # List of structured items
                item_schema = setting_config.get("item_schema", {})
                input_widget = ListEditor(item_schema)
            elif setting_type == "bool":
                input_widget = QCheckBox()
                input_widget.setChecked(setting_config.get("default", False))
            elif setting_type == "directory":
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
                # Use QDoubleSpinBox for float values
                from PySide6.QtWidgets import QDoubleSpinBox

                input_widget = QDoubleSpinBox()
                input_widget.setRange(
                    setting_config.get("min", 0.0),
                    setting_config.get("max", 100.0),
                )
                input_widget.setSingleStep(0.1)  # Step by 0.1
                input_widget.setDecimals(1)  # Show 1 decimal place
                input_widget.setSuffix(setting_config.get("suffix", ""))
            else:  # string
                input_widget = QLineEdit()
                if "placeholder" in setting_config:
                    input_widget.setPlaceholderText(setting_config["placeholder"])

            # Store widget reference
            self._plugin_inputs[plugin_name][setting_key] = input_widget

            # Add to form
            form.addRow(f"{label}:", input_widget)

        layout.addLayout(form)
        layout.addStretch()

        widget.setLayout(layout)
        # Use plugin's name as tab title (shorter than description)
        tab_title = plugin_name.replace("_", " ").title()
        self.tabs.addTab(widget, tab_title)

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
                if isinstance(input_widget, ListEditor):
                    # Parse JSON list
                    import json

                    try:
                        items = json.loads(value) if value else []
                        input_widget.set_items(items)
                    except (json.JSONDecodeError, ValueError):
                        # Use default from schema
                        default = setting_config.get("default", [])
                        input_widget.set_items(default)
                elif isinstance(input_widget, QCheckBox):
                    # Parse boolean
                    bool_value = value.lower() in ("true", "1", "yes") if value else False
                    input_widget.setChecked(bool_value)
                elif isinstance(input_widget, (DirectoryInput, ShortcutInput)):
                    input_widget.setText(value)
                elif isinstance(input_widget, QDoubleSpinBox):
                    input_widget.setValue(float(value) if value else 0.0)
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
                if isinstance(input_widget, ListEditor):
                    # Serialize list to JSON
                    import json

                    items = input_widget.get_items()
                    value = json.dumps(items)
                elif isinstance(input_widget, QCheckBox):
                    value = "true" if input_widget.isChecked() else "false"
                elif isinstance(input_widget, (DirectoryInput, ShortcutInput, QLineEdit)):
                    value = input_widget.text()
                elif isinstance(input_widget, QDoubleSpinBox):
                    value = str(input_widget.value())
                elif isinstance(input_widget, QSpinBox):
                    value = str(input_widget.value())
                else:
                    continue

                # Save to database
                self._set_setting(plugin_name, setting_key, value)

        db.conn.commit()

        # Emit event to notify plugins that settings changed
        self.context.emit(Events.PLUGIN_SETTINGS_CHANGED)

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
