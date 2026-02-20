"""Main widget for the Cue Maker plugin."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pyqtgraph as pg
from PySide6.QtCore import (
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QPainter,
    QPen,
    QPolygon,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from jukebox.core.event_bus import Events
from plugins.cue_maker.constants import (
    ACTION_DELETE,
    ACTION_IMPORT,
    ACTION_INSERT,
    ACTION_SEARCH,
    TableColumn,
)
from plugins.cue_maker.model import EntryStatus
from plugins.cue_maker.table_model import CueTableModel

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol

logger = logging.getLogger(__name__)

# Action definitions: (icon, tooltip)
_ACTIONS = [
    (ACTION_DELETE, "Delete entry"),
    (ACTION_INSERT, "Insert entry after"),
    (ACTION_IMPORT, "Import from library track"),
    (ACTION_SEARCH, "Search in library"),
]
_ACTION_ICON_WIDTH = 22

_HANDLE_TOLERANCE = 6
_MIN_DURATION_MS = 1000
_SNAP_THRESHOLD_PX = 5
_AUDIO_EXTENSIONS = ('.mp3', '.flac', '.wav', '.aiff', '.aif', '.ogg', '.m4a')


class CueTimingBar(QWidget):
    """Draggable timing bar showing start/end handles for the selected cue entry."""

    start_changed = Signal(int)
    end_changed = Signal(int)
    region_changed = Signal(int, int)  # (start_ms, end_ms) emitted during region drag

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setMouseTracking(True)

        self._mix_duration_ms: int = 0
        self._start_ms: int = 0
        self._end_ms: int = 0
        self._has_entry: bool = False
        self._dragging: str | None = None  # "start", "end", or "region"
        self._drag_offset_ms: int = 0  # offset from click to start_ms in region drag
        self._snap_points: list[int] = []

    # -- Public API --

    def set_mix_duration(self, duration_ms: int) -> None:
        """Set total mix duration in milliseconds."""
        self._mix_duration_ms = max(0, duration_ms)
        self.update()

    def set_entry(self, start_ms: int, end_ms: int) -> None:
        """Show handles for the given entry timing."""
        self._start_ms = start_ms
        self._end_ms = end_ms
        self._has_entry = True
        self.update()

    def clear_entry(self) -> None:
        """Hide handles (no entry selected)."""
        self._has_entry = False
        self._dragging = None
        self._snap_points: list[int] = []
        self.update()

    def set_snap_points(self, points: list[int]) -> None:
        """Set magnetic snap points (neighboring entry boundaries in ms)."""
        self._snap_points = points

    # -- Coordinate conversion --

    def _ms_to_x(self, ms: int) -> float:
        if self._mix_duration_ms <= 0:
            return 0.0
        return (ms / self._mix_duration_ms) * self.width()

    def _snap_ms(self, ms: int) -> int:
        """Snap ms to the nearest snap point if within pixel threshold."""
        for sp in self._snap_points:
            if abs(self._ms_to_x(ms) - self._ms_to_x(sp)) <= _SNAP_THRESHOLD_PX:
                return sp
        return ms

    def _x_to_ms(self, x: float) -> int:
        if self.width() <= 0:
            return 0
        return int((x / self.width()) * self._mix_duration_ms)

    # -- Paint --

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background bar
        painter.fillRect(0, 0, w, h, QColor(50, 50, 50))

        if not self._has_entry or self._mix_duration_ms <= 0:
            painter.end()
            return

        x_start = self._ms_to_x(self._start_ms)
        x_end = self._ms_to_x(self._end_ms)

        # Highlighted region between handles
        painter.fillRect(
            QRect(int(x_start), 0, int(x_end - x_start), h),
            QColor(100, 180, 255, 60),
        )

        # Draw snap point guides
        if self._dragging and self._snap_points:
            snap_pen = QPen(QColor(255, 255, 255, 80), 1, Qt.PenStyle.DotLine)
            painter.setPen(snap_pen)
            for sp in self._snap_points:
                sx = int(self._ms_to_x(sp))
                painter.drawLine(sx, 0, sx, h)

        # Draw handles
        self._draw_handle(painter, x_start, QColor(80, 140, 255), h)
        self._draw_handle(painter, x_end, QColor(255, 160, 50), h)

        painter.end()

    def _draw_handle(self, painter: QPainter, x: float, color: QColor, h: int) -> None:
        """Draw a vertical line + triangle marker at x."""
        ix = int(x)
        pen = QPen(color, 2)
        painter.setPen(pen)
        painter.drawLine(ix, 0, ix, h)

        # Small triangle at top
        triangle = QPolygon([QPoint(ix - 4, 0), QPoint(ix + 4, 0), QPoint(ix, 6)])
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(triangle)

    # -- Hit testing --

    def _hit_test(self, x: float) -> str | None:
        """Return 'start', 'end', 'region', or None based on click position."""
        x_start = self._ms_to_x(self._start_ms)
        x_end = self._ms_to_x(self._end_ms)
        if abs(x - x_start) <= _HANDLE_TOLERANCE:
            return "start"
        if abs(x - x_end) <= _HANDLE_TOLERANCE:
            return "end"
        if x_start < x < x_end:
            return "region"
        return None

    # -- Mouse interaction --

    def mousePressEvent(self, event: QEvent) -> None:  # noqa: N802
        if not self._has_entry or event.button() != Qt.MouseButton.LeftButton:
            return
        x = event.position().x()
        hit = self._hit_test(x)
        self._dragging = hit
        if hit == "region":
            self._drag_offset_ms = self._x_to_ms(x) - self._start_ms
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QEvent) -> None:  # noqa: N802
        if self._dragging is None:
            # Update cursor hint
            if self._has_entry:
                hit = self._hit_test(event.position().x())
                if hit in ("start", "end"):
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                elif hit == "region":
                    self.setCursor(Qt.CursorShape.OpenHandCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        ms = self._x_to_ms(event.position().x())

        if self._dragging == "start":
            ms = self._snap_ms(ms)
            ms = max(0, min(ms, self._end_ms - _MIN_DURATION_MS))
            if ms != self._start_ms:
                self._start_ms = ms
                self.update()
                self.start_changed.emit(ms)
        elif self._dragging == "end":
            ms = self._snap_ms(ms)
            ms = max(self._start_ms + _MIN_DURATION_MS, min(ms, self._mix_duration_ms))
            if ms != self._end_ms:
                self._end_ms = ms
                self.update()
                self.end_changed.emit(ms)
        elif self._dragging == "region":
            duration = self._end_ms - self._start_ms
            new_start = ms - self._drag_offset_ms
            new_start = self._snap_ms(new_start)
            # Clamp so the region stays within [0, mix_duration]
            new_start = max(0, min(new_start, self._mix_duration_ms - duration))
            new_end = new_start + duration
            if new_start != self._start_ms:
                self._start_ms = new_start
                self._end_ms = new_end
                self.update()
                self.region_changed.emit(new_start, new_end)

    def mouseReleaseEvent(self, event: QEvent) -> None:  # noqa: N802
        if self._dragging == "region":
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._dragging = None


class ActionsDelegate(QStyledItemDelegate):
    """Delegate that renders clickable action icons in the actions column."""

    action_triggered = Signal(int, int)  # row, action_index

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    @staticmethod
    def _actions_for_index(
        index: QModelIndex,
    ) -> list[tuple[str, str, int]]:
        """Return (icon, tooltip, global_action_index) tuples visible for this row."""
        actions: list[tuple[str, str, int]] = []
        for i, (icon, tooltip) in enumerate(_ACTIONS):
            if icon == ACTION_IMPORT:
                # Only show import button for manual entries
                model = index.model()
                if model is not None:
                    entry = model.get_entry(index.row())
                    if entry is None or entry.status != EntryStatus.MANUAL:
                        continue
            actions.append((icon, tooltip, i))
        return actions

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        """Paint action icons horizontally in the cell."""
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)

        # Draw selection/alternate background
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(option.palette.text().color())

        font = painter.font()
        font.setPointSize(11)
        painter.setFont(font)

        x = option.rect.left() + 2
        y = option.rect.top()
        h = option.rect.height()

        for icon, _tooltip, _gi in self._actions_for_index(index):
            icon_rect = QRect(x, y, _ACTION_ICON_WIDTH, h)
            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, icon)
            x += _ACTION_ICON_WIDTH

        painter.restore()

    def editorEvent(  # noqa: N802
        self,
        event: QEvent,
        model: QAbstractTableModel,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> bool:
        """Handle mouse clicks on action icons."""
        if event.type() != QEvent.Type.MouseButtonRelease:
            return False

        actions = self._actions_for_index(index)
        x_click = event.position().x() - option.rect.left() - 2  # type: ignore[union-attr]
        visual_idx = int(x_click // _ACTION_ICON_WIDTH)

        if 0 <= visual_idx < len(actions):
            _icon, _tooltip, global_idx = actions[visual_idx]
            self.action_triggered.emit(index.row(), global_idx)
            return True
        return False

    def helpEvent(  # noqa: N802
        self,
        event: QEvent,
        view: QTableView,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> bool:
        """Show tooltip for action icon under the cursor."""
        if event.type() != QEvent.Type.ToolTip:
            return super().helpEvent(event, view, option, index)

        actions = self._actions_for_index(index)
        x_hover = event.pos().x() - option.rect.left() - 2  # type: ignore[union-attr]
        visual_idx = int(x_hover // _ACTION_ICON_WIDTH)

        if 0 <= visual_idx < len(actions):
            from PySide6.QtWidgets import QToolTip

            QToolTip.showText(
                event.globalPos(),  # type: ignore[union-attr]
                actions[visual_idx][1],
                view,
            )
            return True
        return super().helpEvent(event, view, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        """Return size hint based on number of actions."""
        width = len(_ACTIONS) * _ACTION_ICON_WIDTH + 4
        return QSize(width, option.rect.height() if option.rect.height() > 0 else 24)


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
    import_requested = Signal(int)  # row index
    search_requested = Signal(int)  # row index

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
        self._cursor_inside_region: bool | None = None
        self._mix_duration_s: float = 0.0
        self._mix_position_timer = QTimer()
        self._mix_position_timer.setInterval(100)
        self._mix_position_timer.timeout.connect(self._poll_mix_position)
        self._init_ui()
        self._connect_signals()
        self._connect_player_events()
        # Accept drag and drop
        self.setAcceptDrops(True)

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

        # --- Timing bar (draggable start/end handles) ---
        self.timing_bar = CueTimingBar(self)
        layout.addWidget(self.timing_bar)

        # --- Middle: Table + Progress ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.table_view = self._create_table()
        layout.addWidget(self.table_view, stretch=1)

        self.setLayout(layout)

    def _create_mix_controls(self) -> QWidget:
        """Create the top bar with mix file controls."""
        group = QGroupBox()
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

        self.export_btn = QPushButton("Export CUE")
        self.export_btn.setToolTip("Export cue sheet to .cue file")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._on_export)
        h.addWidget(self.export_btn)

        self.import_cue_btn = QPushButton("Import CUE")
        self.import_cue_btn.setToolTip("Import cue sheet from .cue file")
        self.import_cue_btn.clicked.connect(self._on_import_cue)
        h.addWidget(self.import_cue_btn)

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

        # Actions delegate
        self._actions_delegate = ActionsDelegate(table)
        self._actions_delegate.action_triggered.connect(self._on_action_triggered)
        table.setItemDelegateForColumn(TableColumn.ACTIONS, self._actions_delegate)

        # Column sizing
        header = table.horizontalHeader()
        header.setSectionResizeMode(TableColumn.OVERLAP, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(TableColumn.TIME, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(TableColumn.ARTIST, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(TableColumn.TITLE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(TableColumn.CONFIDENCE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(TableColumn.DURATION, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(TableColumn.ACTIONS, QHeaderView.ResizeMode.Fixed)

        table.setColumnWidth(TableColumn.OVERLAP, 30)
        table.setColumnWidth(TableColumn.TIME, 60)
        table.setColumnWidth(TableColumn.CONFIDENCE, 80)
        table.setColumnWidth(TableColumn.DURATION, 60)
        actions_width = len(_ACTIONS) * _ACTION_ICON_WIDTH + 4
        table.setColumnWidth(TableColumn.ACTIONS, actions_width)

        # Selection change
        table.selectionModel().currentRowChanged.connect(self._on_row_selected)
        # Double-click: play mix from entry start
        table.doubleClicked.connect(self._on_entry_double_clicked)

        return table

    def _connect_signals(self) -> None:
        """Connect model signals."""
        self.model.layoutChanged.connect(self._update_export_button)
        self.model.dataChanged.connect(self._update_export_button)
        self.model.rowsInserted.connect(self._update_export_button)
        self.model.rowsRemoved.connect(self._update_export_button)
        self.timing_bar.start_changed.connect(self._on_timing_bar_start_changed)
        self.timing_bar.end_changed.connect(self._on_timing_bar_end_changed)
        self.timing_bar.region_changed.connect(self._on_timing_bar_region_changed)

    def _connect_player_events(self) -> None:
        """Connect to player and event bus for mix playback."""
        self.context.player.state_changed.connect(self._on_player_state_changed)
        self.context.subscribe(Events.TRACK_LOADED, self._on_track_loaded_from_library)
        self.context.subscribe(Events.MIX_POSITION_UPDATE, self._on_mix_position_update)
        self.waveform_widget.position_clicked.connect(self._on_waveform_seek)


    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore  # noqa: N802
        """Accept drag events for audio files."""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            # Check if any URL is an audio file
            for url in urls:
                path = url.toLocalFile()
                if path.lower().endswith(_AUDIO_EXTENSIONS):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore  # noqa: N802
        """Handle dropped audio files."""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            # Load the first audio file dropped
            for url in urls:
                path = url.toLocalFile()
                if path.lower().endswith(_AUDIO_EXTENSIONS):
                    self._load_mix_file(path)
                    event.acceptProposedAction()
                    return
        event.ignore()

    def _load_mix_file(self, filepath: str) -> None:
        """Load a mix file (used by both Load button and drag-drop).

        Resets the current state first: stops playback, clears the cuesheet
        and waveform so we start fresh with the new mix.
        """
        # 1. Stop current mix playback if active
        self.stop_mix_playback()

        # 2. Clear the cuesheet
        self.model.clear()

        # 3. Clear the waveform (done inside _start_waveform_generation too,
        #    but do it early so the UI feels responsive)
        self.waveform_widget.clear_waveform()
        self._mix_duration_s = 0.0
        self._selected_row = -1

        # 4. Load the new mix
        self.mix_path_label.setText(Path(filepath).name)
        self.mix_path_label.setStyleSheet("")
        self.model.set_metadata(filepath, Path(filepath).stem, "")
        self.analyze_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.mix_load_requested.emit(filepath)
        self._start_waveform_generation(filepath)

        # Load cached entries if available
        from plugins.cue_maker.cache import load_cached_entries

        cached_entries = load_cached_entries(filepath)
        if cached_entries:
            self.model.load_entries(cached_entries)

        logger.info("[Cue Maker] Mix loaded: %s", filepath)

    # --- Playback slots ---

    def _take_over_player(self) -> None:
        """Notify PlaybackController that the mix is taking over the player."""
        self.context.app.playback.release_track()

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
        """Poll player position, update cursor and highlight region color."""
        if self._is_mix_playing and self.context.player.is_playing():
            position = self.context.player.get_position()
            self.context.emit(Events.MIX_POSITION_UPDATE, position=position)
            self._update_region_color(position)

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
            self._load_mix_file(filepath)

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
            self.timing_bar.set_mix_duration(int(self._mix_duration_s * 1000))
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
        self.timing_bar.set_mix_duration(int(self._mix_duration_s * 1000))
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
        """Update timing bar / highlight when table row selection changes."""
        if not current.isValid():
            self._selected_row = -1
            self.timing_bar.clear_entry()
            self._update_highlight_region()
            return

        self._selected_row = current.row()
        self._refresh_editor_fields()
        self._update_highlight_region()

    def _on_entry_double_clicked(self, index: QModelIndex) -> None:
        """Play the mix starting from the double-clicked entry's start time."""
        if not index.isValid():
            return
        entry = self.model.get_entry(index.row())
        if entry is None or self._mix_duration_s <= 0:
            return
        position = (entry.start_time_ms / 1000.0) / self._mix_duration_s
        position = max(0.0, min(position, 1.0))
        self._on_waveform_seek(position)

    def _refresh_editor_fields(self) -> None:
        """Re-read current selection and update timing bar / highlight."""
        row = self.table_view.currentIndex().row()
        if row < 0:
            row = self._selected_row
        if row < 0:
            self.timing_bar.clear_entry()
            return
        self._selected_row = row
        entry = self.model.get_entry(row)
        if entry:
            end_ms = entry.start_time_ms + entry.duration_ms
            self.timing_bar.set_entry(entry.start_time_ms, end_ms)
            # Build snap points from neighboring entry boundaries
            snap_points: list[int] = []
            prev = self.model.get_entry(row - 1)
            if prev:
                snap_points.append(prev.start_time_ms + prev.duration_ms)
            nxt = self.model.get_entry(row + 1)
            if nxt:
                snap_points.append(nxt.start_time_ms)
            self.timing_bar.set_snap_points(snap_points)
        self._update_highlight_region()

    def _on_action_triggered(self, row: int, action_index: int) -> None:
        """Dispatch action from the actions column delegate."""
        # Select the row first
        self.table_view.setCurrentIndex(self.model.index(row, 0))
        if action_index == 0:
            self._on_delete_entry()
        elif action_index == 1:
            self._on_insert_entry_after()
        elif action_index == 2:
            self._on_import_from_library(row)
        elif action_index == 3:
            self._on_search_in_library(row)

    def _on_delete_entry(self) -> None:
        """Delete the selected entry."""
        row = self.table_view.currentIndex().row()
        if row >= 0:
            self.model.remove_entry(row)
            self._selected_row = -1

    def _on_insert_entry_after(self) -> None:
        """Insert a new manual entry after the selected entry."""
        row = self.table_view.currentIndex().row()
        if row < 0:
            return
        entry = self.model.get_entry(row)
        if entry is None:
            return
        # Place at end of current entry
        new_start = entry.start_time_ms + entry.duration_ms
        next_entry = self.model.get_entry(row + 1)
        if next_entry is not None and new_start >= next_entry.start_time_ms:
            new_start = next_entry.start_time_ms - 1000
        if new_start <= entry.start_time_ms:
            new_start = entry.start_time_ms + 1000
        self.model.add_manual_entry(new_start, "", "")
        # Select the newly inserted entry (search from end for most recent match)
        new_start_rounded = round(new_start / 1000) * 1000
        for i in range(self.model.rowCount() - 1, -1, -1):
            e = self.model.get_entry(i)
            if (
                e
                and e.start_time_ms == new_start_rounded
                and e.artist == ""
                and e.title == ""
                and e.status == EntryStatus.MANUAL
            ):
                self.table_view.setCurrentIndex(self.model.index(i, 0))
                break

    def _on_import_from_library(self, row: int) -> None:
        """Request import of library track info into the given row."""
        self.import_requested.emit(row)

    def _on_search_in_library(self, row: int) -> None:
        """Request search of entry's artist/title in the library."""
        self.search_requested.emit(row)

    def _on_timing_bar_start_changed(self, ms: int) -> None:
        """Handle drag of the start handle on the timing bar."""
        if self._selected_row < 0:
            return
        entry = self.model.get_entry(self._selected_row)
        if entry is None:
            return
        # Keep end fixed: compute new duration after start moves
        end_ms = entry.start_time_ms + entry.duration_ms
        idx = self.model.index(self._selected_row, TableColumn.TIME)
        minutes = (ms // 1000) // 60
        seconds = (ms // 1000) % 60
        self.model.setData(idx, f"{minutes:02d}:{seconds:02d}", Qt.ItemDataRole.EditRole)
        # Re-sort may have moved the entry — find it again
        for i in range(self.model.rowCount()):
            if self.model.get_entry(i) is entry:
                self.table_view.setCurrentIndex(self.model.index(i, 0))
                new_duration = end_ms - entry.start_time_ms
                if new_duration > 0:
                    self.model.update_duration(i, new_duration)
                break
        self._refresh_editor_fields()

    def _on_timing_bar_end_changed(self, ms: int) -> None:
        """Handle drag of the end handle on the timing bar."""
        if self._selected_row < 0:
            return
        entry = self.model.get_entry(self._selected_row)
        if entry is None:
            return
        new_duration = ms - entry.start_time_ms
        if new_duration <= 0:
            return
        self.model.update_duration(self._selected_row, new_duration)
        self._refresh_editor_fields()

    def _on_timing_bar_region_changed(self, start_ms: int, end_ms: int) -> None:
        """Handle drag of the entire region — update start and duration atomically."""
        if self._selected_row < 0:
            return
        entry = self.model.get_entry(self._selected_row)
        if entry is None:
            return
        duration_ms = end_ms - start_ms
        if duration_ms <= 0:
            return
        # Update start time via setData (triggers re-sort)
        idx = self.model.index(self._selected_row, TableColumn.TIME)
        minutes = (start_ms // 1000) // 60
        seconds = (start_ms // 1000) % 60
        self.model.setData(idx, f"{minutes:02d}:{seconds:02d}", Qt.ItemDataRole.EditRole)
        # Find entry after re-sort and set the exact duration
        for i in range(self.model.rowCount()):
            if self.model.get_entry(i) is entry:
                self.table_view.setCurrentIndex(self.model.index(i, 0))
                self.model.update_duration(i, duration_ms)
                break
        self._refresh_editor_fields()

    def _update_highlight_region(self) -> None:
        """Update the highlight region on the waveform for the selected cue entry."""
        # Remove existing highlight
        if self._highlight_region is not None:
            self.waveform_widget.plot_widget.removeItem(self._highlight_region)
            self._highlight_region = None

        # Reset color tracking so next poll re-evaluates
        self._cursor_inside_region = None

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

        logger.debug(
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
            brush=self._BRUSH_OUTSIDE,
            movable=False,
        )
        self.waveform_widget.plot_widget.addItem(self._highlight_region)

    # Highlight region brushes: inside (green tint) vs outside (blue tint)
    _BRUSH_INSIDE = pg.mkBrush(100, 255, 140, 60)
    _BRUSH_OUTSIDE = pg.mkBrush(100, 180, 255, 50)

    def _update_region_color(self, position: float) -> None:
        """Update highlight region color based on cursor position.

        Args:
            position: Playback position as a 0.0-1.0 ratio
        """
        if self._highlight_region is None:
            return

        region_range = self._highlight_region.getRegion()
        expected_length = self.waveform_widget.expected_length
        if expected_length <= 0:
            return

        cursor_x = position * expected_length
        inside = region_range[0] <= cursor_x <= region_range[1]

        if inside != self._cursor_inside_region:
            self._cursor_inside_region = inside
            brush = self._BRUSH_INSIDE if inside else self._BRUSH_OUTSIDE
            self._highlight_region.setBrush(brush)
            # Force full repaint of the region
            self._highlight_region.update()
            self.waveform_widget.plot_widget.update()

    def _on_export(self) -> None:
        """Export cue sheet to file."""
        if not self.model.has_confirmed_entries():
            QMessageBox.warning(
                self,
                "Export",
                "No confirmed entries to export.\n"
                "Confirm at least one entry before exporting.",
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

    def _on_import_cue(self) -> None:
        """Import a cue sheet from a .cue file, replacing current entries."""
        reply = QMessageBox.question(
            self,
            "Import CUE",
            "Loading a CUE file will replace the current cue sheet.\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        cue_config = getattr(self.context.config, "cue_maker", None)
        start_dir = ""
        if cue_config and hasattr(cue_config, "mix_directory"):
            start_dir = str(cue_config.mix_directory.expanduser())

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Import CUE File",
            start_dir,
            "CUE Files (*.cue);;All Files (*)",
        )
        if not filepath:
            return

        try:
            from plugins.cue_maker.exporter import CueExporter

            entries = CueExporter.parse(filepath)
            self.model.load_entries(entries)
            self._selected_row = -1
            self.timing_bar.clear_entry()
            QMessageBox.information(
                self,
                "Import CUE",
                f"Imported {len(entries)} tracks from:\n{Path(filepath).name}",
            )
            logger.info("[Cue Maker] Imported %d entries from %s", len(entries), filepath)
        except (ValueError, OSError) as e:
            QMessageBox.critical(self, "Import Error", str(e))

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
