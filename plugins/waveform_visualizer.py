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
        self.worker = WaveformWorker(
            track_id, filepath, self.context.config.waveform.chunk_duration
        )
        self.worker.chunk_ready.connect(self._on_waveform_chunk)
        self.worker.finished.connect(self._on_waveform_generated)
        self.worker.start()

    def _on_waveform_chunk(self, track_id: int, partial_waveform: Any) -> None:
        """Handle progressive waveform chunk (main thread)."""
        # Display partial waveform immediately
        if self.waveform_widget:
            self.waveform_widget.display_waveform(partial_waveform)

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

        # Remove all padding/margins
        self.plot_widget.setContentsMargins(0, 0, 0, 0)
        self.plot_widget.plotItem.setContentsMargins(0, 0, 0, 0)

        # Disable auto-range padding
        self.plot_widget.plotItem.vb.setDefaultPadding(0)
        self.plot_widget.plotItem.vb.enableAutoRange(enable=False)

        height = waveform_config.height if waveform_config else 120
        self.plot_widget.setMaximumHeight(height)
        self.plot_widget.setMinimumHeight(height)

        # Click to seek
        self.plot_widget.scene().sigMouseClicked.connect(self._on_click)

        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

        # Store config for rendering
        self.waveform_config = waveform_config

        # Create cursor line immediately at position 0
        cursor_color = waveform_config.cursor_color if waveform_config else "#FFFFFF"
        self.cursor_line = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(cursor_color, width=2))
        self.plot_widget.addItem(self.cursor_line)

        # Set initial viewport range with no padding
        self.plot_widget.setXRange(0, 100, padding=0)
        self.plot_widget.setYRange(0, 1, padding=0)

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
                x, treble_total, pen=None, fillLevel=0, brush=pg.mkBrush(treble_color + "FF")
            )

            # Mid in middle (green) - covers bass+mid
            mid_total = bass + mid
            self.plot_widget.plot(
                x, mid_total, pen=None, fillLevel=0, brush=pg.mkBrush(mid_color + "FF")
            )

            # Bass at bottom (blue) - drawn last, on top visually
            self.plot_widget.plot(
                x, bass, pen=None, fillLevel=0, brush=pg.mkBrush(bass_color + "FF")
            )

            # Set range to fit data exactly
            self.plot_widget.setXRange(0, len(bass), padding=0)
            self.plot_widget.setYRange(0, np.max(treble_total) * 1.05, padding=0)

        # Re-add cursor line after clear (cleared removes it)
        if self.cursor_line:
            self.plot_widget.addItem(self.cursor_line)
            self.cursor_line.setPos(0)

    def clear_waveform(self) -> None:
        """Clear waveform display."""
        self.plot_widget.clear()
        self.waveform_data = None
        # Re-add cursor line after clear
        if self.cursor_line:
            self.plot_widget.addItem(self.cursor_line)
            self.cursor_line.setPos(0)

    def set_position(self, position: float) -> None:
        """Set playback position (0.0-1.0)."""
        if self.cursor_line:
            if self.waveform_data is not None and len(self.waveform_data) > 0:
                x = position * len(self.waveform_data)
                self.cursor_line.setPos(x)
            else:
                # No waveform yet, use fixed range 0-100
                x = position * 100
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
    """Background worker to generate waveform progressively."""

    chunk_ready = Signal(int, object)  # track_id, partial waveform chunk
    finished = Signal(int, object)  # track_id, complete waveform (dict or ndarray)

    def __init__(self, track_id: int, filepath: str, chunk_duration: float = 10.0):
        """Initialize worker."""
        super().__init__()
        self.track_id = track_id
        self.filepath = filepath
        self.chunk_duration = chunk_duration  # seconds per chunk

    def run(self) -> None:
        """Generate 3-color waveform (bass/mid/treble) progressively."""
        try:
            import librosa
            from scipy import signal

            # Get audio info first to know total duration
            duration = librosa.get_duration(path=self.filepath)
            sr = 11025  # Target sample rate

            # Downsampling hop for visualization
            hop = 2048

            # Calculate expected total length for pre-allocation
            total_samples = int(duration * sr)
            expected_length = (total_samples // hop) + 1

            # Pre-allocate arrays with zeros (will fill progressively)
            full_bass = np.zeros(expected_length)
            full_mid = np.zeros(expected_length)
            full_treble = np.zeros(expected_length)

            # Pre-calculate filter coefficients (reuse for all chunks)
            sos_bass = signal.butter(4, 250, "lp", fs=sr, output="sos")
            sos_mid = signal.butter(4, [250, 4000], "bandpass", fs=sr, output="sos")
            sos_treble = signal.butter(4, 4000, "hp", fs=sr, output="sos")

            # Process in chunks
            offset = 0.0
            write_index = 0
            while offset < duration:
                # Load chunk
                chunk_dur = min(self.chunk_duration, duration - offset)
                y, _ = librosa.load(
                    self.filepath, sr=sr, mono=True, offset=offset, duration=chunk_dur
                )

                # Separate frequency bands
                bass = signal.sosfilt(sos_bass, y)
                mid = signal.sosfilt(sos_mid, y)
                treble = signal.sosfilt(sos_treble, y)

                # Downsample for visualization
                bass_chunk = np.abs(bass[::hop])
                mid_chunk = np.abs(mid[::hop])
                treble_chunk = np.abs(treble[::hop])

                # Write to pre-allocated array at correct position
                chunk_len = len(bass_chunk)
                end_index = min(write_index + chunk_len, expected_length)
                actual_len = end_index - write_index

                full_bass[write_index:end_index] = bass_chunk[:actual_len]
                full_mid[write_index:end_index] = mid_chunk[:actual_len]
                full_treble[write_index:end_index] = treble_chunk[:actual_len]

                write_index = end_index

                # Emit progressive update with partial data (normalized)
                # Only normalize non-zero portion for better visual feedback
                current_data = write_index
                bass_partial = full_bass[:current_data]
                mid_partial = full_mid[:current_data]
                treble_partial = full_treble[:current_data]

                # Normalize each band for progressive display
                bass_norm = (
                    bass_partial / np.max(bass_partial) if np.max(bass_partial) > 0 else bass_partial
                )
                mid_norm = (
                    mid_partial / np.max(mid_partial) if np.max(mid_partial) > 0 else mid_partial
                )
                treble_norm = (
                    treble_partial / np.max(treble_partial)
                    if np.max(treble_partial) > 0
                    else treble_partial
                )

                # Pad with zeros to expected length for stable display
                bass_display = np.zeros(expected_length)
                mid_display = np.zeros(expected_length)
                treble_display = np.zeros(expected_length)

                bass_display[:current_data] = bass_norm
                mid_display[:current_data] = mid_norm
                treble_display[:current_data] = treble_norm

                chunk_data = {"bass": bass_display, "mid": mid_display, "treble": treble_display}
                self.chunk_ready.emit(self.track_id, chunk_data)

                offset += self.chunk_duration

            # Final normalization - trim to actual length
            actual_length = write_index
            full_bass = full_bass[:actual_length]
            full_mid = full_mid[:actual_length]
            full_treble = full_treble[:actual_length]

            bass_wave = full_bass / np.max(full_bass) if np.max(full_bass) > 0 else full_bass
            mid_wave = full_mid / np.max(full_mid) if np.max(full_mid) > 0 else full_mid
            treble_wave = (
                full_treble / np.max(full_treble) if np.max(full_treble) > 0 else full_treble
            )

            waveform_data = {"bass": bass_wave, "mid": mid_wave, "treble": treble_wave}

            self.finished.emit(self.track_id, waveform_data)

        except Exception as e:
            logging.error(f"Waveform generation failed: {e}")
