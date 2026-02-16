"""Main widget for the Cue Maker plugin."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from plugins.cue_maker.constants import STATUS_COLORS, TableColumn
from plugins.cue_maker.model import EntryStatus
from plugins.cue_maker.table_model import CueTableModel

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol

logger = logging.getLogger(__name__)


class CueMakerWidget(QWidget):
    """Main container widget for cue sheet creation.

    Layout:
        Top:    Mix info bar (filepath + load/analyze/export buttons)
        Middle: Cue entries table
        Bottom: Entry editor (time, artist, title, status controls)
    """

    # Signals
    mix_load_requested = Signal(str)  # filepath
    analyze_requested = Signal()
    export_requested = Signal()

    def __init__(self, context: PluginContextProtocol, parent: QWidget | None = None) -> None:
        """Initialize cue maker widget.

        Args:
            context: Plugin context for accessing app services
            parent: Parent widget
        """
        super().__init__(parent)
        self.context = context
        self.model = CueTableModel(self)
        self._selected_row: int = -1
        self._init_ui()
        self._connect_signals()

    def _init_ui(self) -> None:
        """Build the complete UI layout."""
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # --- Top: Mix controls ---
        layout.addWidget(self._create_mix_controls())

        # --- Middle: Table + Progress ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.table_view = self._create_table()
        layout.addWidget(self.table_view, stretch=1)

        # --- Bottom: Entry editor ---
        layout.addWidget(self._create_entry_editor())

        self.setLayout(layout)

    def _create_mix_controls(self) -> QWidget:
        """Create the top bar with mix file controls."""
        group = QGroupBox("Mix")
        h = QHBoxLayout()
        h.setContentsMargins(4, 4, 4, 4)

        self.mix_path_label = QLabel("No mix loaded")
        self.mix_path_label.setStyleSheet("color: #888;")
        h.addWidget(self.mix_path_label, stretch=1)

        self.load_btn = QPushButton("Load Mix")
        self.load_btn.setToolTip("Load an audio mix file")
        self.load_btn.clicked.connect(self._on_load_mix)
        h.addWidget(self.load_btn)

        self.analyze_btn = QPushButton("Analyze")
        self.analyze_btn.setToolTip("Analyze mix to identify tracks (shazamix)")
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.clicked.connect(self.analyze_requested.emit)
        h.addWidget(self.analyze_btn)

        self.add_entry_btn = QPushButton("+ Add Entry")
        self.add_entry_btn.setToolTip("Add a manual cue entry")
        self.add_entry_btn.clicked.connect(self._on_add_manual_entry)
        h.addWidget(self.add_entry_btn)

        self.export_btn = QPushButton("Export CUE")
        self.export_btn.setToolTip("Export cue sheet to .cue file")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._on_export)
        h.addWidget(self.export_btn)

        group.setLayout(h)
        return group

    def _create_table(self) -> QTableView:
        """Create and configure the cue entries table view."""
        table = QTableView()
        table.setModel(self.model)
        table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)

        # Column sizing
        header = table.horizontalHeader()
        header.setSectionResizeMode(TableColumn.TIME, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(TableColumn.ARTIST, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(TableColumn.TITLE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(TableColumn.CONFIDENCE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(TableColumn.DURATION, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(TableColumn.STATUS, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(TableColumn.ACTIONS, QHeaderView.ResizeMode.Fixed)

        table.setColumnWidth(TableColumn.TIME, 60)
        table.setColumnWidth(TableColumn.CONFIDENCE, 80)
        table.setColumnWidth(TableColumn.DURATION, 60)
        table.setColumnWidth(TableColumn.STATUS, 80)
        table.setColumnWidth(TableColumn.ACTIONS, 100)

        # Selection change
        table.selectionModel().currentRowChanged.connect(self._on_row_selected)

        return table

    def _create_entry_editor(self) -> QWidget:
        """Create the bottom entry editor panel."""
        group = QGroupBox("Entry Editor")
        h = QHBoxLayout()
        h.setContentsMargins(4, 4, 4, 4)

        # Time input
        h.addWidget(QLabel("Time:"))
        self.time_input = QLineEdit()
        self.time_input.setPlaceholderText("MM:SS")
        self.time_input.setMaximumWidth(70)
        self.time_input.editingFinished.connect(self._on_time_edited)
        h.addWidget(self.time_input)

        # Artist input
        h.addWidget(QLabel("Artist:"))
        self.artist_input = QLineEdit()
        self.artist_input.setPlaceholderText("Artist name")
        self.artist_input.editingFinished.connect(self._on_artist_edited)
        h.addWidget(self.artist_input)

        # Title input
        h.addWidget(QLabel("Title:"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Track title")
        self.title_input.editingFinished.connect(self._on_title_edited)
        h.addWidget(self.title_input)

        # Status buttons
        self.confirm_btn = QPushButton("✓")
        self.confirm_btn.setToolTip("Confirm entry")
        self.confirm_btn.setFixedWidth(32)
        self.confirm_btn.setStyleSheet(f"background-color: {STATUS_COLORS['confirmed']};")
        self.confirm_btn.clicked.connect(lambda: self._set_status(EntryStatus.CONFIRMED))
        h.addWidget(self.confirm_btn)

        self.reject_btn = QPushButton("✗")
        self.reject_btn.setToolTip("Reject entry")
        self.reject_btn.setFixedWidth(32)
        self.reject_btn.setStyleSheet(f"background-color: {STATUS_COLORS['rejected']};")
        self.reject_btn.clicked.connect(lambda: self._set_status(EntryStatus.REJECTED))
        h.addWidget(self.reject_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setToolTip("Remove entry from list")
        self.delete_btn.clicked.connect(self._on_delete_entry)
        h.addWidget(self.delete_btn)

        group.setLayout(h)

        # Disable until selection
        self._set_editor_enabled(False)
        return group

    def _connect_signals(self) -> None:
        """Connect model signals."""
        self.model.layoutChanged.connect(self._update_export_button)
        self.model.dataChanged.connect(self._update_export_button)
        self.model.rowsInserted.connect(self._update_export_button)
        self.model.rowsRemoved.connect(self._update_export_button)

    # --- Slots ---

    def _on_load_mix(self) -> None:
        """Open file dialog to load a mix."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Load Mix File",
            "",
            "Audio Files (*.mp3 *.flac *.wav *.aiff *.aif *.ogg *.m4a);;All Files (*)",
        )
        if filepath:
            self.mix_path_label.setText(Path(filepath).name)
            self.mix_path_label.setStyleSheet("")
            self.model.set_metadata(filepath, Path(filepath).stem, "")
            self.analyze_btn.setEnabled(True)
            self.mix_load_requested.emit(filepath)
            logger.info("[Cue Maker] Mix loaded: %s", filepath)

    def _on_row_selected(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """Update editor when table row selection changes."""
        if not current.isValid():
            self._selected_row = -1
            self._set_editor_enabled(False)
            return

        self._selected_row = current.row()
        entry = self.model.get_entry(self._selected_row)
        if entry:
            self._set_editor_enabled(True)
            self.time_input.setText(entry.to_display_time())
            self.artist_input.setText(entry.artist)
            self.title_input.setText(entry.title)

    def _on_time_edited(self) -> None:
        """Apply time edit from input field."""
        if self._selected_row < 0:
            return
        idx = self.model.index(self._selected_row, TableColumn.TIME)
        self.model.setData(idx, self.time_input.text(), Qt.ItemDataRole.EditRole)

    def _on_artist_edited(self) -> None:
        """Apply artist edit from input field."""
        if self._selected_row < 0:
            return
        idx = self.model.index(self._selected_row, TableColumn.ARTIST)
        self.model.setData(idx, self.artist_input.text(), Qt.ItemDataRole.EditRole)

    def _on_title_edited(self) -> None:
        """Apply title edit from input field."""
        if self._selected_row < 0:
            return
        idx = self.model.index(self._selected_row, TableColumn.TITLE)
        self.model.setData(idx, self.title_input.text(), Qt.ItemDataRole.EditRole)

    def _set_status(self, status: EntryStatus) -> None:
        """Set status on selected entry."""
        if self._selected_row >= 0:
            self.model.set_entry_status(self._selected_row, status)

    def _on_delete_entry(self) -> None:
        """Delete the selected entry."""
        if self._selected_row >= 0:
            self.model.remove_entry(self._selected_row)
            self._selected_row = -1
            self._set_editor_enabled(False)

    def _on_add_manual_entry(self) -> None:
        """Add a new manual entry at time 00:00."""
        self.model.add_manual_entry(0, "", "")
        # Select the newly added row
        last_row = self.model.rowCount() - 1
        if last_row >= 0:
            idx = self.model.index(0, 0)  # Time 0 will be first after sort
            self.table_view.setCurrentIndex(idx)

    def _on_export(self) -> None:
        """Export cue sheet to file."""
        if not self.model.has_confirmed_entries():
            QMessageBox.warning(
                self,
                "Export",
                "No confirmed entries to export.\nConfirm at least one entry first.",
            )
            return

        default_name = Path(self.model.sheet.mix_filepath).stem + ".cue"
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export CUE File",
            default_name,
            "CUE Files (*.cue);;All Files (*)",
        )
        if filepath:
            try:
                from plugins.cue_maker.exporter import CueExporter

                CueExporter.export(self.model.sheet, filepath)
                QMessageBox.information(
                    self, "Export", f"CUE file exported to:\n{filepath}"
                )
                logger.info("[Cue Maker] Exported to %s", filepath)
            except (ValueError, OSError) as e:
                QMessageBox.critical(self, "Export Error", str(e))

    def _set_editor_enabled(self, enabled: bool) -> None:
        """Enable/disable entry editor controls."""
        self.time_input.setEnabled(enabled)
        self.artist_input.setEnabled(enabled)
        self.title_input.setEnabled(enabled)
        self.confirm_btn.setEnabled(enabled)
        self.reject_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)
        if not enabled:
            self.time_input.clear()
            self.artist_input.clear()
            self.title_input.clear()

    def _update_export_button(self) -> None:
        """Enable export button when confirmed entries exist."""
        self.export_btn.setEnabled(self.model.has_confirmed_entries())

    # --- Public API for plugin ---

    def set_analysis_progress(self, current: int, total: int, message: str) -> None:
        """Update progress bar during analysis."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"{message} (%p%)")

    def on_analysis_complete(self, entries: list) -> None:
        """Handle analysis results."""
        self.progress_bar.setVisible(False)
        self.analyze_btn.setEnabled(True)
        self.model.load_entries(entries)
        logger.info("[Cue Maker] Analysis loaded %d entries", len(entries))

    def on_analysis_error(self, error_message: str) -> None:
        """Handle analysis failure."""
        self.progress_bar.setVisible(False)
        self.analyze_btn.setEnabled(True)
        QMessageBox.critical(self, "Analysis Error", error_message)
