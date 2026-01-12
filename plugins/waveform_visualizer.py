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
    modes = ["jukebox", "curating"]  # Active in both modes (waveform always visible)

    # Class variable to keep batch processor alive (contains orphan workers)
    _batch_processor: Any = None

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None
        self.waveform_widget: WaveformWidget | None = None
        self.current_track_id: int | None = None  # Currently displayed track

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to events
        from jukebox.core.event_bus import Events

        self.context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)
        self.context.subscribe(Events.TRACKS_ADDED, self._on_tracks_added)

        # Auto-start batch waveform generation at startup
        # Use a timer to defer until after UI is fully loaded
        from PySide6.QtCore import QTimer

        QTimer.singleShot(1000, self._start_batch_waveform)

    def _on_tracks_added(self) -> None:
        """Auto-generate missing waveforms when tracks are added."""
        self._start_batch_waveform()

    def register_ui(self, ui_builder: Any) -> None:
        """Add waveform widget."""
        waveform_config = self.context.config.waveform
        self.waveform_widget = WaveformWidget(waveform_config)

        # Connect position updates
        self.context.subscribe("position_update", self._update_cursor)
        self.waveform_widget.position_clicked.connect(self._on_seek_requested)

        ui_builder.add_bottom_widget(self.waveform_widget)

        # Add menu for batch waveform generation
        menu = ui_builder.add_menu("&Waveform")
        ui_builder.add_menu_action(
            menu, "Generate All Waveforms (Batch)", self._start_batch_waveform
        )

    def _update_cursor(self, position: float) -> None:
        """Update cursor position."""
        if self.waveform_widget:
            self.waveform_widget.set_position(position)

    def _on_seek_requested(self, position: float) -> None:
        """Handle seek request from waveform click."""
        self.context.player.set_position(position)

    def _on_track_loaded(self, track_id: int) -> None:
        """Display waveform from cache, or add to priority queue if not cached."""
        if not self.waveform_widget:
            return

        # Store current track ID
        self.current_track_id = track_id

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
                # Corrupted cache, clear
                self.waveform_widget.clear_waveform()
        else:
            # Not in cache - add to priority queue if batch is running
            self.waveform_widget.clear_waveform()

            if (
                WaveformVisualizerPlugin._batch_processor
                and WaveformVisualizerPlugin._batch_processor.is_running
            ):
                # Get filepath
                track = self.context.database.conn.execute(
                    "SELECT filepath FROM tracks WHERE id = ?", (track_id,)
                ).fetchone()

                if track:
                    item = (track_id, track["filepath"])
                    added = WaveformVisualizerPlugin._batch_processor.add_priority_item(item)
                    if added:
                        logging.info(f"[Waveform] Track {track_id} added to priority queue")

    def _start_batch_waveform(self) -> None:
        """Start batch waveform generation for all tracks."""
        # Stop any running batch
        if (
            WaveformVisualizerPlugin._batch_processor
            and WaveformVisualizerPlugin._batch_processor.is_running
        ):
            logging.info("Batch processor already running, stopping it first")
            WaveformVisualizerPlugin._batch_processor.stop()

        # Get all tracks
        tracks = self.context.database.conn.execute(
            "SELECT id, filepath FROM tracks ORDER BY id"
        ).fetchall()

        if not tracks:
            logging.info("[Batch Waveform] No tracks to generate waveforms for")
            return

        # Filter tracks without waveforms
        tracks_to_generate = []
        already_generated = 0

        import os

        for track in tracks:
            cached = self.context.database.conn.execute(
                "SELECT track_id FROM waveform_cache WHERE track_id = ?", (track["id"],)
            ).fetchone()

            filename = os.path.basename(track["filepath"])

            if not cached:
                tracks_to_generate.append((track["id"], track["filepath"]))
                logging.info(f"  Track {track['id']}: {filename} - NEEDS WAVEFORM")
            else:
                already_generated += 1
                logging.info(f"  Track {track['id']}: {filename} - already has waveform")

        logging.info(
            f"[Batch Waveform] Status: {already_generated} already done, {len(tracks_to_generate)} to generate (total: {len(tracks)})"
        )

        if not tracks_to_generate:
            logging.info("[Batch Waveform] All tracks already have waveforms")
            self.context.emit("status_message", message="All waveforms generated", color="#00FF00")
            return

        # Create batch processor
        from jukebox.core.batch_processor import BatchProcessor

        def worker_factory(item: tuple[int, str]) -> QThread:
            """Create a complete waveform worker for a track."""
            track_id, filepath = item
            worker = CompleteWaveformWorker(
                track_id=track_id,
                filepath=filepath,
                chunk_duration=self.context.config.waveform.chunk_duration,
            )
            # Connect progress updates for progressive display
            worker.progress_update.connect(self._on_waveform_progress)
            return worker

        WaveformVisualizerPlugin._batch_processor = BatchProcessor(
            name="Waveform Generation",
            worker_factory=worker_factory,
            context=self.context,
        )

        # Connect signals
        WaveformVisualizerPlugin._batch_processor.item_complete.connect(
            self._on_batch_waveform_complete
        )
        WaveformVisualizerPlugin._batch_processor.item_error.connect(self._on_batch_waveform_error)

        # Start batch processing
        WaveformVisualizerPlugin._batch_processor.start(tracks_to_generate)

    def _on_waveform_progress(self, track_id: int, partial_waveform: dict[str, Any]) -> None:
        """Handle progressive waveform updates during generation."""
        # Only display if this is the currently displayed track
        if track_id == self.current_track_id and self.waveform_widget:
            self.waveform_widget.display_waveform(partial_waveform)

    def _on_batch_waveform_complete(self, item: tuple[int, str], result: dict[str, Any]) -> None:
        """Handle single waveform completion in batch."""
        track_id, filepath = item

        # Save to database (safe in main thread)
        try:
            import os
            import pickle

            # Cache waveform
            waveform_bytes = pickle.dumps(result["waveform_data"])
            self.context.database.conn.execute(
                """
                INSERT OR REPLACE INTO waveform_cache (track_id, waveform_data)
                VALUES (?, ?)
            """,
                (track_id, waveform_bytes),
            )

            # Save audio analysis
            self.context.database.conn.execute(
                """
                INSERT OR REPLACE INTO audio_analysis (
                    track_id, energy, bass_energy, mid_energy, treble_energy, dynamic_range
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    track_id,
                    result["energy"],
                    result["bass_energy"],
                    result["mid_energy"],
                    result["treble_energy"],
                    result["dynamic_range"],
                ),
            )

            self.context.database.conn.commit()

            # If this is the currently displayed track, show the waveform
            if track_id == self.current_track_id and self.waveform_widget:
                self.waveform_widget.display_waveform(result["waveform_data"])
                logging.debug(f"[Waveform] Displayed waveform for current track {track_id}")

            # Emit event to notify analysis complete
            self.context.emit("audio_analysis_complete", track_id=track_id)

            # DEBUG level: show filename
            filename = os.path.basename(filepath)
            logging.debug(f"[Batch Waveform] Saved: {filename}")

        except Exception as e:
            logging.error(f"[Batch Waveform] Failed to save results for track {track_id}: {e}")

    def _on_batch_waveform_error(self, item: tuple[int, str], error: str) -> None:
        """Handle batch waveform error."""
        track_id, filepath = item
        import os

        filename = os.path.basename(filepath)
        # DEBUG level: show which file failed (BatchProcessor already logged the error)
        logging.debug(f"[Batch Waveform] Failed file: {filename}")

    def activate(self, mode: str) -> None:
        """Activate plugin for this mode."""
        # Waveform always visible in both modes
        logging.debug(f"[Waveform] Activated for {mode} mode")

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for this mode."""
        # Never called since active in both modes
        logging.debug(f"[Waveform] Deactivated for {mode} mode")

    def shutdown(self) -> None:
        """Cleanup on application exit."""
        # Stop batch processor if running (but keep it alive in class variable)
        if WaveformVisualizerPlugin._batch_processor:
            logging.debug("[Waveform] Stopping batch processor during shutdown")
            WaveformVisualizerPlugin._batch_processor.stop()
            # Disconnect all signals from batch processor
            try:
                WaveformVisualizerPlugin._batch_processor.item_complete.disconnect()
                WaveformVisualizerPlugin._batch_processor.item_error.disconnect()
            except (RuntimeError, TypeError):
                pass
        # Don't set to None - keep it alive so orphan workers can finish


class WaveformWidget(QWidget):
    """Interactive waveform widget with playback cursor."""

    position_clicked = Signal(float)  # 0.0-1.0

    def __init__(self, waveform_config: Any = None) -> None:
        """Initialize widget."""
        super().__init__()
        self.waveform_data: np.ndarray | None = None
        self.expected_length: int = (
            0  # Expected total length (for stable cursor during progressive display)
        )
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
            # Update expected length (for stable cursor positioning)
            # This is the full length, even for partial waveforms (padded with zeros)
            self.expected_length = len(bass)

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
            # Don't reset position - keep current position stable

    def clear_waveform(self) -> None:
        """Clear waveform display."""
        self.plot_widget.clear()
        self.waveform_data = None
        self.expected_length = 0
        # Re-add cursor line after clear
        if self.cursor_line:
            self.plot_widget.addItem(self.cursor_line)
            self.cursor_line.setPos(0)

    def set_position(self, position: float) -> None:
        """Set playback position (0.0-1.0)."""
        if self.cursor_line:
            # Use expected_length for stable cursor positioning
            # (even during progressive waveform display)
            if self.expected_length > 0:
                x = position * self.expected_length
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


class CompleteWaveformWorker(QThread):
    """Worker to generate complete waveform for a track (all chunks)."""

    complete = Signal(dict)  # Result dict with waveform_data and analysis metrics
    error = Signal(str)  # Error message
    progress_update = Signal(int, dict)  # track_id, partial waveform data

    def __init__(self, track_id: int, filepath: str, chunk_duration: float, parent: Any = None):
        """Initialize worker.

        Args:
            track_id: Track ID
            filepath: Path to audio file
            chunk_duration: Duration of each chunk in seconds
            parent: Parent object
        """
        super().__init__(parent)
        self.track_id = track_id
        self.filepath = filepath
        self.chunk_duration = chunk_duration
        # Set thread name for debugging
        import os

        self.setObjectName(f"WaveformWorker-{track_id}-{os.path.basename(filepath)[:20]}")

    def run(self) -> None:
        """Generate complete waveform."""
        try:
            import librosa
            from scipy import signal

            # Get audio duration
            duration = librosa.get_duration(path=self.filepath)

            if duration < 0.1:
                self.error.emit(f"Track too short or empty: {duration}s")
                return

            # Parameters
            sr = 11025
            hop = 2048

            # Pre-calculate filter coefficients
            sos_bass = signal.butter(4, 250, "lp", fs=sr, output="sos")
            sos_mid = signal.butter(4, [250, 4000], "bandpass", fs=sr, output="sos")
            sos_treble = signal.butter(4, 4000, "hp", fs=sr, output="sos")

            # Pre-allocate arrays
            total_samples = int(duration * sr)
            expected_length = max((total_samples // hop) + 1, 1)

            full_bass = np.zeros(expected_length)
            full_mid = np.zeros(expected_length)
            full_treble = np.zeros(expected_length)

            write_index = 0
            offset = 0.0

            # Process all chunks
            while offset < duration:
                actual_chunk_duration = min(self.chunk_duration, duration - offset)

                # Load chunk
                y, _ = librosa.load(
                    self.filepath, sr=sr, mono=True, offset=offset, duration=actual_chunk_duration
                )

                if len(y) == 0:
                    break

                # Separate frequency bands
                bass = signal.sosfilt(sos_bass, y)
                mid = signal.sosfilt(sos_mid, y)
                treble = signal.sosfilt(sos_treble, y)

                # Downsample
                bass_chunk = np.abs(bass[::hop])
                mid_chunk = np.abs(mid[::hop])
                treble_chunk = np.abs(treble[::hop])

                # Write to arrays
                chunk_len = len(bass_chunk)
                end_index = min(write_index + chunk_len, expected_length)
                actual_len = end_index - write_index

                full_bass[write_index:end_index] = bass_chunk[:actual_len]
                full_mid[write_index:end_index] = mid_chunk[:actual_len]
                full_treble[write_index:end_index] = treble_chunk[:actual_len]

                write_index = end_index
                offset += self.chunk_duration

                # Emit progressive update after each chunk
                if write_index > 0:
                    # Create partial normalized waveforms for display
                    bass_partial = full_bass[:write_index]
                    mid_partial = full_mid[:write_index]
                    treble_partial = full_treble[:write_index]

                    # Normalize
                    bass_norm = (
                        bass_partial / np.max(bass_partial)
                        if np.max(bass_partial) > 0
                        else bass_partial
                    )
                    mid_norm = (
                        mid_partial / np.max(mid_partial)
                        if np.max(mid_partial) > 0
                        else mid_partial
                    )
                    treble_norm = (
                        treble_partial / np.max(treble_partial)
                        if np.max(treble_partial) > 0
                        else treble_partial
                    )

                    # Pad to expected length for stable display
                    bass_display = np.zeros(expected_length)
                    mid_display = np.zeros(expected_length)
                    treble_display = np.zeros(expected_length)

                    bass_display[:write_index] = bass_norm
                    mid_display[:write_index] = mid_norm
                    treble_display[:write_index] = treble_norm

                    partial_waveform = {
                        "bass": bass_display,
                        "mid": mid_display,
                        "treble": treble_display,
                    }

                    # Emit progress update
                    self.progress_update.emit(self.track_id, partial_waveform)

            # Trim to actual length
            full_bass = full_bass[:write_index]
            full_mid = full_mid[:write_index]
            full_treble = full_treble[:write_index]

            if write_index == 0:
                self.error.emit("No waveform data generated")
                return

            # Calculate analysis metrics
            bass_energy = float(np.mean(full_bass))
            mid_energy = float(np.mean(full_mid))
            treble_energy = float(np.mean(full_treble))
            energy = bass_energy + mid_energy + treble_energy
            dynamic_range = float(
                20 * np.log10(np.max(full_bass + full_mid + full_treble) + 1e-10)
                - 20 * np.log10(np.mean(full_bass + full_mid + full_treble) + 1e-10)
            )

            # Normalize
            bass_wave = full_bass / np.max(full_bass) if np.max(full_bass) > 0 else full_bass
            mid_wave = full_mid / np.max(full_mid) if np.max(full_mid) > 0 else full_mid
            treble_wave = (
                full_treble / np.max(full_treble) if np.max(full_treble) > 0 else full_treble
            )

            # Emit result
            result = {
                "waveform_data": {
                    "bass": bass_wave,
                    "mid": mid_wave,
                    "treble": treble_wave,
                },
                "energy": energy,
                "bass_energy": bass_energy,
                "mid_energy": mid_energy,
                "treble_energy": treble_energy,
                "dynamic_range": dynamic_range,
            }

            self.complete.emit(result)

        except Exception as e:
            self.error.emit(str(e))
