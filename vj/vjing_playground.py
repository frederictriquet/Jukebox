#!/usr/bin/env python3
"""VJing Effects Playground — standalone app for previewing VJing effects in real-time.

Usage:
    uv run python tools/vjing_playground.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add project root to path so we can import jukebox/plugins modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "plugins"))

import socket
import struct
import threading

import numpy as np
import vlc
from PySide6.QtCore import Qt, QTimer

try:
    import sounddevice as sd

    HAS_SOUNDDEVICE = True
except ImportError:
    sd = None  # type: ignore[assignment]
    HAS_SOUNDDEVICE = False
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from video_exporter.layers.vjing_layer import VJingLayer

from jukebox.core.config import load_config
from jukebox.core.database import Database

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

PREVIEW_SIZE = 512
LED_PANEL_SIZE = 64  # render resolution for LED panel
LED_PANEL_DISPLAY = 256  # display size (64x64 scaled up with nearest-neighbor)
FPS = 30
DB_PATH = Path.home() / ".jukebox" / "jukebox.db"

# Microphone live mode
MIC_DURATION = 3600  # 1-hour session buffer (frames = MIC_DURATION * FPS)
MIC_SR = 22050
MIC_BLOCK_SIZE = 2048  # ~93ms at 22050 Hz — good low-freq resolution


def _discover_effects() -> list[str]:
    """Auto-discover effects by introspecting _render_* methods on VJingLayer.

    Starts from AVAILABLE_EFFECTS, then appends any newly discovered _render_*
    methods not already listed (excluding internal orchestration methods).
    """
    # Internal methods that follow _render_* naming but aren't actual effects
    internal = {"with_transitions", "gpu_effect"}

    known = list(VJingLayer.AVAILABLE_EFFECTS)
    known_set = set(known)

    for name in sorted(dir(VJingLayer)):
        if name.startswith("_render_") and callable(getattr(VJingLayer, name)):
            effect_name = name[len("_render_") :]
            if effect_name not in known_set and effect_name not in internal:
                known.append(effect_name)
                known_set.add(effect_name)

    return known


# Genre button states
STATE_OFF = 0  # grey — indifferent
STATE_ON = 1  # green — must have
STATE_EXCLUDE = 2  # red — must not have

STATE_STYLES = {
    STATE_OFF: "QPushButton { background: #555; color: #ccc; font-weight: bold; }",
    STATE_ON: "QPushButton { background: #2a2; color: white; font-weight: bold; }",
    STATE_EXCLUDE: "QPushButton { background: #a22; color: white; font-weight: bold; }",
}


class MicrophoneSource:
    """Real-time microphone capture with audio feature extraction."""

    def __init__(self, sr: int = MIC_SR, block_size: int = MIC_BLOCK_SIZE) -> None:
        self.sr = sr
        self.block_size = block_size
        # Ring buffer: 4 blocks (~370 ms at 22050 Hz)
        self._buffer = np.zeros(block_size * 4, dtype=np.float32)
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None

        # Beat detection state
        self._last_beat_frame = -100
        self._bass_history: list[float] = []

        # Auto-gain: running max with slow decay for normalization
        self._running_max: float = 1e-6

        # Pre-compute FFT band masks
        n_fft = block_size * 2
        freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
        self._n_fft = n_fft
        self._bass_mask = (freqs >= 20) & (freqs < 250)
        self._mid_mask = (freqs >= 250) & (freqs < 4000)
        self._treble_mask = freqs >= 4000

        # 32-band spectrum edges
        self._n_bands = 32
        n_bins = len(freqs)
        self._band_edges = np.linspace(0, n_bins, self._n_bands + 1, dtype=int)

    def start(self) -> None:
        if not HAS_SOUNDDEVICE:
            raise RuntimeError("sounddevice is not installed (pip install sounddevice)")
        self._stream = sd.InputStream(
            samplerate=self.sr,
            channels=1,
            blocksize=self.block_size,
            callback=self._callback,
            dtype="float32",
        )
        self._stream.start()
        log.info("[Mic] Started microphone capture at %d Hz, block=%d", self.sr, self.block_size)

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            log.info("[Mic] Stopped microphone capture")

    @property
    def is_active(self) -> bool:
        return self._stream is not None and self._stream.active

    def _callback(
        self, indata: np.ndarray, frames: int, _time_info: object, status: object
    ) -> None:
        if status:
            log.debug("[Mic] callback status: %s", status)
        with self._lock:
            n = min(frames, len(indata))
            self._buffer = np.roll(self._buffer, -n)
            self._buffer[-n:] = indata[:n, 0]

    def get_audio_features(self, frame_idx: int) -> dict:
        """Compute real-time audio features from current buffer."""
        with self._lock:
            chunk = self._buffer.copy()

        # FFT
        fft_full = np.abs(np.fft.rfft(chunk, n=self._n_fft))

        # Per-band RMS energy
        bass_e = float(np.sqrt(np.mean(fft_full[self._bass_mask] ** 2)))
        mid_e = float(np.sqrt(np.mean(fft_full[self._mid_mask] ** 2)))
        treble_e = float(np.sqrt(np.mean(fft_full[self._treble_mask] ** 2)))

        # Auto-gain normalization (slow decay so visuals stay dynamic)
        peak = max(bass_e, mid_e, treble_e)
        self._running_max = max(peak * 1.2, self._running_max * 0.998)
        norm = max(self._running_max, 1e-6)
        bass_n = min(1.0, bass_e / norm)
        mid_n = min(1.0, mid_e / norm)
        treble_n = min(1.0, treble_e / norm)
        energy = (bass_n + mid_n + treble_n) / 3.0

        # 32-band spectrum
        bands = np.zeros(self._n_bands)
        for i in range(self._n_bands):
            s, e = self._band_edges[i], self._band_edges[i + 1]
            if s < e:
                bands[i] = np.mean(fft_full[s:e])
        max_band = float(np.max(bands))
        if max_band > 0:
            bands /= max_band

        # Beat detection: bass spike above recent average
        self._bass_history.append(bass_n)
        if len(self._bass_history) > 30:
            self._bass_history.pop(0)
        avg_bass = float(np.mean(self._bass_history))
        min_interval = 7  # ~4 beats/sec at 30 fps
        is_beat = bass_n > max(0.5, avg_bass * 1.5) and (
            frame_idx - self._last_beat_frame
        ) >= min_interval
        if is_beat:
            self._last_beat_frame = frame_idx

        return {
            "energy": energy,
            "bass": bass_n,
            "mid": mid_n,
            "treble": treble_n,
            "fft": bands,
            "is_beat": is_beat,
        }


class LiveVJingLayer(VJingLayer):
    """VJingLayer variant for real-time microphone input.

    Skips the heavy audio pre-computation (frequency filtering, full-track FFT,
    beat detection) and instead accepts live audio features frame-by-frame via
    the ``live_ctx`` attribute.
    """

    live_ctx: dict | None = None

    def _precompute(self) -> None:
        """Allocate empty feature arrays and init effects (no audio analysis)."""
        n = self.total_frames
        self.energy = np.zeros(n)
        self.bass_energy = np.zeros(n)
        self.mid_energy = np.zeros(n)
        self.treble_energy = np.zeros(n)
        self.fft_data: list[np.ndarray] = [np.zeros(32) for _ in range(n)]
        self.beats: list[int] = []
        self._has_frequency_bands = True

        # Init per-effect state (particles, constellation, etc.)
        for name in self.active_effects:
            init_fn = getattr(self, f"_init_{name}", None)
            if init_fn:
                init_fn()

        if self._pending_gpu_init:
            self._init_gpu_renderer()

    def render(self, frame_idx: int, time_pos: float) -> "Image.Image":  # type: ignore[name-defined] # noqa: F821
        """Inject live audio context then delegate to parent render."""
        if self.live_ctx is not None:
            safe = min(frame_idx, self.total_frames - 1)
            ctx = self.live_ctx
            self.energy[safe] = ctx["energy"]
            self.bass_energy[safe] = ctx["bass"]
            self.mid_energy[safe] = ctx["mid"]
            self.treble_energy[safe] = ctx["treble"]
            self.fft_data[safe] = ctx["fft"]
            if ctx["is_beat"] and (not self.beats or self.beats[-1] != frame_idx):
                self.beats.append(frame_idx)
        return super().render(frame_idx, time_pos)


class VJingPlayground(QMainWindow):
    """Standalone VJing effects playground."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VJing Effects Playground")
        self.setMinimumSize(1100, 900)

        # Load config for genre codes
        self._config = load_config()

        # Database
        self._db = Database(DB_PATH)
        self._db.connect()

        # Audio state
        self._audio: np.ndarray | None = None
        self._sr: int = 22050
        self._duration: float = 0.0
        self._current_filepath: str = ""

        # VJing state
        self._vjing_layer: VJingLayer | None = None
        self._led_layer: VJingLayer | None = None
        self._current_palette = "neon"
        self._frame_idx = 0

        # VLC
        self._vlc_instance = vlc.Instance("--no-video", "--quiet")
        self._vlc_player: vlc.MediaPlayer = self._vlc_instance.media_player_new()

        # All tracks cache (for genre filtering in memory)
        self._all_tracks: list[dict] = []
        self._displayed_tracks: list[dict] = []

        # Genre button states
        self._genre_states: dict[str, int] = {}
        self._slider_dragging = False

        # Microphone live mode
        self._mic_mode = False
        self._mic_source: MicrophoneSource | None = None

        # ESP32 UDP sender
        self._esp32_socket: socket.socket | None = None
        self._esp32_ip: str = "ledpanel.local"
        self._esp32_frame_number: int = 0

        # Preview timer
        self._timer = QTimer()
        self._timer.setInterval(1000 // FPS)
        self._timer.timeout.connect(self._update_frame)

        # VLC position sync timer
        self._position_timer = QTimer()
        self._position_timer.setInterval(250)
        self._position_timer.timeout.connect(self._sync_position_from_vlc)

        self._setup_ui()
        self._load_tracks()

    # ─── UI Setup ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # Left panel
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # Search bar
        self._search_bar = QLineEdit()
        self._search_bar.setPlaceholderText("Search tracks...")
        self._search_bar.setClearButtonEnabled(True)
        self._search_debounce = QTimer()
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(300)
        self._search_debounce.timeout.connect(self._on_search)
        self._search_bar.textChanged.connect(lambda _: self._search_debounce.start())
        left_layout.addWidget(self._search_bar)

        # Genre filter buttons
        genre_box = QGroupBox("Genre Filter")
        genre_layout = QHBoxLayout(genre_box)
        genre_layout.setContentsMargins(4, 4, 4, 4)
        genre_layout.setSpacing(2)
        self._genre_buttons: dict[str, QPushButton] = {}
        for gc in self._config.genre_editor.codes:
            btn = QPushButton(gc.code)
            btn.setFixedSize(32, 26)
            btn.setToolTip(f"{gc.name} ({gc.code})")
            self._genre_states[gc.code] = STATE_OFF
            btn.setStyleSheet(STATE_STYLES[STATE_OFF])
            btn.clicked.connect(lambda checked=False, c=gc.code: self._on_genre_clicked(c))
            genre_layout.addWidget(btn)
            self._genre_buttons[gc.code] = btn
        genre_layout.addStretch()
        left_layout.addWidget(genre_box)

        # Track list
        self._track_list = QListWidget()
        self._track_list.itemClicked.connect(self._on_track_selected)
        left_layout.addWidget(self._track_list, stretch=1)

        # Playback controls
        playback_box = QGroupBox("Playback")
        pb_layout = QVBoxLayout(playback_box)
        btn_row = QHBoxLayout()
        self._btn_play = QPushButton("Play")
        self._btn_play.clicked.connect(self._toggle_play_pause)
        self._btn_stop = QPushButton("Stop")
        self._btn_stop.clicked.connect(self._stop_preview)
        self._btn_mic = QPushButton("Mic")
        self._btn_mic.setToolTip("Toggle live microphone input")
        self._btn_mic.clicked.connect(self._toggle_mic)
        if not HAS_SOUNDDEVICE:
            self._btn_mic.setEnabled(False)
            self._btn_mic.setToolTip("sounddevice not installed (uv sync --extra video)")
        btn_row.addWidget(self._btn_play)
        btn_row.addWidget(self._btn_stop)
        btn_row.addWidget(self._btn_mic)
        pb_layout.addLayout(btn_row)

        self._position_slider = QSlider(Qt.Orientation.Horizontal)
        self._position_slider.setRange(0, 1000)
        self._position_slider.sliderPressed.connect(self._on_slider_pressed)
        self._position_slider.sliderReleased.connect(self._on_slider_released)
        pb_layout.addWidget(self._position_slider)

        self._time_label = QLabel("0:00 / 0:00")
        pb_layout.addWidget(self._time_label)
        left_layout.addWidget(playback_box)

        # Effect checkboxes — auto-discover and split into three categories
        all_effects = _discover_effects()
        post_fx = VJingLayer.POST_PROCESSING_EFFECTS
        final_fx = VJingLayer.FINAL_PASS_EFFECTS
        special_fx = post_fx | final_fx
        generator_effects = [e for e in all_effects if e not in special_fx]
        post_effects = [e for e in all_effects if e in post_fx]
        final_effects = [e for e in all_effects if e in final_fx]

        effects_box = QGroupBox("Generator Effects")
        effects_outer = QVBoxLayout(effects_box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        effects_widget = QWidget()
        effects_grid = QGridLayout(effects_widget)
        effects_grid.setSpacing(4)

        self._effect_checkboxes: dict[str, QCheckBox] = {}
        cols = 3
        for i, effect_name in enumerate(generator_effects):
            cb = QCheckBox(effect_name)
            cb.setChecked(True)
            cb.toggled.connect(self._on_effect_toggled)
            effects_grid.addWidget(cb, i // cols, i % cols)
            self._effect_checkboxes[effect_name] = cb

        scroll.setWidget(effects_widget)
        effects_outer.addWidget(scroll)

        # All / None buttons for generators
        btn_row2 = QHBoxLayout()
        btn_all = QPushButton("All")
        btn_all.clicked.connect(self._check_all_effects)
        btn_none = QPushButton("None")
        btn_none.clicked.connect(self._uncheck_all_effects)
        btn_row2.addWidget(btn_all)
        btn_row2.addWidget(btn_none)
        effects_outer.addLayout(btn_row2)

        left_layout.addWidget(effects_box)

        # Post-processing effects (mutually exclusive — radio buttons)
        post_box = QGroupBox("Post-Processing")
        post_layout = QHBoxLayout(post_box)
        post_layout.setContentsMargins(4, 4, 4, 4)
        post_layout.setSpacing(8)

        self._post_fx_group = QButtonGroup(self)
        self._post_fx_group.setExclusive(True)
        self._post_fx_radios: dict[str, QRadioButton] = {}

        none_radio = QRadioButton("none")
        none_radio.setChecked(True)
        self._post_fx_group.addButton(none_radio)
        post_layout.addWidget(none_radio)

        for effect_name in post_effects + final_effects:
            rb = QRadioButton(effect_name)
            rb.setChecked(False)
            self._post_fx_group.addButton(rb)
            post_layout.addWidget(rb)
            self._post_fx_radios[effect_name] = rb

        self._post_fx_group.buttonToggled.connect(self._on_effect_toggled)
        post_layout.addStretch()

        left_layout.addWidget(post_box)

        # Palette combo
        palette_row = QHBoxLayout()
        palette_row.addWidget(QLabel("Palette:"))
        self._palette_combo = QComboBox()
        self._palette_combo.addItems(sorted(VJingLayer.COLOR_PALETTES.keys()))
        self._palette_combo.setCurrentText("neon")
        self._palette_combo.currentTextChanged.connect(self._on_palette_changed)
        palette_row.addWidget(self._palette_combo)
        left_layout.addLayout(palette_row)

        # Simultaneous effects
        simul_row = QHBoxLayout()
        simul_row.addWidget(QLabel("Simultaneous:"))
        self._simul_combo = QComboBox()
        for n in range(1, 11):
            self._simul_combo.addItem(str(n))
        self._simul_combo.setCurrentText("3")
        self._simul_combo.currentTextChanged.connect(self._on_effect_toggled)
        simul_row.addWidget(self._simul_combo)
        left_layout.addLayout(simul_row)

        # Audio sensitivity slider (0.5x — 3.0x, default 1.0x)
        sens_row = QHBoxLayout()
        sens_row.addWidget(QLabel("Sensitivity:"))
        self._sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self._sensitivity_slider.setRange(50, 300)  # 0.50 to 3.00
        self._sensitivity_slider.setValue(100)  # 1.0x
        self._sensitivity_slider.setTickInterval(50)
        self._sensitivity_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._sensitivity_slider.valueChanged.connect(self._on_sensitivity_changed)
        sens_row.addWidget(self._sensitivity_slider)
        self._sensitivity_label = QLabel("1.0x")
        self._sensitivity_label.setFixedWidth(35)
        sens_row.addWidget(self._sensitivity_label)
        left_layout.addLayout(sens_row)

        # Right panel — previews
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # Main preview (512x512)
        preview_header = QHBoxLayout()
        self._cb_preview = QCheckBox("Preview (512×512)")
        self._cb_preview.setChecked(True)
        self._cb_preview.toggled.connect(self._on_preview_toggled)
        preview_header.addWidget(self._cb_preview)
        preview_header.addStretch()
        right_layout.addLayout(preview_header)

        self._preview_label = QLabel()
        self._preview_label.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self._preview_label.setStyleSheet("background: black;")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self._preview_label)

        # LED panel preview (32x32 rendered, displayed at 256x256 with big pixels)
        led_group = QGroupBox()
        led_header = QHBoxLayout()
        self._cb_led = QCheckBox("LED Panel (32×32)")
        self._cb_led.setChecked(True)
        self._cb_led.toggled.connect(self._on_led_toggled)
        led_header.addWidget(self._cb_led)
        led_header.addStretch()
        led_group.setLayout(led_header)

        led_layout = QHBoxLayout()
        led_layout.setContentsMargins(4, 4, 4, 4)
        self._led_label = QLabel()
        self._led_label.setFixedSize(LED_PANEL_DISPLAY, LED_PANEL_DISPLAY)
        self._led_label.setStyleSheet("background: black;")
        self._led_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        led_layout.addWidget(self._led_label)
        led_layout.addStretch()

        led_container = QWidget()
        led_container_layout = QVBoxLayout(led_container)
        led_container_layout.setContentsMargins(0, 0, 0, 0)
        led_container_layout.setSpacing(2)
        led_container_layout.addWidget(led_group)
        led_container_layout.addLayout(led_layout)
        right_layout.addWidget(led_container)

        # ESP32 UDP sender
        esp32_row = QHBoxLayout()
        self._cb_esp32 = QCheckBox("→ ESP32")
        self._cb_esp32.setChecked(False)
        self._cb_esp32.toggled.connect(self._on_esp32_toggled)
        esp32_row.addWidget(self._cb_esp32)
        self._esp32_ip_edit = QLineEdit()
        self._esp32_ip_edit.setText("ledpanel.local")
        self._esp32_ip_edit.textChanged.connect(self._on_esp32_ip_changed)
        esp32_row.addWidget(self._esp32_ip_edit)
        esp32_row.addStretch()
        right_layout.addLayout(esp32_row)

        right_layout.addStretch()

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([450, PREVIEW_SIZE + 20])

        # Status bar
        self.statusBar().showMessage("Ready")

    # ─── Data Loading ──────────────────────────────────────────────────

    def _load_tracks(self, query: str = "") -> None:
        """Load tracks from DB into the list widget."""
        try:
            if query:
                rows = self._db.search_tracks(query, limit=500)
            else:
                rows = self._db.get_all_tracks(limit=2000)
        except Exception as e:
            log.error(f"Failed to load tracks: {e}")
            rows = []

        self._all_tracks = [dict(r) for r in rows]
        self._apply_genre_filter()

    def _apply_genre_filter(self) -> None:
        """Filter tracks based on genre button states, then repopulate list."""
        on_codes = {c for c, s in self._genre_states.items() if s == STATE_ON}
        off_codes = {c for c, s in self._genre_states.items() if s == STATE_EXCLUDE}

        if not on_codes and not off_codes:
            self._displayed_tracks = list(self._all_tracks)
        else:
            filtered = []
            for t in self._all_tracks:
                genre = (t.get("genre") or "").upper()
                # All ON codes must be present
                if on_codes and not all(c in genre for c in on_codes):
                    continue
                # No OFF codes must be present
                if off_codes and any(c in genre for c in off_codes):
                    continue
                filtered.append(t)
            self._displayed_tracks = filtered

        self._populate_track_list()

    def _populate_track_list(self) -> None:
        """Repopulate the QListWidget from displayed tracks."""
        self._track_list.clear()
        for t in self._displayed_tracks:
            artist = t.get("artist") or "Unknown"
            title = t.get("title") or Path(t.get("filepath", "")).stem
            item = QListWidgetItem(f"{artist} — {title}")
            item.setData(Qt.ItemDataRole.UserRole, t.get("filepath", ""))
            item.setToolTip(t.get("filepath", ""))
            self._track_list.addItem(item)

        self.statusBar().showMessage(f"{len(self._displayed_tracks)} tracks")

    # ─── Search & Genre Filter ─────────────────────────────────────────

    def _on_search(self) -> None:
        text = self._search_bar.text().strip()
        self._load_tracks(text)

    def _on_genre_clicked(self, code: str) -> None:
        """Cycle genre button state: OFF -> ON -> EXCLUDE -> OFF."""
        current = self._genre_states[code]
        next_state = (current + 1) % 3
        self._genre_states[code] = next_state
        self._genre_buttons[code].setStyleSheet(STATE_STYLES[next_state])
        self._apply_genre_filter()

    # ─── Track Selection & Audio Loading ───────────────────────────────

    def _on_track_selected(self, item: QListWidgetItem) -> None:
        filepath = item.data(Qt.ItemDataRole.UserRole)
        if not filepath or not Path(filepath).exists():
            self.statusBar().showMessage(f"File not found: {filepath}")
            return

        if self._mic_mode:
            self._stop_mic_mode()
        self._stop_preview()
        self._current_filepath = filepath
        self.statusBar().showMessage(f"Loading: {Path(filepath).name}...")
        QApplication.processEvents()

        # Load audio with librosa for VJing analysis
        try:
            import librosa

            self._audio, self._sr = librosa.load(filepath, sr=22050, mono=True)
            self._duration = len(self._audio) / self._sr
        except Exception as e:
            self.statusBar().showMessage(f"Failed to load audio: {e}")
            return

        self._build_layers()
        self._start_preview(filepath)

    # ─── VJing Layer Management ────────────────────────────────────────

    def _get_checked_effects(self) -> list[str]:
        effects = [name for name, cb in self._effect_checkboxes.items() if cb.isChecked()]
        selected = self._post_fx_group.checkedButton()
        if selected and selected.text() != "none":
            effects.append(selected.text())
        return effects

    def _build_layers(self) -> None:
        """Full rebuild of both VJingLayers (expensive — audio analysis + precompute)."""
        if self._mic_mode:
            self._build_live_layers()
            return
        if self._audio is None:
            return

        checked = self._get_checked_effects()
        if not checked:
            self._vjing_layer = None
            self._led_layer = None
            self.statusBar().showMessage("No effects selected")
            return

        try:
            simul = int(self._simul_combo.currentText())
        except ValueError:
            simul = 3

        self.statusBar().showMessage(f"Building VJing layers ({len(checked)} effects)…")
        QApplication.processEvents()

        sens = self._get_sensitivity()
        common = dict(
            fps=FPS,
            audio=self._audio,
            sr=self._sr,
            duration=self._duration,
            genre="",
            preset="_playground",
            presets={"_playground": checked},
            intensity=1.0,
            color_palette=self._current_palette,
            simultaneous_effects=simul,
            transitions_enabled=True,
            use_gpu=True,
            audio_sensitivity=sens,
        )

        try:
            self._vjing_layer = (
                VJingLayer(width=PREVIEW_SIZE, height=PREVIEW_SIZE, **common)
                if self._cb_preview.isChecked()
                else None
            )
            self._led_layer = (
                VJingLayer(width=LED_PANEL_SIZE, height=LED_PANEL_SIZE, **common)
                if self._cb_led.isChecked()
                else None
            )
            self.statusBar().showMessage(
                f"Ready — {len(checked)} effects, palette={self._current_palette}"
            )
        except Exception as e:
            log.error(f"Failed to create VJingLayer: {e}")
            self._vjing_layer = None
            self._led_layer = None
            self.statusBar().showMessage(f"VJing error: {e}")

    def _hot_swap_effects(
        self, layer: VJingLayer, effects: list[str], time_pos: float
    ) -> None:
        """Update active effects on an existing layer without re-doing audio analysis.

        Preserves the order of already-active effects (new ones appended at the end)
        and adjusts layer._effect_phase_offset so the currently visible effect keeps
        playing without interruption after the list size changes.
        """
        old_effects = layer.active_effects
        old_set = set(old_effects)
        new_set = set(effects)

        # Keep existing order; append newly added effects at the end
        kept = [e for e in old_effects if e in new_set]
        added = [e for e in effects if e not in old_set]
        ordered = kept + added

        # Adjust phase offset to keep the current primary effect visible
        old_num, new_num = len(old_effects), len(ordered)
        if old_num > 0 and new_num > 0:
            cycle = layer.effect_cycle_duration
            old_total = cycle * old_num
            t_old = (time_pos + layer._effect_phase_offset) % old_total
            old_primary = int(t_old / cycle) % old_num
            primary_effect = old_effects[old_primary]

            if primary_effect in ordered:
                new_primary = ordered.index(primary_effect)
                pos_in_window = t_old % cycle
                new_total = cycle * new_num
                target_t = new_primary * cycle + pos_in_window
                layer._effect_phase_offset = (
                    target_t - time_pos % new_total + new_total
                ) % new_total

        layer.active_effects = ordered
        layer.presets["_playground"] = ordered

        # Initialize state for newly added effects that have an _init_<name> method
        for name in added:
            if hasattr(layer, f"_init_{name}"):
                getattr(layer, f"_init_{name}")()

    def _on_effect_toggled(self, *_args: object) -> None:
        checked = self._get_checked_effects()
        if not checked:
            self._vjing_layer = None
            self._led_layer = None
            self.statusBar().showMessage("No effects selected")
            return

        try:
            simul = int(self._simul_combo.currentText())
        except ValueError:
            simul = 3

        time_pos = self._frame_idx / FPS

        # Hot-swap on any existing layer (fast, no audio re-analysis)
        has_layer = False
        for layer in (self._vjing_layer, self._led_layer):
            if layer is not None:
                self._hot_swap_effects(layer, checked, time_pos)
                layer.simultaneous_effects = max(1, min(10, simul))
                has_layer = True

        if has_layer:
            self.statusBar().showMessage(
                f"{len(checked)} effects, palette={self._current_palette}"
            )
        else:
            # No layers at all (e.g. after "None" then re-check) — async rebuild
            self._build_layers()

    def _on_palette_changed(self, palette_name: str) -> None:
        self._current_palette = palette_name
        for layer in (self._vjing_layer, self._led_layer):
            if layer is not None:
                layer.color_palette_name = palette_name
                layer.color_palette = VJingLayer.COLOR_PALETTES.get(
                    palette_name, VJingLayer.COLOR_PALETTES["neon"]
                )

    def _get_sensitivity(self) -> dict[str, float]:
        """Return audio_sensitivity dict from the slider value."""
        val = self._sensitivity_slider.value() / 100.0
        return {"bass": val, "mid": val, "treble": val}

    def _on_sensitivity_changed(self, value: int) -> None:
        val = value / 100.0
        self._sensitivity_label.setText(f"{val:.1f}x")
        sens = {"bass": val, "mid": val, "treble": val}
        for layer in (self._vjing_layer, self._led_layer):
            if layer is not None:
                layer.audio_sensitivity = sens

    def _on_preview_toggled(self, checked: bool) -> None:
        self._preview_label.setVisible(checked)
        # Layer kept alive on uncheck so hot-swap stays valid.
        # Only rebuild if re-enabling and no layer exists (e.g. first load).
        if checked and self._vjing_layer is None and (self._mic_mode or self._audio is not None):
            self._build_layers()

    def _on_led_toggled(self, checked: bool) -> None:
        self._led_label.setVisible(checked)
        if checked and self._led_layer is None and (self._mic_mode or self._audio is not None):
            self._build_layers()

    def _on_esp32_toggled(self, checked: bool) -> None:
        if checked:
            ip = self._esp32_ip_edit.text().strip()
            if not ip:
                self.statusBar().showMessage("ESP32: entrez une IP")
                self._cb_esp32.setChecked(False)
                return
            self._esp32_ip = ip
            self._esp32_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._esp32_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
            self._esp32_frame_number = 0
            self.statusBar().showMessage(f"ESP32: envoi activé → {ip}:5005")
        else:
            if self._esp32_socket:
                self._esp32_socket.close()
                self._esp32_socket = None
            self._esp32_ip = ""
            self.statusBar().showMessage("ESP32: envoi désactivé")

    def _on_esp32_ip_changed(self, text: str) -> None:
        self._esp32_ip = text.strip()

    _ESP32_CHUNK_SIZE = 1024

    def _send_frame_to_esp32(self, led_rgb_image: "Image.Image") -> None:  # noqa: F821
        if self._esp32_socket is None or not self._esp32_ip:
            return
        try:
            raw = led_rgb_image.tobytes("raw", "RGB")
            total_chunks = len(raw) // self._ESP32_CHUNK_SIZE
            for i in range(total_chunks):
                chunk = raw[i * self._ESP32_CHUNK_SIZE : (i + 1) * self._ESP32_CHUNK_SIZE]
                header = struct.pack(">IHH", self._esp32_frame_number, i, total_chunks)
                self._esp32_socket.sendto(header + chunk, (self._esp32_ip, 5005))
            self._esp32_frame_number += 1
        except OSError as e:
            log.warning("ESP32 send error: %s", e)

    def _check_all_effects(self) -> None:
        for cb in self._effect_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)
        self._on_effect_toggled()

    def _uncheck_all_effects(self) -> None:
        for cb in self._effect_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._on_effect_toggled()

    # ─── Microphone Live Mode ─────────────────────────────────────────

    def _toggle_mic(self) -> None:
        if self._mic_mode:
            self._stop_mic_mode()
        else:
            self._start_mic_mode()

    def _start_mic_mode(self) -> None:
        self._stop_preview()
        self._mic_mode = True
        self._mic_source = MicrophoneSource(sr=MIC_SR, block_size=MIC_BLOCK_SIZE)
        try:
            self._mic_source.start()
        except Exception as e:
            log.error("Failed to start microphone: %s", e)
            self.statusBar().showMessage(f"Mic error: {e}")
            self._mic_mode = False
            self._mic_source = None
            return

        self._build_live_layers()
        self._frame_idx = 0
        self._timer.start()
        self._btn_mic.setText("Stop Mic")
        self._btn_mic.setStyleSheet(
            "QPushButton { background: #a22; color: white; font-weight: bold; }"
        )
        self._btn_play.setEnabled(False)
        self._btn_stop.setEnabled(False)
        self.statusBar().showMessage("Mic live — listening...")

    def _stop_mic_mode(self) -> None:
        self._timer.stop()
        if self._mic_source:
            self._mic_source.stop()
            self._mic_source = None
        self._mic_mode = False
        self._vjing_layer = None
        self._led_layer = None
        self._frame_idx = 0

        self._btn_mic.setText("Mic")
        self._btn_mic.setStyleSheet("")
        self._btn_play.setEnabled(True)
        self._btn_stop.setEnabled(True)

        # Black frames
        black = QPixmap(PREVIEW_SIZE, PREVIEW_SIZE)
        black.fill(Qt.GlobalColor.black)
        self._preview_label.setPixmap(black)
        black_led = QPixmap(LED_PANEL_DISPLAY, LED_PANEL_DISPLAY)
        black_led.fill(Qt.GlobalColor.black)
        self._led_label.setPixmap(black_led)
        self.statusBar().showMessage("Mic stopped")

    def _build_live_layers(self) -> None:
        """Build LiveVJingLayer instances for mic mode (no audio analysis)."""
        checked = self._get_checked_effects()
        if not checked:
            self._vjing_layer = None
            self._led_layer = None
            self.statusBar().showMessage("No effects selected")
            return

        try:
            simul = int(self._simul_combo.currentText())
        except ValueError:
            simul = 3

        sens = self._get_sensitivity()
        common = dict(
            fps=FPS,
            audio=np.zeros(1, dtype=np.float32),
            sr=MIC_SR,
            duration=float(MIC_DURATION),
            genre="",
            preset="_playground",
            presets={"_playground": checked},
            intensity=1.0,
            color_palette=self._current_palette,
            simultaneous_effects=simul,
            transitions_enabled=True,
            use_gpu=True,
            audio_sensitivity=sens,
        )

        try:
            self._vjing_layer = (
                LiveVJingLayer(width=PREVIEW_SIZE, height=PREVIEW_SIZE, **common)
                if self._cb_preview.isChecked()
                else None
            )
            self._led_layer = (
                LiveVJingLayer(width=LED_PANEL_SIZE, height=LED_PANEL_SIZE, **common)
                if self._cb_led.isChecked()
                else None
            )
            self.statusBar().showMessage(
                f"Mic live — {len(checked)} effects, palette={self._current_palette}"
            )
        except Exception as e:
            log.error(f"Failed to create LiveVJingLayer: {e}")
            self._vjing_layer = None
            self._led_layer = None
            self.statusBar().showMessage(f"VJing error: {e}")

    # ─── Playback ──────────────────────────────────────────────────────

    def _start_preview(self, filepath: str) -> None:
        """Start VLC playback + preview timer."""
        media = self._vlc_instance.media_new(str(filepath))
        self._vlc_player.set_media(media)
        self._vlc_player.play()

        self._frame_idx = 0
        self._timer.start()
        self._position_timer.start()
        self._btn_play.setText("Pause")

    def _stop_preview(self) -> None:
        """Stop everything."""
        self._timer.stop()
        self._position_timer.stop()
        self._vlc_player.stop()
        self._frame_idx = 0
        self._btn_play.setText("Play")

        # Black frames
        black = QPixmap(PREVIEW_SIZE, PREVIEW_SIZE)
        black.fill(Qt.GlobalColor.black)
        self._preview_label.setPixmap(black)
        black_led = QPixmap(LED_PANEL_DISPLAY, LED_PANEL_DISPLAY)
        black_led.fill(Qt.GlobalColor.black)
        self._led_label.setPixmap(black_led)

    def _toggle_play_pause(self) -> None:
        if self._vlc_player.is_playing():
            self._vlc_player.pause()
            self._timer.stop()
            self._btn_play.setText("Play")
        elif self._vlc_player.get_media() is not None:
            self._vlc_player.play()
            self._timer.start()
            self._btn_play.setText("Pause")

    def _on_slider_pressed(self) -> None:
        self._slider_dragging = True

    def _on_slider_released(self) -> None:
        self._slider_dragging = False
        pos = self._position_slider.value() / 1000.0
        self._vlc_player.set_position(pos)
        if self._vjing_layer:
            self._frame_idx = int(pos * self._vjing_layer.total_frames)

    def _sync_position_from_vlc(self) -> None:
        """Sync slider and frame_idx from VLC position."""
        if self._slider_dragging:
            return
        pos = self._vlc_player.get_position()
        if pos < 0:
            return
        self._position_slider.setValue(int(pos * 1000))

        # Update time label
        current_s = pos * self._duration if self._duration > 0 else 0
        total_s = self._duration
        self._time_label.setText(
            f"{int(current_s) // 60}:{int(current_s) % 60:02d} / "
            f"{int(total_s) // 60}:{int(total_s) % 60:02d}"
        )

        # Sync frame index
        if self._vjing_layer:
            self._frame_idx = int(pos * self._vjing_layer.total_frames)

    # ─── Rendering ─────────────────────────────────────────────────────

    def _update_frame(self) -> None:
        """Render one frame and display it on both previews."""
        active_layer = self._vjing_layer or self._led_layer
        if active_layer is None:
            return

        total = active_layer.total_frames
        if self._frame_idx >= total:
            self._frame_idx = total - 1

        # In mic mode, feed real-time audio features into the live layers
        if self._mic_mode and self._mic_source and self._mic_source.is_active:
            ctx = self._mic_source.get_audio_features(self._frame_idx)
            if isinstance(self._vjing_layer, LiveVJingLayer):
                self._vjing_layer.live_ctx = ctx
            if isinstance(self._led_layer, LiveVJingLayer):
                self._led_layer.live_ctx = ctx
            # Update time label for mic mode
            elapsed = self._frame_idx / FPS
            self._time_label.setText(
                f"{int(elapsed) // 60}:{int(elapsed) % 60:02d} (live)"
            )

        time_pos = self._frame_idx / FPS

        if self._vjing_layer is not None and self._cb_preview.isChecked():
            try:
                pil_img = self._vjing_layer.render(self._frame_idx, time_pos)
                rgb_img = pil_img.convert("RGB")
                data = rgb_img.tobytes("raw", "RGB")
                qimg = QImage(
                    data,
                    PREVIEW_SIZE,
                    PREVIEW_SIZE,
                    3 * PREVIEW_SIZE,
                    QImage.Format.Format_RGB888,
                )
                self._preview_label.setPixmap(QPixmap.fromImage(qimg))
            except Exception as e:
                log.error(f"Render error frame {self._frame_idx}: {e}")

        if self._led_layer is not None and self._cb_led.isChecked():
            try:
                from PIL import Image as PILImage

                led_img = self._led_layer.render(self._frame_idx, time_pos)
                led_rgb = led_img.convert("RGB")
                if self._cb_esp32.isChecked():
                    self._send_frame_to_esp32(led_rgb)
                led_scaled = led_rgb.resize(
                    (LED_PANEL_DISPLAY, LED_PANEL_DISPLAY), PILImage.Resampling.NEAREST
                )
                led_data = led_scaled.tobytes("raw", "RGB")
                led_qimg = QImage(
                    led_data,
                    LED_PANEL_DISPLAY,
                    LED_PANEL_DISPLAY,
                    3 * LED_PANEL_DISPLAY,
                    QImage.Format.Format_RGB888,
                )
                self._led_label.setPixmap(QPixmap.fromImage(led_qimg))
            except Exception as e:
                log.error(f"LED render error frame {self._frame_idx}: {e}")

        self._highlight_active_effects(time_pos)
        self._frame_idx += 1

    def _highlight_active_effects(self, time_pos: float) -> None:
        """Bold + green the effect names currently visible on screen."""
        layer = self._vjing_layer or self._led_layer
        if layer is None:
            return

        active = set(layer.active_effects)
        num = len(layer.active_effects)
        visible: set[str] = set()
        for i, name in enumerate(layer.active_effects):
            if layer._calculate_effect_alpha(i, time_pos, num) > 0.0:
                visible.add(name)

        on = "font-weight: bold; color: #00FF00;"
        off = ""
        for name, cb in self._effect_checkboxes.items():
            cb.setStyleSheet(on if name in visible else off)
        for name, rb in self._post_fx_radios.items():
            rb.setStyleSheet(on if name in visible else off)

    # ─── Cleanup ───────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        self._position_timer.stop()
        if self._mic_source:
            self._mic_source.stop()
            self._mic_source = None
        if self._esp32_socket:
            self._esp32_socket.close()
            self._esp32_socket = None
        self._vlc_player.stop()
        self._vlc_player.release()
        self._vlc_instance.release()
        if self._db:
            self._db.close()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark palette
    from PySide6.QtGui import QColor, QPalette

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Button, QColor(50, 50, 50))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    window = VJingPlayground()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
