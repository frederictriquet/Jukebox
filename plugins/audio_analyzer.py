"""Audio analysis plugin - extracts musical features."""

import logging
import os
from typing import Any

import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from jukebox.core.event_bus import Events

# Whitelist of valid audio_analysis columns (prevents SQL injection)
AUDIO_ANALYSIS_COLUMNS: frozenset[str] = frozenset([
    # Core stats
    "tempo", "rms_energy", "spectral_centroid", "zero_crossing_rate",
    # Energy & dynamics
    "rms_mean", "rms_std", "rms_p10", "rms_p90", "peak_amplitude",
    "crest_factor", "loudness_variation",
    # Frequency band energies
    "sub_bass_mean", "sub_bass_ratio", "bass_mean", "bass_ratio",
    "low_mid_mean", "low_mid_ratio", "mid_mean", "mid_ratio",
    "high_mid_mean", "high_mid_ratio", "high_mean", "high_ratio",
    # Spectral features
    "spectral_centroid_std", "spectral_bandwidth", "spectral_rolloff",
    "spectral_flatness", "spectral_contrast", "spectral_entropy",
    # MFCC
    "mfcc_1", "mfcc_2", "mfcc_3", "mfcc_4", "mfcc_5",
    "mfcc_6", "mfcc_7", "mfcc_8", "mfcc_9", "mfcc_10",
    # Percussive vs harmonic
    "harmonic_energy", "percussive_energy", "perc_harm_ratio",
    "onset_strength_mean", "percussive_onset_rate",
    # Rhythm & tempo
    "tempo_confidence", "beat_interval_mean", "beat_interval_std",
    "onset_rate", "tempogram_periodicity",
    # Harmony
    "chroma_entropy", "chroma_centroid", "chroma_energy_std", "tonnetz_mean",
    # Structure
    "intro_energy_ratio", "core_energy_ratio", "outro_energy_ratio", "energy_slope",
    # Legacy (from waveform analysis)
    "dynamic_range",
])


def analyze_audio_file(filepath: str, extract_ml_features: bool = False) -> dict[str, float]:
    """Analyze audio file and extract features.

    Args:
        filepath: Path to audio file
        extract_ml_features: If True, extract full stats including tempo, brightness,
                            percussive, RMS, and comprehensive ML features (slower)

    Returns:
        Dict with ML features (only when extract_ml_features=True), empty dict otherwise

    Raises:
        Exception: If analysis fails
    """
    if not extract_ml_features:
        return {}

    import warnings

    import librosa

    # Suppress librosa/audioread warnings for corrupted files
    warnings.filterwarnings("ignore", category=UserWarning, module="librosa")

    # Load audio
    y, sr = librosa.load(filepath, sr=None, mono=True)

    if len(y) == 0:
        raise ValueError("Empty audio file")

    return _extract_ml_features(y, int(sr))


def _extract_ml_features(y: np.ndarray, sr: int) -> dict[str, float]:
    """Extract comprehensive ML features for learning.

    Args:
        y: Audio time series
        sr: Sample rate

    Returns:
        Dict with ~50 ML features including tempo, brightness, percussive, RMS
    """
    import librosa

    features: dict[str, float] = {}

    # Core stats: tempo, brightness (spectral_centroid), percussive (zcr), RMS
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    features["tempo"] = float(tempo) if tempo else 0.0

    rms = librosa.feature.rms(y=y)[0]
    features["rms_energy"] = float(np.mean(rms))

    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    features["spectral_centroid"] = float(np.mean(centroid))

    zcr = librosa.feature.zero_crossing_rate(y)[0]
    features["zero_crossing_rate"] = float(np.mean(zcr))

    # 1. Energy & dynamics (8 features)
    features["rms_mean"] = float(np.mean(rms))
    features["rms_std"] = float(np.std(rms))
    features["rms_p10"] = float(np.percentile(rms, 10))
    features["rms_p90"] = float(np.percentile(rms, 90))
    features["peak_amplitude"] = float(np.max(np.abs(y)))
    features["crest_factor"] = float(features["peak_amplitude"] / (features["rms_mean"] + 1e-10))
    features["loudness_variation"] = float(np.std(rms))

    # 2. Frequency band energies (12 features)
    # Compute STFT for band analysis
    stft = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)

    def band_energy(stft_mat: np.ndarray, freqs: np.ndarray, f_min: float, f_max: float) -> tuple[float, float]:
        """Compute mean energy and ratio for a frequency band."""
        mask = (freqs >= f_min) & (freqs < f_max)
        band = stft_mat[mask, :]
        band_mean = float(np.mean(band))
        total_energy = float(np.mean(stft_mat))
        ratio = band_mean / (total_energy + 1e-10)
        return band_mean, ratio

    # Sub-bass (20-60 Hz)
    features["sub_bass_mean"], features["sub_bass_ratio"] = band_energy(stft, freqs, 20, 60)
    # Bass (60-150 Hz)
    features["bass_mean"], features["bass_ratio"] = band_energy(stft, freqs, 60, 150)
    # Low-mid (150-500 Hz)
    features["low_mid_mean"], features["low_mid_ratio"] = band_energy(stft, freqs, 150, 500)
    # Mid (500-2000 Hz)
    features["mid_mean"], features["mid_ratio"] = band_energy(stft, freqs, 500, 2000)
    # High-mid (2-6 kHz)
    features["high_mid_mean"], features["high_mid_ratio"] = band_energy(stft, freqs, 2000, 6000)
    # High/treble (6-20 kHz)
    features["high_mean"], features["high_ratio"] = band_energy(stft, freqs, 6000, 20000)

    # 3. Spectral features (6 features) - centroid already computed
    features["spectral_centroid_std"] = float(np.std(centroid))
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
    features["spectral_bandwidth"] = float(np.mean(bandwidth))
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
    features["spectral_rolloff"] = float(np.mean(rolloff))
    flatness = librosa.feature.spectral_flatness(y=y)[0]
    features["spectral_flatness"] = float(np.mean(flatness))
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
    features["spectral_contrast"] = float(np.mean(contrast))
    # Spectral entropy
    spec_norm = stft / (np.sum(stft, axis=0, keepdims=True) + 1e-10)
    spec_entropy = -np.sum(spec_norm * np.log(spec_norm + 1e-10), axis=0)
    features["spectral_entropy"] = float(np.mean(spec_entropy))

    # 4. MFCC (10 coefficients)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=10)
    for i in range(10):
        features[f"mfcc_{i+1}"] = float(np.mean(mfcc[i, :]))

    # 5. Percussive vs harmonic (5 features)
    y_harmonic, y_percussive = librosa.effects.hpss(y)
    features["harmonic_energy"] = float(np.mean(librosa.feature.rms(y=y_harmonic)[0]))
    features["percussive_energy"] = float(np.mean(librosa.feature.rms(y=y_percussive)[0]))
    features["perc_harm_ratio"] = features["percussive_energy"] / (features["harmonic_energy"] + 1e-10)

    onset_env = librosa.onset.onset_strength(y=y_percussive, sr=sr)
    features["onset_strength_mean"] = float(np.mean(onset_env))
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)
    duration = len(y) / sr
    features["percussive_onset_rate"] = len(onsets) / duration if duration > 0 else 0.0

    # 6. Rhythm & tempo (5 additional features) - tempo already computed
    features["tempo_confidence"] = 1.0  # Placeholder (librosa doesn't return confidence easily)
    if len(beats) > 1:
        beat_times = librosa.frames_to_time(beats, sr=sr)
        beat_intervals = np.diff(beat_times)
        features["beat_interval_mean"] = float(np.mean(beat_intervals))
        features["beat_interval_std"] = float(np.std(beat_intervals))
    else:
        features["beat_interval_mean"] = 0.0
        features["beat_interval_std"] = 0.0

    # Onset rate
    all_onsets = librosa.onset.onset_detect(y=y, sr=sr)
    features["onset_rate"] = len(all_onsets) / duration if duration > 0 else 0.0

    # Tempogram dominant periodicity
    tempogram = librosa.feature.tempogram(onset_envelope=onset_env, sr=sr)
    features["tempogram_periodicity"] = float(np.mean(tempogram))

    # 7. Harmony (4 features)
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    chroma_norm = chroma / (np.sum(chroma, axis=0, keepdims=True) + 1e-10)
    chroma_entropy = -np.sum(chroma_norm * np.log(chroma_norm + 1e-10), axis=0)
    features["chroma_entropy"] = float(np.mean(chroma_entropy))
    features["chroma_centroid"] = float(np.mean(np.argmax(chroma, axis=0)))
    features["chroma_energy_std"] = float(np.std(np.sum(chroma, axis=0)))

    tonnetz = librosa.feature.tonnetz(y=y_harmonic, sr=sr)
    features["tonnetz_mean"] = float(np.mean(tonnetz))

    # 8. Structure (4 features)
    # Split track into intro (0-20%), core (20-80%), outro (80-100%)
    n_samples = len(y)
    intro_end = int(n_samples * 0.2)
    core_start = intro_end
    core_end = int(n_samples * 0.8)
    outro_start = core_end

    intro_energy = float(np.mean(np.abs(y[:intro_end])))
    core_energy = float(np.mean(np.abs(y[core_start:core_end])))
    outro_energy = float(np.mean(np.abs(y[outro_start:])))
    total_energy = float(np.mean(np.abs(y)))

    features["intro_energy_ratio"] = intro_energy / (total_energy + 1e-10)
    features["core_energy_ratio"] = core_energy / (total_energy + 1e-10)
    features["outro_energy_ratio"] = outro_energy / (total_energy + 1e-10)

    # Energy slope (linear regression of RMS over time)
    time_indices = np.arange(len(rms))
    slope, _ = np.polyfit(time_indices, rms, 1)
    features["energy_slope"] = float(slope)

    return features


class AudioAnalyzerPlugin:
    """Analyze audio tracks and extract musical features."""

    name = "audio_analyzer"
    version = "1.0.0"
    description = "Audio feature extraction (tempo, energy, etc.)"
    modes = ["curating"]  # Only show stats in curating mode (batch always runs)

    # Class variable to keep batch processor alive (contains orphan workers)
    _batch_processor: Any = None

    def __init__(self) -> None:
        """Initialize plugin."""
        self.context: Any = None
        self.analysis_widget: AnalysisWidget | None = None
        self.current_track_id: int | None = None

    def initialize(self, context: Any) -> None:
        """Initialize plugin."""
        self.context = context

        # Subscribe to events
        from jukebox.core.event_bus import Events

        context.subscribe(Events.TRACK_LOADED, self._on_track_loaded)
        context.subscribe(Events.AUDIO_ANALYSIS_COMPLETE, self._on_analysis_complete)


    def register_ui(self, ui_builder: Any) -> None:
        """Register analysis widget."""
        self.analysis_widget = AnalysisWidget()
        ui_builder.add_bottom_widget(self.analysis_widget)

        # Add menu for batch analysis
        menu = ui_builder.get_or_create_menu("&Tools")
        ui_builder.add_menu_separator(menu)
        ui_builder.add_menu_action(menu, "Analyze All Tracks...", self._start_batch_analysis)

    def _on_track_loaded(self, track_id: int) -> None:
        """Display track analysis when loaded, or add to priority queue if not cached."""
        if not self.analysis_widget:
            return

        # Store current track
        self.current_track_id = track_id

        # Check if analysis exists in cache (generated by waveform plugin)
        cached = self.context.database.analysis.get(track_id)

        if cached:
            # Display cached analysis
            self.analysis_widget.display_analysis(
                {
                    "tempo": cached["tempo"],
                    "energy": cached["energy"],
                    "bass_energy": cached["bass_energy"],
                    "mid_energy": cached["mid_energy"],
                    "treble_energy": cached["treble_energy"],
                    "spectral_centroid": cached["spectral_centroid"],
                    "zero_crossing_rate": cached["zero_crossing_rate"],
                    "rms_energy": cached["rms_energy"],
                    "dynamic_range": cached["dynamic_range"],
                }
            )
        else:
            # Analysis not available yet - add to priority queue if batch is running
            self.analysis_widget.show_analyzing()

            if (
                AudioAnalyzerPlugin._batch_processor
                and AudioAnalyzerPlugin._batch_processor.is_running
            ):
                # Get filepath
                track = self.context.database.tracks.get_by_id(track_id)

                if track:
                    item = (track_id, track["filepath"])
                    added = AudioAnalyzerPlugin._batch_processor.add_priority_item(item)
                    if added:
                        logging.info(f"[Audio Analysis] Track {track_id} added to priority queue")

    def _on_analysis_complete(self, track_id: int) -> None:
        """Handle audio analysis completion event."""
        if not self.analysis_widget:
            return

        # Only update if this is the currently displayed track
        if track_id != self.current_track_id:
            return

        # Reload analysis from database
        cached = self.context.database.analysis.get(track_id)

        if cached:
            self.analysis_widget.display_analysis(
                {
                    "tempo": cached["tempo"],
                    "energy": cached["energy"],
                    "bass_energy": cached["bass_energy"],
                    "mid_energy": cached["mid_energy"],
                    "treble_energy": cached["treble_energy"],
                    "spectral_centroid": cached["spectral_centroid"],
                    "zero_crossing_rate": cached["zero_crossing_rate"],
                    "rms_energy": cached["rms_energy"],
                    "dynamic_range": cached["dynamic_range"],
                }
            )

    def _start_batch_analysis(self) -> None:
        """Start batch analysis of all tracks in the current mode."""
        from jukebox.utils.batch_helper import start_batch_processing

        # Get current mode
        current_mode = self.context.config.ui.mode

        # Get tracks for current mode from database
        tracks = self.context.database.tracks.get_all(mode=current_mode)

        if not tracks:
            logging.info(f"[Batch Analysis] No tracks to analyze in {current_mode} mode")
            return

        logging.info(f"[Batch Analysis] Analyzing {current_mode} mode tracks")

        # Convert to list of tuples
        items = [(track["id"], track["filepath"]) for track in tracks]

        def needs_analysis(track_id: int, filepath: str) -> bool:
            """Check if track needs analysis."""
            analysis = self.context.database.analysis.get(track_id)
            # Analyze if no record OR if any key field is NULL
            if not analysis:
                return True
            return (
                analysis["tempo"] is None
                or analysis["spectral_centroid"] is None
                or analysis["zero_crossing_rate"] is None
                or analysis["rms_energy"] is None
                or analysis["rms_mean"] is None
            )

        def worker_factory(item: tuple[int, str]) -> QThread:
            """Create analysis worker for a track."""
            track_id, filepath = item
            return AnalysisWorker(track_id=track_id, filepath=filepath)

        start_batch_processing(
            name="Audio Analysis",
            batch_processor_holder=AudioAnalyzerPlugin,
            context=self.context,
            items=items,
            needs_processing_fn=needs_analysis,
            worker_factory=worker_factory,
            on_complete=self._on_batch_analysis_complete,
            on_error=self._on_batch_analysis_error,
            no_work_message="All tracks analyzed",
        )

    def _on_batch_analysis_complete(self, item: tuple[int, str], result: dict[str, float]) -> None:
        """Handle single analysis completion in batch."""
        track_id, filepath = item

        # Save to database (safe in main thread)
        try:
            # Filter columns against whitelist to prevent SQL injection
            safe_data = {col: result[col] for col in result if col in AUDIO_ANALYSIS_COLUMNS}
            if not safe_data:
                logging.warning(f"[Batch Analysis] No valid columns in result for track {track_id}")
                return

            # Log any rejected columns (should not happen in normal operation)
            rejected = set(result) - set(safe_data)
            if rejected:
                logging.warning(f"[Batch Analysis] Rejected invalid columns: {rejected}")

            # Save analysis using Database API
            self.context.database.analysis.save(track_id, safe_data)

            # Emit event to update UI if this track is currently displayed
            self.context.emit(Events.AUDIO_ANALYSIS_COMPLETE, track_id=track_id)

            # DEBUG level: show filename and feature count
            filename = os.path.basename(filepath)
            feature_count = len(safe_data)
            logging.debug(f"[Batch Analysis] Saved {feature_count} features for: {filename}")

        except Exception as e:
            logging.error(f"[Batch Analysis] Failed to save results for track {track_id}: {e}", exc_info=True)

    def _on_batch_analysis_error(self, item: tuple[int, str], error: str) -> None:
        """Handle batch analysis error."""
        track_id, filepath = item
        filename = os.path.basename(filepath)
        # DEBUG level: show which file failed (BatchProcessor already logged the error)
        logging.debug(f"[Batch Analysis] Failed file: {filename}")

    def activate(self, mode: str) -> None:
        """Activate plugin for this mode."""
        # Show stats widget in curating mode
        if self.analysis_widget:
            self.analysis_widget.setVisible(True)
        logging.debug(f"[Audio Analysis] Activated for {mode} mode")

    def deactivate(self, mode: str) -> None:
        """Deactivate plugin for this mode."""
        # Hide stats widget in jukebox mode (batch continues)
        if self.analysis_widget:
            self.analysis_widget.setVisible(False)
        logging.debug(f"[Audio Analysis] Deactivated for {mode} mode")

    def shutdown(self) -> None:
        """Cleanup on application exit."""
        # Stop batch processor if running (but keep it alive in class variable)
        if AudioAnalyzerPlugin._batch_processor:
            logging.debug("[Audio Analysis] Stopping batch processor during shutdown")
            AudioAnalyzerPlugin._batch_processor.stop()
            # Disconnect all signals from batch processor
            try:
                AudioAnalyzerPlugin._batch_processor.item_complete.disconnect()
                AudioAnalyzerPlugin._batch_processor.item_error.disconnect()
            except (RuntimeError, TypeError):
                pass
        # Don't set to None - keep it alive so orphan workers can finish

    def get_settings_schema(self) -> dict[str, Any]:
        """Return settings schema for configuration UI.

        Returns:
            Dict mapping setting keys to their configuration
        """
        return {}


class AnalysisWidget(QWidget):
    """Widget to display audio analysis results."""

    def __init__(self) -> None:
        """Initialize widget."""
        super().__init__()
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI."""
        from PySide6.QtWidgets import QVBoxLayout

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 5, 10, 5)
        main_layout.setSpacing(3)

        # Create labels with compact formatting
        self.energy_label = QLabel("Energy: --")
        self.bass_label = QLabel("Bass: --")
        self.mid_label = QLabel("Mid: --")
        self.treble_label = QLabel("Treble: --")
        self.dynamic_label = QLabel("Dynamic: --")
        self.tempo_label = QLabel("Tempo: --")
        self.centroid_label = QLabel("Brightness: --")
        self.zcr_label = QLabel("Percussive: --")
        self.rms_label = QLabel("RMS: --")

        # First row: waveform-based metrics
        row1 = QHBoxLayout()
        row1.setSpacing(15)
        row1.addWidget(QLabel("<b>Waveform:</b>"))
        row1.addWidget(self.energy_label)
        row1.addWidget(self.bass_label)
        row1.addWidget(self.mid_label)
        row1.addWidget(self.treble_label)
        row1.addWidget(self.dynamic_label)
        row1.addStretch()

        # Second row: advanced analysis metrics
        row2 = QHBoxLayout()
        row2.setSpacing(15)
        row2.addWidget(QLabel("<b>Analysis:</b>"))
        row2.addWidget(self.tempo_label)
        row2.addWidget(self.centroid_label)
        row2.addWidget(self.zcr_label)
        row2.addWidget(self.rms_label)
        row2.addStretch()

        main_layout.addLayout(row1)
        main_layout.addLayout(row2)

        self.setLayout(main_layout)
        self.setMaximumHeight(55)

    def show_analyzing(self) -> None:
        """Show analyzing state."""
        self.energy_label.setText("Energy: --")
        self.bass_label.setText("Bass: --")
        self.mid_label.setText("Mid: --")
        self.treble_label.setText("Treble: --")
        self.dynamic_label.setText("Dynamic: --")

    def display_analysis(self, analysis: dict[str, float | None]) -> None:
        """Display analysis results."""
        energy = analysis.get("energy")
        self.energy_label.setText(f"Energy: {energy:.3f}" if energy else "Energy: --")

        bass = analysis.get("bass_energy")
        self.bass_label.setText(f"Bass: {bass:.3f}" if bass else "Bass: --")

        mid = analysis.get("mid_energy")
        self.mid_label.setText(f"Mid: {mid:.3f}" if mid else "Mid: --")

        treble = analysis.get("treble_energy")
        self.treble_label.setText(f"Treble: {treble:.3f}" if treble else "Treble: --")

        dyn_range = analysis.get("dynamic_range")
        self.dynamic_label.setText(f"Dynamic: {dyn_range:.1f} dB" if dyn_range else "Dynamic: --")

        tempo = analysis.get("tempo")
        self.tempo_label.setText(f"Tempo: {tempo:.0f} BPM" if tempo else "Tempo: --")

        centroid = analysis.get("spectral_centroid")
        self.centroid_label.setText(
            f"Brightness: {centroid:.0f} Hz" if centroid else "Brightness: --"
        )

        zcr = analysis.get("zero_crossing_rate")
        self.zcr_label.setText(f"Percussive: {zcr:.3f}" if zcr else "Percussive: --")

        rms = analysis.get("rms_energy")
        self.rms_label.setText(f"RMS: {rms:.3f}" if rms else "RMS: --")


class AnalysisWorker(QThread):
    """Worker for batch audio analysis (for BatchProcessor)."""

    complete = Signal(dict)  # Result dict with analysis metrics
    error = Signal(str)  # Error message

    def __init__(self, track_id: int, filepath: str, parent: Any = None):
        """Initialize worker.

        Args:
            track_id: Track ID
            filepath: Path to audio file
            parent: Parent object
        """
        super().__init__(parent)
        self.track_id = track_id
        self.filepath = filepath
        # Set thread name for debugging
        self.setObjectName(f"AnalysisWorker-{track_id}-{os.path.basename(filepath)[:20]}")

    def run(self) -> None:
        """Perform analysis (always extracts full stats)."""
        try:
            analysis = analyze_audio_file(self.filepath, extract_ml_features=True)
            self.complete.emit(analysis)
        except ValueError as e:
            # Empty or invalid audio file - log as warning, not error
            filename = os.path.basename(self.filepath)
            error_msg = f"Skipping {filename}: {e}"
            logging.warning(f"[AudioAnalysisWorker] {error_msg}")
            self.error.emit(error_msg)
        except Exception as e:
            filename = os.path.basename(self.filepath)
            error_msg = f"Error analyzing {filename}: {e}"
            logging.error(f"[AudioAnalysisWorker] {error_msg}", exc_info=True)
            self.error.emit(error_msg)
