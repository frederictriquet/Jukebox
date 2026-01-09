"""Waveform visualizer plugin."""

import logging
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget


class WaveformVisualizerPlugin:
    """Visualize track waveforms."""

    name = "waveform_visualizer"
    version = "1.0.0"
    description = "Display track waveforms"

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None
        self.waveform_widget: WaveformWidget | None = None
        self.worker: WaveformWorker | None = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to track loaded event
        from jukebox.core.event_bus import Events

        self.context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)

    def register_ui(self, ui_builder: Any) -> None:
        """Add waveform widget."""
        waveform_config = self.context.config.waveform
        self.waveform_widget = WaveformWidget(waveform_config)

        # Connect position updates
        from jukebox.core.event_bus import Events

        self.context.subscribe("position_update", self._update_cursor)
        self.waveform_widget.position_clicked.connect(self._on_seek_requested)

        ui_builder.add_bottom_widget(self.waveform_widget)

    def _update_cursor(self, position: float) -> None:
        """Update cursor position."""
        if self.waveform_widget:
            self.waveform_widget.set_position(position)

    def _on_seek_requested(self, position: float) -> None:
        """Handle seek request from waveform click."""
        if self.context.app and hasattr(self.context.app, "player"):
            self.context.app.player.set_position(position)

    def _on_track_loaded(self, track_id: int) -> None:
        """Generate and show waveform."""
        if not self.waveform_widget:
            return

        # Check cache
        cached = self.context.database.conn.execute(
            "SELECT waveform_data FROM waveform_cache WHERE track_id = ?", (track_id,)
        ).fetchone()

        if cached:
            # Load from cache
            import pickle

            try:
                waveform = pickle.loads(cached[0])
                self.waveform_widget.display_waveform(waveform)
            except Exception:
                # Old format, clear and regenerate
                self.waveform_widget.clear_waveform()
                track = self.context.database.conn.execute(
                    "SELECT filepath FROM tracks WHERE id = ?", (track_id,)
                ).fetchone()
                if track:
                    self._generate_waveform(track_id, track["filepath"])
        else:
            # Not in cache - clear previous and generate in background
            self.waveform_widget.clear_waveform()

            track = self.context.database.conn.execute(
                "SELECT filepath FROM tracks WHERE id = ?", (track_id,)
            ).fetchone()

            if track:
                self._generate_waveform(track_id, track["filepath"])

    def _generate_waveform(self, track_id: int, filepath: str) -> None:
        """Generate waveform in background thread."""
        # Stop any existing worker
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(1000)  # Wait max 1 second
            if self.worker.isRunning():
                self.worker.terminate()

        # Start new worker
        self.worker = WaveformWorker(track_id, filepath)
        self.worker.finished.connect(self._on_waveform_generated)
        self.worker.start()

    def _on_waveform_generated(self, track_id: int, waveform: Any) -> None:
        """Handle waveform generation complete (main thread)."""
        # Cache in database (main thread - SQLite safe)
        try:
            import pickle

            # Serialize dict or array
            waveform_bytes = pickle.dumps(waveform)

            self.context.database.conn.execute(
                """
                INSERT OR REPLACE INTO waveform_cache (track_id, waveform_data)
                VALUES (?, ?)
            """,
                (track_id, waveform_bytes),
            )
            self.context.database.conn.commit()
        except Exception as e:
            logging.error(f"Failed to cache waveform: {e}")

        # Display
        if self.waveform_widget:
            self.waveform_widget.display_waveform(waveform)

    def shutdown(self) -> None:
        """Cleanup."""
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()


class WaveformWidget(QWidget):
    """Interactive waveform widget with playback cursor."""

    position_clicked = Signal(float)  # 0.0-1.0

    def __init__(self, waveform_config: Any = None) -> None:
        """Initialize widget."""
        super().__init__()
        self.waveform_data: np.ndarray | None = None
        self.cursor_line: Any = None
        self.waveform_config = waveform_config
        self._init_ui(waveform_config)

    def _init_ui(self, waveform_config: Any = None) -> None:
        """Initialize UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("k")
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.hideAxis("left")
        self.plot_widget.hideAxis("bottom")

        height = waveform_config.height if waveform_config else 120
        self.plot_widget.setMaximumHeight(height)
        self.plot_widget.setMinimumHeight(height)  # Keep constant height

        # Click to seek
        self.plot_widget.scene().sigMouseClicked.connect(self._on_click)

        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

        # Store config for rendering
        self.waveform_config = waveform_config

    def display_waveform(self, waveform: Any) -> None:
        """Display waveform data with 3 colors stacked (Engine DJ style)."""
        # waveform is a dict with bass, mid, treble arrays
        if isinstance(waveform, dict):
            bass = waveform.get("bass", np.array([]))
            mid = waveform.get("mid", np.array([]))
            treble = waveform.get("treble", np.array([]))
            self.waveform_data = bass  # Use bass for length reference
        else:
            # Fallback: single waveform
            self.waveform_data = waveform
            bass = mid = treble = waveform / 3

        self.plot_widget.clear()

        # Stack 3 bands vertically (Engine DJ style) - cumulative stacking
        if len(bass) > 0 and len(mid) > 0 and len(treble) > 0:
            x = np.arange(len(bass))

            # Get colors from config
            bass_color = self.waveform_config.bass_color if self.waveform_config else "#0066FF"
            mid_color = self.waveform_config.mid_color if self.waveform_config else "#00FF00"
            treble_color = self.waveform_config.treble_color if self.waveform_config else "#FFFFFF"

            # Treble on top (white) - draw first as background
            treble_total = bass + mid + treble
            self.plot_widget.plot(
                x, treble_total, pen=None,
                fillLevel=0, brush=pg.mkBrush(treble_color + "FF")
            )

            # Mid in middle (green) - covers bass+mid
            mid_total = bass + mid
            self.plot_widget.plot(
                x, mid_total, pen=None,
                fillLevel=0, brush=pg.mkBrush(mid_color + "FF")
            )

            # Bass at bottom (blue) - drawn last, on top visually
            self.plot_widget.plot(
                x, bass, pen=None,
                fillLevel=0, brush=pg.mkBrush(bass_color + "FF")
            )

        # Create cursor line
        cursor_color = self.waveform_config.cursor_color if self.waveform_config else "#FFFFFF"
        self.cursor_line = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(cursor_color, width=2))
        self.plot_widget.addItem(self.cursor_line)

    def clear_waveform(self) -> None:
        """Clear waveform display."""
        self.plot_widget.clear()
        self.waveform_data = None
        self.cursor_line = None
        # Keep widget visible to maintain layout space

    def set_position(self, position: float) -> None:
        """Set playback position (0.0-1.0)."""
        if self.cursor_line and self.waveform_data is not None:
            x = position * len(self.waveform_data)
            self.cursor_line.setPos(x)

    def _on_click(self, event: Any) -> None:
        """Handle click on waveform."""
        if self.waveform_data is None:
            return

        # Get click position
        mouse_point = self.plot_widget.plotItem.vb.mapSceneToView(event.scenePos())
        x = mouse_point.x()

        # Convert to position (0.0-1.0)
        position = x / len(self.waveform_data)
        position = max(0.0, min(1.0, position))

        self.position_clicked.emit(position)


class WaveformWorker(QThread):
    """Background worker to generate waveform."""

    finished = Signal(int, object)  # track_id, waveform (dict or ndarray)

    def __init__(self, track_id: int, filepath: str):
        """Initialize worker."""
        super().__init__()
        self.track_id = track_id
        self.filepath = filepath

    def run(self) -> None:
        """Generate 3-color waveform (bass/mid/treble)."""
        try:
            import librosa
            from scipy import signal

            # Load audio at lower sample rate for faster processing
            y, sr = librosa.load(self.filepath, sr=11025, mono=True)

            # Separate frequency bands
            # Bass: < 250 Hz
            sos_bass = signal.butter(4, 250, "lp", fs=sr, output="sos")
            bass = signal.sosfilt(sos_bass, y)

            # Mid: 250-4000 Hz
            sos_mid = signal.butter(4, [250, 4000], "bandpass", fs=sr, output="sos")
            mid = signal.sosfilt(sos_mid, y)

            # Treble: > 4000 Hz (limited by Nyquist at 11025/2 = 5512 Hz)
            sos_treble = signal.butter(4, 4000, "hp", fs=sr, output="sos")
            treble = signal.sosfilt(sos_treble, y)

            # Downsample more aggressively for visualization
            hop = 2048  # Less dense sampling
            bass_wave = np.abs(bass[::hop])
            mid_wave = np.abs(mid[::hop])
            treble_wave = np.abs(treble[::hop])

            # Normalize each
            bass_wave = bass_wave / np.max(bass_wave) if np.max(bass_wave) > 0 else bass_wave
            mid_wave = mid_wave / np.max(mid_wave) if np.max(mid_wave) > 0 else mid_wave
            treble_wave = treble_wave / np.max(treble_wave) if np.max(treble_wave) > 0 else treble_wave

            waveform_data = {"bass": bass_wave, "mid": mid_wave, "treble": treble_wave}

            self.finished.emit(self.track_id, waveform_data)

        except Exception as e:
            logging.error(f"Waveform generation failed: {e}")
