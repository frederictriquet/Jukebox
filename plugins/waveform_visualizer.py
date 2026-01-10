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

    # Class variable to keep orphan workers alive until they finish
    _orphan_workers: list[Any] = []

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None
        self.waveform_widget: WaveformWidget | None = None
        self.current_generation: dict[str, Any] | None = None  # Generation state tracking
        self.current_worker: WaveformWorker | None = None  # Keep reference to current worker

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
        """Generate waveform progressively using one thread per chunk."""
        # Clear waveform display immediately
        if self.waveform_widget:
            self.waveform_widget.clear_waveform()

        # If already generating for a different track, cancel by not continuing
        # (current chunk will finish naturally in ~1-2 seconds)
        if self.current_generation:
            # Disconnect current worker's signals before cancelling
            if self.current_worker:
                try:
                    self.current_worker.chunk_ready.disconnect()
                    self.current_worker.error.disconnect()
                except (RuntimeError, TypeError):
                    pass
                # Detach worker from parent and keep in orphan list
                self.current_worker.setParent(None)
                WaveformVisualizerPlugin._orphan_workers.append(self.current_worker)
                # Clean up finished workers from orphan list
                WaveformVisualizerPlugin._orphan_workers = [
                    w for w in WaveformVisualizerPlugin._orphan_workers if w.isRunning()
                ]
            # Mark old generation as cancelled
            self.current_generation = None
            self.current_worker = None

        # Initialize generation state
        try:
            import librosa

            # Get audio info to know total duration
            duration = librosa.get_duration(path=filepath)

            # Skip if duration is zero or very short
            if duration < 0.1:
                logging.warning(f"Track too short or empty: {duration}s for {filepath}")
                return

            sr = 11025  # Target sample rate
            hop = 2048  # Downsampling hop

            # Calculate expected total length for pre-allocation
            total_samples = int(duration * sr)
            expected_length = max((total_samples // hop) + 1, 1)

            # Pre-calculate filter coefficients (reuse for all chunks)
            from scipy import signal

            sos_bass = signal.butter(4, 250, "lp", fs=sr, output="sos")
            sos_mid = signal.butter(4, [250, 4000], "bandpass", fs=sr, output="sos")
            sos_treble = signal.butter(4, 4000, "hp", fs=sr, output="sos")

            # Initialize generation state
            self.current_generation = {
                "track_id": track_id,
                "filepath": filepath,
                "duration": duration,
                "sr": sr,
                "hop": hop,
                "expected_length": expected_length,
                "sos_bass": sos_bass,
                "sos_mid": sos_mid,
                "sos_treble": sos_treble,
                "full_bass": np.zeros(expected_length),
                "full_mid": np.zeros(expected_length),
                "full_treble": np.zeros(expected_length),
                "write_index": 0,
                "offset": 0.0,
            }

            # Start first chunk
            self._start_next_chunk()

        except Exception as e:
            logging.error(f"Failed to initialize waveform generation for {filepath}: {e}")
            self.current_generation = None

    def _start_next_chunk(self) -> None:
        """Start processing the next chunk."""
        if not self.current_generation:
            return

        gen = self.current_generation
        chunk_duration = self.context.config.waveform.chunk_duration

        # Check if we're done
        if gen["offset"] >= gen["duration"]:
            self._finalize_waveform()
            return

        # Calculate chunk duration (last chunk may be shorter)
        actual_chunk_duration = min(chunk_duration, gen["duration"] - gen["offset"])

        # Create worker for this chunk
        self.current_worker = WaveformWorker(
            track_id=gen["track_id"],
            filepath=gen["filepath"],
            offset=gen["offset"],
            chunk_duration=actual_chunk_duration,
            sr=gen["sr"],
            hop=gen["hop"],
            sos_bass=gen["sos_bass"],
            sos_mid=gen["sos_mid"],
            sos_treble=gen["sos_treble"],
        )

        # Connect signals
        self.current_worker.chunk_ready.connect(self._on_chunk_complete)
        self.current_worker.error.connect(self._on_chunk_error)

        # Start worker
        self.current_worker.start()

    def _on_chunk_complete(
        self, track_id: int, bass_chunk: np.ndarray, mid_chunk: np.ndarray, treble_chunk: np.ndarray
    ) -> None:
        """Handle chunk completion."""
        # Check if this is still the current generation
        if not self.current_generation or self.current_generation["track_id"] != track_id:
            # Stale chunk from cancelled generation, ignore
            return

        gen = self.current_generation

        # Skip if chunk is empty
        if len(bass_chunk) == 0:
            gen["offset"] += self.context.config.waveform.chunk_duration
            self._start_next_chunk()
            return

        # Write to pre-allocated arrays at correct position
        chunk_len = len(bass_chunk)
        end_index = min(gen["write_index"] + chunk_len, gen["expected_length"])
        actual_len = end_index - gen["write_index"]

        gen["full_bass"][gen["write_index"] : end_index] = bass_chunk[:actual_len]
        gen["full_mid"][gen["write_index"] : end_index] = mid_chunk[:actual_len]
        gen["full_treble"][gen["write_index"] : end_index] = treble_chunk[:actual_len]

        gen["write_index"] = end_index

        # Emit progressive update with partial data (normalized)
        current_data = gen["write_index"]

        # Skip progressive update if no data yet
        if current_data == 0 or gen["expected_length"] == 0:
            gen["offset"] += self.context.config.waveform.chunk_duration
            self._start_next_chunk()
            return

        bass_partial = gen["full_bass"][:current_data]
        mid_partial = gen["full_mid"][:current_data]
        treble_partial = gen["full_treble"][:current_data]

        # Normalize each band for progressive display
        bass_norm = bass_partial / np.max(bass_partial) if np.max(bass_partial) > 0 else bass_partial
        mid_norm = mid_partial / np.max(mid_partial) if np.max(mid_partial) > 0 else mid_partial
        treble_norm = (
            treble_partial / np.max(treble_partial) if np.max(treble_partial) > 0 else treble_partial
        )

        # Pad with zeros to expected length for stable display
        bass_display = np.zeros(gen["expected_length"])
        mid_display = np.zeros(gen["expected_length"])
        treble_display = np.zeros(gen["expected_length"])

        bass_display[:current_data] = bass_norm
        mid_display[:current_data] = mid_norm
        treble_display[:current_data] = treble_norm

        chunk_data = {"bass": bass_display, "mid": mid_display, "treble": treble_display}

        # Display partial waveform
        if self.waveform_widget:
            self.waveform_widget.display_waveform(chunk_data)

        # Move to next chunk
        gen["offset"] += self.context.config.waveform.chunk_duration
        self._start_next_chunk()

    def _on_chunk_error(self, track_id: int, error_msg: str) -> None:
        """Handle chunk error."""
        logging.error(f"Chunk error for track {track_id}: {error_msg}")

        # Check if this is still the current generation
        if not self.current_generation or self.current_generation["track_id"] != track_id:
            return

        # Disconnect worker signals before cancelling
        if self.current_worker:
            try:
                self.current_worker.chunk_ready.disconnect()
                self.current_worker.error.disconnect()
            except (RuntimeError, TypeError):
                pass

        # Cancel generation on error
        self.current_generation = None
        self.current_worker = None

    def _finalize_waveform(self) -> None:
        """Finalize waveform generation and cache results."""
        if not self.current_generation:
            return

        gen = self.current_generation
        actual_length = gen["write_index"]

        # Skip if no data was written
        if actual_length == 0:
            logging.warning(f"No waveform data generated for track {gen['track_id']}")
            self.current_generation = None
            return

        # Trim to actual length
        full_bass = gen["full_bass"][:actual_length]
        full_mid = gen["full_mid"][:actual_length]
        full_treble = gen["full_treble"][:actual_length]

        # Final normalization
        bass_wave = full_bass / np.max(full_bass) if np.max(full_bass) > 0 else full_bass
        mid_wave = full_mid / np.max(full_mid) if np.max(full_mid) > 0 else full_mid
        treble_wave = full_treble / np.max(full_treble) if np.max(full_treble) > 0 else full_treble

        waveform_data = {"bass": bass_wave, "mid": mid_wave, "treble": treble_wave}

        # Cache in database
        try:
            import pickle

            waveform_bytes = pickle.dumps(waveform_data)

            self.context.database.conn.execute(
                """
                INSERT OR REPLACE INTO waveform_cache (track_id, waveform_data)
                VALUES (?, ?)
            """,
                (gen["track_id"], waveform_bytes),
            )
            self.context.database.conn.commit()
        except Exception as e:
            logging.error(f"Failed to cache waveform: {e}")

        # Display final waveform
        if self.waveform_widget:
            self.waveform_widget.display_waveform(waveform_data)

        # Clear generation state
        self.current_generation = None
        self.current_worker = None

    def shutdown(self) -> None:
        """Cleanup."""
        # Disconnect signals from current worker
        if self.current_worker:
            try:
                self.current_worker.chunk_ready.disconnect()
                self.current_worker.error.disconnect()
            except (RuntimeError, TypeError):
                pass

            # Detach worker from parent and keep in orphan list
            self.current_worker.setParent(None)
            WaveformVisualizerPlugin._orphan_workers.append(self.current_worker)
            # Clean up finished workers from orphan list
            WaveformVisualizerPlugin._orphan_workers = [
                w for w in WaveformVisualizerPlugin._orphan_workers if w.isRunning()
            ]

        # Clear generation state - worker will finish naturally
        self.current_generation = None
        self.current_worker = None


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
    """Background worker to generate one waveform chunk."""

    chunk_ready = Signal(int, object, object, object)  # track_id, bass, mid, treble arrays
    error = Signal(int, str)  # track_id, error message

    def __init__(
        self,
        track_id: int,
        filepath: str,
        offset: float,
        chunk_duration: float,
        sr: int,
        hop: int,
        sos_bass: Any,
        sos_mid: Any,
        sos_treble: Any,
        parent: Any = None,
    ):
        """Initialize worker for single chunk.

        Args:
            track_id: Track ID for this chunk
            filepath: Path to audio file
            offset: Starting position in seconds
            chunk_duration: Duration of this chunk in seconds
            sr: Sample rate
            hop: Downsampling hop
            sos_bass: Pre-calculated bass filter coefficients
            sos_mid: Pre-calculated mid filter coefficients
            sos_treble: Pre-calculated treble filter coefficients
            parent: Parent object
        """
        super().__init__(parent)
        self.track_id = track_id
        self.filepath = filepath
        self.offset = offset
        self.chunk_duration = chunk_duration
        self.sr = sr
        self.hop = hop
        self.sos_bass = sos_bass
        self.sos_mid = sos_mid
        self.sos_treble = sos_treble

    def run(self) -> None:
        """Process single chunk."""
        try:
            import librosa
            from scipy import signal

            # Load chunk
            y, _ = librosa.load(
                self.filepath, sr=self.sr, mono=True, offset=self.offset, duration=self.chunk_duration
            )

            # Check if audio is empty
            if len(y) == 0:
                self.error.emit(self.track_id, "Empty audio chunk")
                return

            # Separate frequency bands
            bass = signal.sosfilt(self.sos_bass, y)
            mid = signal.sosfilt(self.sos_mid, y)
            treble = signal.sosfilt(self.sos_treble, y)

            # Downsample for visualization
            bass_chunk = np.abs(bass[:: self.hop])
            mid_chunk = np.abs(mid[:: self.hop])
            treble_chunk = np.abs(treble[:: self.hop])

            # Emit chunk data
            self.chunk_ready.emit(self.track_id, bass_chunk, mid_chunk, treble_chunk)

        except Exception as e:
            self.error.emit(self.track_id, str(e))
