"""Main widget for the Cue Maker plugin."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pyqtgraph as pg
from PySide6.QtCore import QModelIndex, Qt, QTimer, Signal
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

from jukebox.core.event_bus import Events
from plugins.cue_maker.constants import TableColumn
from plugins.cue_maker.table_model import CueTableModel

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol

logger = logging.getLogger(__name__)


class CueMakerWidget(QWidget):
    """Main container widget for cue sheet creation.

    Layout:
        Top:    Mix info bar (filepath + load/analyze/export buttons)
        Middle: Waveform + Cue entries table
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
        self._waveform_worker = None
        self._is_mix_playing: bool = False
        self._highlight_region: pg.LinearRegionItem | None = None
        self._mix_duration_s: float = 0.0
        self._mix_position_timer = QTimer()
        self._mix_position_timer.setInterval(100)
        self._mix_position_timer.timeout.connect(self._poll_mix_position)
        self._init_ui()
        self._connect_signals()
        self._connect_player_events()

    def _init_ui(self) -> None:
        """Build the complete UI layout."""
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # --- Top: Mix controls ---
        layout.addWidget(self._create_mix_controls())

        # --- Waveform ---
        self.waveform_widget = self._create_waveform()
        layout.addWidget(self.waveform_widget)

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

        self.play_btn = QPushButton("\u25b6")
        self.play_btn.setToolTip("Play mix")
        self.play_btn.setFixedWidth(32)
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._on_play_pause)
        h.addWidget(self.play_btn)

        self.stop_btn = QPushButton("\u25a0")
        self.stop_btn.setToolTip("Stop mix")
        self.stop_btn.setFixedWidth(32)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        h.addWidget(self.stop_btn)

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

    def _create_waveform(self) -> QWidget:
        """Create the waveform display widget for the loaded mix."""
        from plugins.waveform_visualizer import WaveformWidget

        try:
            waveform_config = self.context.config.waveform
            # Validate it's a real config (not a Mock) by checking type
            if not isinstance(waveform_config.height, int):
                waveform_config = None
        except (AttributeError, TypeError):
            waveform_config = None
        widget = WaveformWidget(waveform_config)
        return widget

    def _create_table(self) -> QTableView:
        """Create and configure the cue entries table view."""
        table = QTableView()
        table.setModel(self.model)
        table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(False)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)

        # Column sizing
        header = table.horizontalHeader()
        header.setSectionResizeMode(TableColumn.OVERLAP, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(TableColumn.TIME, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(TableColumn.ARTIST, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(TableColumn.TITLE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(TableColumn.CONFIDENCE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(TableColumn.DURATION, QHeaderView.ResizeMode.Fixed)

        table.setColumnWidth(TableColumn.OVERLAP, 30)
        table.setColumnWidth(TableColumn.TIME, 60)
        table.setColumnWidth(TableColumn.CONFIDENCE, 80)
        table.setColumnWidth(TableColumn.DURATION, 60)

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

    def _connect_player_events(self) -> None:
        """Connect to player and event bus for mix playback."""
        self.context.player.state_changed.connect(self._on_player_state_changed)
        self.context.subscribe(Events.TRACK_LOADED, self._on_track_loaded_from_library)
        self.context.subscribe(Events.MIX_POSITION_UPDATE, self._on_mix_position_update)
        self.waveform_widget.position_clicked.connect(self._on_waveform_seek)

    # --- Playback slots ---

    def _take_over_player(self) -> None:
        """Notify PlaybackController that the mix is taking over the player."""
        self.context.app.playback._current_track_filepath = None

    def _on_play_pause(self) -> None:
        """Toggle play/pause for the mix."""
        player = self.context.player
        mix_path = self.model.sheet.mix_filepath
        if not mix_path:
            return

        if self._is_mix_playing and player.is_playing():
            player.pause()
        else:
            # If mix is not currently loaded in the player, load it
            current = player.current_file
            if current is None or str(current) != mix_path:
                player.load(Path(mix_path))
            self._take_over_player()
            self._is_mix_playing = True
            player.play()

    def _on_stop(self) -> None:
        """Stop mix playback."""
        if self._is_mix_playing:
            self.context.player.stop()
            self._is_mix_playing = False

    def _on_player_state_changed(self, state: str) -> None:
        """Update play/stop button states and manage position timer."""
        if not self._is_mix_playing:
            self.play_btn.setText("\u25b6")
            self._mix_position_timer.stop()
            return

        if state == "playing":
            self.play_btn.setText("\u23f8")
            self.stop_btn.setEnabled(True)
            self._mix_position_timer.start()
        elif state == "paused":
            self.play_btn.setText("\u25b6")
            self._mix_position_timer.stop()
        elif state == "stopped":
            self.play_btn.setText("\u25b6")
            self.stop_btn.setEnabled(False)
            self._mix_position_timer.stop()
            self._is_mix_playing = False

    def _poll_mix_position(self) -> None:
        """Poll player position and emit MIX_POSITION_UPDATE."""
        if self._is_mix_playing and self.context.player.is_playing():
            position = self.context.player.get_position()
            self.context.emit(Events.MIX_POSITION_UPDATE, position=position)

    def _on_mix_position_update(self, position: float) -> None:
        """Update waveform cursor from mix position event."""
        self.waveform_widget.set_position(position)

    def _on_track_loaded_from_library(self, track_id: int) -> None:
        """Handle a library track being loaded - mix playback stops."""
        self._is_mix_playing = False
        self._mix_position_timer.stop()
        self.play_btn.setText("\u25b6")

    def _on_waveform_seek(self, position: float) -> None:
        """Seek in the mix when user clicks on the waveform."""
        if not self.model.sheet.mix_filepath:
            return

        # Place cursor immediately for visual feedback
        self.waveform_widget.set_position(position)

        player = self.context.player
        current = player.current_file
        needs_load = current is None or str(current) != self.model.sheet.mix_filepath

        if needs_load:
            player.load(Path(self.model.sheet.mix_filepath))

        self._take_over_player()
        self._is_mix_playing = True

        if needs_load or not player.is_playing():
            player.play()
            # VLC ignores seek when just started — small delay then seek
            QTimer.singleShot(50, lambda: player.set_position(position))
        else:
            player.set_position(position)

    # --- Slots ---

    def _on_load_mix(self) -> None:
        """Open file dialog to load a mix."""
        # Use configured mix directory as default
        cue_config = getattr(self.context.config, "cue_maker", None)
        start_dir = ""
        if cue_config and hasattr(cue_config, "mix_directory"):
            start_dir = str(cue_config.mix_directory.expanduser())

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Load Mix File",
            start_dir,
            "Audio Files (*.mp3 *.flac *.wav *.aiff *.aif *.ogg *.m4a);;All Files (*)",
        )
        if filepath:
            self.mix_path_label.setText(Path(filepath).name)
            self.mix_path_label.setStyleSheet("")
            self.model.set_metadata(filepath, Path(filepath).stem, "")
            self.analyze_btn.setEnabled(True)
            self.play_btn.setEnabled(True)
            self.mix_load_requested.emit(filepath)
            self._start_waveform_generation(filepath)
            logger.info("[Cue Maker] Mix loaded: %s", filepath)

    def _start_waveform_generation(self, filepath: str) -> None:
        """Start background waveform generation for the mix, or load from cache."""
        # Stop any existing worker
        if self._waveform_worker is not None:
            self._waveform_worker.requestInterruption()
            self._waveform_worker.quit()
            self._waveform_worker.wait(5000)
            self._waveform_worker = None

        # Clear existing waveform
        self.waveform_widget.clear_waveform()

        # Check cache first
        from plugins.cue_maker.cache import load_cached_waveform

        cached = load_cached_waveform(filepath)
        if cached is not None:
            self.waveform_widget.display_waveform(cached)
            self._mix_duration_s = len(cached["bass"]) * 2048 / 11025
            logger.info("[Cue Maker] Loaded waveform from cache for %s", filepath)
            return

        # Generate waveform in background
        from plugins.waveform_visualizer import CompleteWaveformWorker

        chunk_duration = getattr(self.context.config, "waveform", None)
        chunk_dur = chunk_duration.chunk_duration if chunk_duration else 10.0

        self._mix_filepath = filepath
        self._waveform_worker = CompleteWaveformWorker(
            track_id=0,
            filepath=filepath,
            chunk_duration=chunk_dur,
        )
        self._waveform_worker.setObjectName("CueMaker-WaveformWorker")
        self._waveform_worker.progress_update.connect(self._on_waveform_progress)
        self._waveform_worker.complete.connect(self._on_waveform_complete)
        self._waveform_worker.error.connect(self._on_waveform_error)
        self._waveform_worker.start()
        logger.info("[Cue Maker] Waveform generation started for %s", filepath)

    def _on_waveform_progress(self, _track_id: int, partial_waveform: dict) -> None:
        """Update waveform display progressively."""
        self.waveform_widget.display_waveform(partial_waveform)
        # Re-add highlight region (display_waveform clears all plot items)
        if self._selected_row >= 0:
            self._update_highlight_region()

    def _on_waveform_complete(self, result: dict) -> None:
        """Handle waveform generation complete and save to cache."""
        waveform_data = result.get("waveform_data")
        self._mix_duration_s = result.get("duration", 0.0)
        if waveform_data:
            self.waveform_widget.display_waveform(waveform_data)

            # Save to cache
            mix_path = getattr(self, "_mix_filepath", None)
            if mix_path:
                from plugins.cue_maker.cache import save_waveform_cache

                save_waveform_cache(mix_path, waveform_data)

        # Re-add highlight region (display_waveform clears all plot items)
        if self._selected_row >= 0:
            self._update_highlight_region()

        logger.info("[Cue Maker] Waveform generation complete")

    def _on_waveform_error(self, error_message: str) -> None:
        """Handle waveform generation error."""
        logger.warning("[Cue Maker] Waveform generation failed: %s", error_message)

    def _on_row_selected(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """Update editor when table row selection changes."""
        if not current.isValid():
            self._selected_row = -1
            self._set_editor_enabled(False)
            self._update_highlight_region()
            return

        self._selected_row = current.row()
        entry = self.model.get_entry(self._selected_row)
        if entry:
            self._set_editor_enabled(True)
            self.time_input.setText(entry.to_display_time())
            self.artist_input.setText(entry.artist)
            self.title_input.setText(entry.title)
        self._update_highlight_region()

    def _update_highlight_region(self) -> None:
        """Update the highlight region on the waveform for the selected cue entry."""
        # Remove existing highlight
        if self._highlight_region is not None:
            self.waveform_widget.plot_widget.removeItem(self._highlight_region)
            self._highlight_region = None

        if self._selected_row < 0:
            return

        entry = self.model.get_entry(self._selected_row)
        if entry is None:
            return

        mix_duration = self._mix_duration_s
        if not mix_duration or mix_duration <= 0:
            return

        expected_length = self.waveform_widget.expected_length
        if expected_length <= 0:
            return

        start_time_s = entry.start_time_ms / 1000.0
        end_time_s = (entry.start_time_ms + entry.duration_ms) / 1000.0
        # Clamp to mix duration
        end_time_s = min(end_time_s, mix_duration)

        x_start = (start_time_s / mix_duration) * expected_length
        x_end = (end_time_s / mix_duration) * expected_length

        logger.info(
            "[Cue Maker] Highlight row=%d: cue=[%.1fs → %.1fs, dur=%.1fs] "
            "highlight=[x_start=%.1f, x_end=%.1f, width=%.1f] "
            "mix_duration=%.1fs expected_length=%d",
            self._selected_row,
            start_time_s,
            end_time_s,
            end_time_s - start_time_s,
            x_start,
            x_end,
            x_end - x_start,
            mix_duration,
            expected_length,
        )

        self._highlight_region = pg.LinearRegionItem(
            values=[x_start, x_end],
            brush=pg.mkBrush(100, 180, 255, 50),
            movable=False,
        )
        self.waveform_widget.plot_widget.addItem(self._highlight_region)

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
                "No entries to export.\nAdd at least one entry first.",
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
                QMessageBox.information(self, "Export", f"CUE file exported to:\n{filepath}")
                logger.info("[Cue Maker] Exported to %s", filepath)
            except (ValueError, OSError) as e:
                QMessageBox.critical(self, "Export Error", str(e))

    def _set_editor_enabled(self, enabled: bool) -> None:
        """Enable/disable entry editor controls."""
        self.time_input.setEnabled(enabled)
        self.artist_input.setEnabled(enabled)
        self.title_input.setEnabled(enabled)
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
        from jukebox.core.event_bus import Events

        self.progress_bar.setVisible(True)
        if current < 0:
            # Status message — show indeterminate progress bar
            self.progress_bar.setMaximum(0)
            self.progress_bar.setFormat(message)
            self.context.emit(Events.STATUS_MESSAGE, message=f"Cue Maker: {message}")
        else:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"{message} (%p%)")
            self.context.emit(
                Events.STATUS_MESSAGE, message=f"Cue Maker: {message} ({current}/{total})"
            )

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

    def stop_mix_playback(self) -> None:
        """Stop mix playback if active."""
        if self._is_mix_playing:
            self._mix_position_timer.stop()
            self.context.player.stop()
            self._is_mix_playing = False
        if self._highlight_region is not None:
            self.waveform_widget.plot_widget.removeItem(self._highlight_region)
            self._highlight_region = None

    def cleanup_workers(self) -> None:
        """Stop any running background workers."""
        if self._highlight_region is not None:
            self.waveform_widget.plot_widget.removeItem(self._highlight_region)
            self._highlight_region = None
        if self._waveform_worker is not None:
            self._waveform_worker.requestInterruption()
            self._waveform_worker.quit()
            self._waveform_worker.wait(5000)
            self._waveform_worker = None
