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
        self.waveform_widget = WaveformWidget()
        ui_builder.add_sidebar_widget(self.waveform_widget, "Waveform")

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
            waveform = np.frombuffer(cached[0], dtype=np.float32)
            self.waveform_widget.display_waveform(waveform)
        else:
            # Generate in background
            track = self.context.database.conn.execute(
                "SELECT filepath FROM tracks WHERE id = ?", (track_id,)
            ).fetchone()

            if track:
                self._generate_waveform(track_id, track["filepath"])

    def _generate_waveform(self, track_id: int, filepath: str) -> None:
        """Generate waveform in background thread."""
        self.worker = WaveformWorker(track_id, filepath)
        self.worker.finished.connect(self._on_waveform_generated)
        self.worker.start()

    def _on_waveform_generated(self, track_id: int, waveform: np.ndarray) -> None:
        """Handle waveform generation complete (main thread)."""
        # Cache in database (main thread - SQLite safe)
        try:
            self.context.database.conn.execute(
                """
                INSERT OR REPLACE INTO waveform_cache (track_id, waveform_data)
                VALUES (?, ?)
            """,
                (track_id, waveform.astype(np.float32).tobytes()),
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
    """Widget to display waveform."""

    def __init__(self) -> None:
        """Initialize widget."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI."""
        layout = QVBoxLayout()

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("k")
        layout.addWidget(self.plot_widget)

        self.setLayout(layout)

    def display_waveform(self, waveform: np.ndarray) -> None:
        """Display waveform data."""
        self.plot_widget.clear()
        self.plot_widget.plot(waveform, pen="g")


class WaveformWorker(QThread):
    """Background worker to generate waveform."""

    finished = Signal(int, np.ndarray)  # track_id, waveform

    def __init__(self, track_id: int, filepath: str):
        """Initialize worker."""
        super().__init__()
        self.track_id = track_id
        self.filepath = filepath

    def run(self) -> None:
        """Generate waveform."""
        try:
            import librosa

            # Load audio
            y, sr = librosa.load(self.filepath, sr=22050, mono=True)

            # Downsample for visualization
            hop_length = 512
            waveform = np.abs(y[::hop_length])

            # Normalize
            waveform = waveform / np.max(waveform) if np.max(waveform) > 0 else waveform

            self.finished.emit(self.track_id, waveform)

        except Exception as e:
            logging.error(f"Waveform generation failed: {e}")
