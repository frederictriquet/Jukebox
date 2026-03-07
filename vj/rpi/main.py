#!/usr/bin/env python3
"""VJing Panel — app Raspberry Pi, micro en continu → LED 64×64 via ESP32 UDP.

Usage:
    python vj/rpi/main.py
    python vj/rpi/main.py --esp32 192.168.1.42
    python vj/rpi/main.py --esp32 ledpanel.local
"""

from __future__ import annotations

import argparse
import logging
import random
import socket
import struct
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "plugins"))

import numpy as np

try:
    import sounddevice as sd

    HAS_SOUNDDEVICE = True
except ImportError:
    sd = None  # type: ignore[assignment]
    HAS_SOUNDDEVICE = False

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPalette, QPixmap
from PySide6.QtWidgets import (
    QMessageBox,
    QApplication,
    QButtonGroup,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from video_exporter.layers.vjing_layer import VJingLayer

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

LED_SIZE = 64
LED_DISPLAY = 256
FPS = 30
MIC_SR = 22050
MIC_BLOCK_SIZE = 2048
MIC_DURATION = 3600  # buffer 1h en mode live

ESP32_PORT = 5005
ESP32_CHUNK_SIZE = 1024


# ─── Découverte des effets ────────────────────────────────────────────────────


def _discover_effects() -> list[str]:
    internal = {"with_transitions", "gpu_effect"}
    known = list(VJingLayer.AVAILABLE_EFFECTS)
    known_set = set(known)
    for name in sorted(dir(VJingLayer)):
        if name.startswith("_render_") and callable(getattr(VJingLayer, name)):
            effect_name = name[len("_render_"):]
            if effect_name not in known_set and effect_name not in internal:
                known.append(effect_name)
                known_set.add(effect_name)
    return known


# ─── Capture microphone ───────────────────────────────────────────────────────


class MicrophoneSource:
    """Capture microphone temps réel avec extraction de features audio."""

    def __init__(self, sr: int = MIC_SR, block_size: int = MIC_BLOCK_SIZE) -> None:
        self.sr = sr
        self.block_size = block_size
        self._buffer = np.zeros(block_size * 4, dtype=np.float32)
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None

        self._last_beat_frame = -100
        self._bass_history: list[float] = []
        self._running_max: float = 1e-6

        n_fft = block_size * 2
        freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
        self._n_fft = n_fft
        self._bass_mask = (freqs >= 20) & (freqs < 250)
        self._mid_mask = (freqs >= 250) & (freqs < 4000)
        self._treble_mask = freqs >= 4000

        self._n_bands = 32
        n_bins = len(freqs)
        self._band_edges = np.linspace(0, n_bins, self._n_bands + 1, dtype=int)

    def start(self) -> None:
        if not HAS_SOUNDDEVICE:
            raise RuntimeError("sounddevice not installed (uv sync --extra video)")
        self._stream = sd.InputStream(
            samplerate=self.sr,
            channels=1,
            blocksize=self.block_size,
            callback=self._callback,
            dtype="float32",
        )
        self._stream.start()
        log.info("[Mic] Démarré à %d Hz, block=%d", self.sr, self.block_size)

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            log.info("[Mic] Arrêté")

    @property
    def is_active(self) -> bool:
        return self._stream is not None and self._stream.active

    def _callback(
        self, indata: np.ndarray, frames: int, _time_info: object, status: object
    ) -> None:
        if status:
            log.debug("[Mic] status: %s", status)
        with self._lock:
            n = min(frames, len(indata))
            self._buffer = np.roll(self._buffer, -n)
            self._buffer[-n:] = indata[:n, 0]

    def get_audio_features(self, frame_idx: int) -> dict:
        with self._lock:
            chunk = self._buffer.copy()

        fft_full = np.abs(np.fft.rfft(chunk, n=self._n_fft))

        bass_e = float(np.sqrt(np.mean(fft_full[self._bass_mask] ** 2)))
        mid_e = float(np.sqrt(np.mean(fft_full[self._mid_mask] ** 2)))
        treble_e = float(np.sqrt(np.mean(fft_full[self._treble_mask] ** 2)))

        peak = max(bass_e, mid_e, treble_e)
        self._running_max = max(peak * 1.2, self._running_max * 0.998)
        norm = max(self._running_max, 1e-6)
        bass_n = min(1.0, bass_e / norm)
        mid_n = min(1.0, mid_e / norm)
        treble_n = min(1.0, treble_e / norm)
        energy = (bass_n + mid_n + treble_n) / 3.0

        bands = np.zeros(self._n_bands)
        for i in range(self._n_bands):
            s, e = self._band_edges[i], self._band_edges[i + 1]
            if s < e:
                bands[i] = np.mean(fft_full[s:e])
        max_band = float(np.max(bands))
        if max_band > 0:
            bands /= max_band

        self._bass_history.append(bass_n)
        if len(self._bass_history) > 30:
            self._bass_history.pop(0)
        avg_bass = float(np.mean(self._bass_history))
        min_interval = 7
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


# ─── Layer live (micro) ───────────────────────────────────────────────────────


class LiveVJingLayer(VJingLayer):
    """VJingLayer sans analyse audio : reçoit les features frame par frame."""

    live_ctx: dict | None = None

    def _precompute(self) -> None:
        n = self.total_frames
        self.energy = np.zeros(n)
        self.bass_energy = np.zeros(n)
        self.mid_energy = np.zeros(n)
        self.treble_energy = np.zeros(n)
        self.fft_data: list[np.ndarray] = [np.zeros(32) for _ in range(n)]
        self.beats: list[int] = []
        self._has_frequency_bands = True

        for name in self.active_effects:
            init_fn = getattr(self, f"_init_{name}", None)
            if init_fn:
                init_fn()

        if self._pending_gpu_init:
            self._init_gpu_renderer()

    def render(self, frame_idx: int, time_pos: float) -> "Image.Image":  # type: ignore[name-defined] # noqa: F821
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


# ─── Fenêtre principale ───────────────────────────────────────────────────────


class RpiVJPanel(QMainWindow):
    """App VJing pour Raspberry Pi — micro continu → LED 64×64 → ESP32."""

    def __init__(self, esp32_host: str = "ledpanel.local") -> None:
        super().__init__()
        self.setWindowTitle("VJ Panel")
        self.setMinimumSize(900, 700)

        self._esp32_host = esp32_host
        self._esp32_socket: socket.socket | None = None
        self._esp32_frame_number: int = 0

        self._led_layer: LiveVJingLayer | None = None
        self._mic_source: MicrophoneSource | None = None
        self._frame_idx: int = 0
        self._current_palette = "neon"

        self._manual_beat = False
        self._mic_mode = True  # False = mode auto sans micro
        self._last_visible: frozenset[str] = frozenset()

        self._timer = QTimer()
        self._timer.setInterval(1000 // FPS)
        self._timer.timeout.connect(self._update_frame)

        self._setup_ui()
        self._open_esp32_socket()
        self._start_mic()

    # ─── UI ──────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # ── Panel gauche ─────────────────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # Generator Effects
        all_effects = _discover_effects()
        post_fx = VJingLayer.POST_PROCESSING_EFFECTS
        final_fx = VJingLayer.FINAL_PASS_EFFECTS
        special_fx = post_fx | final_fx
        generator_effects = sorted(e for e in all_effects if e not in special_fx)
        post_effects = [e for e in all_effects if e in post_fx]
        final_effects = [e for e in all_effects if e in final_fx]

        effects_box = QGroupBox("Generator Effects")
        effects_outer = QVBoxLayout(effects_box)

        effects_grid = QGridLayout()
        effects_grid.setSpacing(4)

        self._effect_checkboxes: dict[str, QPushButton] = {}
        cols = 4
        for i, name in enumerate(generator_effects):
            cb = QPushButton(name)
            cb.setCheckable(True)
            cb.setChecked(True)
            cb.setMinimumHeight(90)
            cb.setStyleSheet(self._fx_btn_style(checked=True, active=False))
            cb.toggled.connect(self._on_effect_toggled)
            effects_grid.addWidget(cb, i // cols, i % cols)
            self._effect_checkboxes[name] = cb

        effects_outer.addLayout(effects_grid)

        btn_row = QHBoxLayout()
        btn_all = QPushButton("All")
        btn_all.clicked.connect(self._check_all_effects)
        btn_none = QPushButton("None")
        btn_none.clicked.connect(self._uncheck_all_effects)
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        effects_outer.addLayout(btn_row)
        left_layout.addWidget(effects_box)

        # Post-Processing
        post_box = QGroupBox("Post-Processing")
        post_grid = QGridLayout(post_box)
        post_grid.setContentsMargins(4, 4, 4, 4)
        post_grid.setSpacing(8)

        self._post_fx_group = QButtonGroup(self)
        self._post_fx_group.setExclusive(True)
        self._post_fx_radios: dict[str, QPushButton] = {}

        all_post = ["none"] + post_effects + final_effects
        post_cols = (len(all_post) + 1) // 2
        for i, name in enumerate(all_post):
            rb = QPushButton(name)
            rb.setCheckable(True)
            rb.setChecked(name == "none")
            rb.setMinimumHeight(44)
            rb.setStyleSheet(self._fx_btn_style(checked=(name == "none"), active=False))
            self._post_fx_group.addButton(rb)
            post_grid.addWidget(rb, i // post_cols, i % post_cols)
            if name != "none":
                self._post_fx_radios[name] = rb

        self._post_fx_group.buttonToggled.connect(self._on_effect_toggled)
        left_layout.addWidget(post_box)

        left_layout.addStretch()

        # ── Panel droit ──────────────────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        led_header = QLabel("LED Panel (64×64)")
        right_layout.addWidget(led_header)

        self._led_label = QLabel()
        self._led_label.setFixedSize(LED_DISPLAY, LED_DISPLAY)
        self._led_label.setStyleSheet("background: black;")
        self._led_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self._led_label)

        self._esp32_status = QLabel(f"ESP32: {self._esp32_host}")
        self._esp32_status.setStyleSheet("color: #888;")
        right_layout.addWidget(self._esp32_status)

        # Palette
        palette_row = QHBoxLayout()
        palette_lbl = QLabel("Palette:")
        palette_lbl.setStyleSheet("font-size: 28px;")
        palette_row.addWidget(palette_lbl)
        self._palette_combo = QComboBox()
        self._palette_combo.addItems(sorted(VJingLayer.COLOR_PALETTES.keys()))
        self._palette_combo.setCurrentText("neon")
        self._palette_combo.setStyleSheet("font-size: 28px; min-height: 48px;")
        self._palette_combo.currentTextChanged.connect(self._on_palette_changed)
        palette_row.addWidget(self._palette_combo)
        right_layout.addLayout(palette_row)

        # Simultaneous
        simul_row = QHBoxLayout()
        simul_lbl = QLabel("Simultaneous:")
        simul_lbl.setStyleSheet("font-size: 28px;")
        simul_row.addWidget(simul_lbl)
        self._simul_combo = QComboBox()
        for n in range(1, 11):
            self._simul_combo.addItem(str(n))
        self._simul_combo.setCurrentText("1")
        self._simul_combo.setStyleSheet("font-size: 28px; min-height: 48px;")
        self._simul_combo.currentTextChanged.connect(self._on_effect_toggled)
        simul_row.addWidget(self._simul_combo)
        right_layout.addLayout(simul_row)

        # Sensitivity
        sens_row = QHBoxLayout()
        sens_lbl = QLabel("Sensitivity:")
        sens_lbl.setStyleSheet("font-size: 28px;")
        sens_row.addWidget(sens_lbl)
        self._sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self._sensitivity_slider.setRange(50, 300)
        self._sensitivity_slider.setValue(100)
        self._sensitivity_slider.setTickInterval(50)
        self._sensitivity_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._sensitivity_slider.setStyleSheet("min-height: 48px;")
        self._sensitivity_slider.valueChanged.connect(self._on_sensitivity_changed)
        sens_row.addWidget(self._sensitivity_slider)
        self._sensitivity_label = QLabel("1.0x")
        self._sensitivity_label.setStyleSheet("font-size: 28px;")
        self._sensitivity_label.setFixedWidth(70)
        sens_row.addWidget(self._sensitivity_label)
        right_layout.addLayout(sens_row)

        # Mode mic / auto
        self._btn_mic_mode = QPushButton("Mic ON")
        self._btn_mic_mode.setFixedHeight(48)
        self._btn_mic_mode.setStyleSheet(
            "QPushButton { background: #1a4a1a; color: #4f4; font-weight: bold; "
            "font-size: 15px; border: 2px solid #2a6a2a; border-radius: 6px; }"
        )
        self._btn_mic_mode.clicked.connect(self._toggle_mic_mode)
        right_layout.addWidget(self._btn_mic_mode)

        # Zone de tap beat (tactile)
        self._beat_btn = QPushButton("TAP BEAT")
        self._beat_btn.setFixedHeight(80)
        self._beat_btn.setStyleSheet("""
            QPushButton {
                background: #2a2a2a;
                color: #888;
                font-size: 20px;
                font-weight: bold;
                border: 2px solid #444;
                border-radius: 8px;
            }
            QPushButton:pressed {
                background: #ff4400;
                color: white;
                border-color: #ff6622;
            }
        """)
        self._beat_btn.pressed.connect(self._on_tap_beat)
        right_layout.addWidget(self._beat_btn)

        right_layout.addStretch()

        quit_row = QHBoxLayout()
        quit_row.addStretch()
        btn_quit = QPushButton("Quit")
        btn_quit.setFixedHeight(48)
        btn_quit.setStyleSheet(
            "QPushButton { background: #3a1a1a; color: #f88; font-size: 24px; "
            "font-weight: bold; border: 2px solid #6a2a2a; border-radius: 6px; padding: 0 20px; }"
            "QPushButton:pressed { background: #a22; color: white; }"
        )
        btn_quit.clicked.connect(self._confirm_quit)
        quit_row.addWidget(btn_quit)
        right_layout.addLayout(quit_row)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([560, LED_DISPLAY + 40])

        self.statusBar().showMessage("Starting microphone…")

    # ─── Styles boutons effets ────────────────────────────────────────────

    @staticmethod
    def _fx_btn_style(checked: bool, active: bool) -> str:
        if active:
            return ("font-size: 44px; font-weight: bold; color: #00FF00; "
                    "background: #1a3a1a; border: 2px solid #00FF00; border-radius: 4px;")
        if checked:
            return ("font-size: 44px; color: #ccc; "
                    "background: #3a3a3a; border: 2px solid #666; border-radius: 4px;")
        return ("font-size: 44px; color: #555; "
                "background: #1e1e1e; border: 2px solid #333; border-radius: 4px;")

    # ─── Mode mic / auto ─────────────────────────────────────────────────

    def _toggle_mic_mode(self) -> None:
        self._mic_mode = not self._mic_mode
        if self._mic_mode:
            self._btn_mic_mode.setText("Mic ON")
            self._btn_mic_mode.setStyleSheet(
                "QPushButton { background: #1a4a1a; color: #4f4; font-weight: bold; "
                "font-size: 15px; border: 2px solid #2a6a2a; border-radius: 6px; }"
            )
            self._start_mic()
        else:
            self._btn_mic_mode.setText("Auto (no mic)")
            self._btn_mic_mode.setStyleSheet(
                "QPushButton { background: #2a2a2a; color: #888; font-weight: bold; "
                "font-size: 15px; border: 2px solid #444; border-radius: 6px; }"
            )
            if self._mic_source:
                self._mic_source.stop()
                self._mic_source = None

    def _make_auto_ctx(self) -> dict:
        """Contexte audio synthétique pour le mode sans micro."""
        return {
            "energy": 0.5,
            "bass": 0.4,
            "mid": 0.5,
            "treble": 0.3,
            "fft": np.full(32, 0.4),
            "is_beat": False,
        }

    # ─── Mic ─────────────────────────────────────────────────────────────

    def _start_mic(self) -> None:
        if not HAS_SOUNDDEVICE:
            self.statusBar().showMessage("ERROR: sounddevice not installed — auto mode")
            self._switch_to_auto_mode()
            return

        self._mic_source = MicrophoneSource(sr=MIC_SR, block_size=MIC_BLOCK_SIZE)
        try:
            self._mic_source.start()
        except Exception as e:
            log.error("Mic : %s", e)
            self.statusBar().showMessage(f"Mic error: {e} — auto mode")
            self._switch_to_auto_mode()
            return

        self._build_live_layer()
        self._frame_idx = 0
        self._timer.start()
        self.statusBar().showMessage(
            f"Mic active — {len(self._effect_checkboxes)} effects, palette={self._current_palette}"
        )

    def _switch_to_auto_mode(self) -> None:
        self._mic_mode = False
        self._btn_mic_mode.setText("Auto (no mic)")
        self._btn_mic_mode.setStyleSheet(
            "QPushButton { background: #2a2a2a; color: #888; font-weight: bold; "
            "font-size: 15px; border: 2px solid #444; border-radius: 6px; }"
        )
        self._build_live_layer()
        self._frame_idx = 0
        self._timer.start()

    # ─── Layer ───────────────────────────────────────────────────────────

    def _get_checked_effects(self) -> list[str]:
        effects = [name for name, cb in self._effect_checkboxes.items() if cb.isChecked()]
        selected = self._post_fx_group.checkedButton()
        if selected and selected.text() != "none":
            effects.append(selected.text())
        return effects

    def _get_sensitivity(self) -> dict[str, float]:
        val = self._sensitivity_slider.value() / 100.0
        return {"bass": val, "mid": val, "treble": val}

    def _build_live_layer(self) -> None:
        checked = self._get_checked_effects()
        random.shuffle(checked)
        if not checked:
            self._led_layer = None
            self.statusBar().showMessage("No effect selected")
            return

        try:
            simul = int(self._simul_combo.currentText())
        except ValueError:
            simul = 1

        try:
            self._led_layer = LiveVJingLayer(
                width=LED_SIZE,
                height=LED_SIZE,
                fps=FPS,
                audio=np.zeros(1, dtype=np.float32),
                sr=MIC_SR,
                duration=float(MIC_DURATION),
                genre="",
                preset="_rpi",
                presets={"_rpi": checked},
                intensity=1.0,
                color_palette=self._current_palette,
                simultaneous_effects=simul,
                transitions_enabled=True,
                use_gpu=False,
                audio_sensitivity=self._get_sensitivity(),
            )
        except Exception as e:
            log.error("LiveVJingLayer : %s", e)
            self._led_layer = None
            self.statusBar().showMessage(f"Layer error: {e}")

    def _hot_swap_effects(self, effects: list[str], time_pos: float) -> None:
        if self._led_layer is None:
            return
        layer = self._led_layer
        old_effects = layer.active_effects
        old_set = set(old_effects)
        new_set = set(effects)

        kept = [e for e in old_effects if e in new_set]
        added = [e for e in effects if e not in old_set]
        ordered = kept + added

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
        layer.presets["_rpi"] = ordered
        for name in added:
            if hasattr(layer, f"_init_{name}"):
                getattr(layer, f"_init_{name}")()

    def _on_effect_toggled(self, *_args: object) -> None:
        self._last_visible = frozenset()  # force style refresh on next frame
        checked = self._get_checked_effects()
        if not checked:
            self._led_layer = None
            self.statusBar().showMessage("No effect selected")
            return

        try:
            simul = int(self._simul_combo.currentText())
        except ValueError:
            simul = 1

        time_pos = self._frame_idx / FPS

        if self._led_layer is not None:
            self._hot_swap_effects(checked, time_pos)
            self._led_layer.simultaneous_effects = max(1, min(10, simul))
        else:
            self._build_live_layer()

        self.statusBar().showMessage(
            f"{len(checked)} effects, palette={self._current_palette}"
        )

    def _on_palette_changed(self, palette_name: str) -> None:
        self._current_palette = palette_name
        if self._led_layer is not None:
            self._led_layer.color_palette_name = palette_name
            self._led_layer.color_palette = VJingLayer.COLOR_PALETTES.get(
                palette_name, VJingLayer.COLOR_PALETTES["neon"]
            )

    def _on_sensitivity_changed(self, value: int) -> None:
        val = value / 100.0
        self._sensitivity_label.setText(f"{val:.1f}x")
        if self._led_layer is not None:
            self._led_layer.audio_sensitivity = {"bass": val, "mid": val, "treble": val}

    def _check_all_effects(self) -> None:
        for cb in self._effect_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.setStyleSheet(self._fx_btn_style(checked=True, active=False))
            cb.blockSignals(False)
        self._on_effect_toggled()

    def _uncheck_all_effects(self) -> None:
        for cb in self._effect_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.setStyleSheet(self._fx_btn_style(checked=False, active=False))
            cb.blockSignals(False)
        self._on_effect_toggled()

    # ─── Beat manuel ─────────────────────────────────────────────────────

    def _on_tap_beat(self) -> None:
        self._manual_beat = True

    # ─── ESP32 ───────────────────────────────────────────────────────────

    def _open_esp32_socket(self) -> None:
        self._esp32_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._esp32_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
        log.info("[ESP32] Socket UDP ouvert → %s:%d", self._esp32_host, ESP32_PORT)
        self._esp32_status.setText(f"ESP32: {self._esp32_host}:{ESP32_PORT}")

    def _send_frame_to_esp32(self, led_rgb_image: object) -> None:
        if self._esp32_socket is None:
            return
        try:
            raw = led_rgb_image.tobytes("raw", "RGB")  # type: ignore[union-attr]
            total_chunks = len(raw) // ESP32_CHUNK_SIZE
            for i in range(total_chunks):
                chunk = raw[i * ESP32_CHUNK_SIZE : (i + 1) * ESP32_CHUNK_SIZE]
                header = struct.pack(">IHH", self._esp32_frame_number, i, total_chunks)
                self._esp32_socket.sendto(header + chunk, (self._esp32_host, ESP32_PORT))
            self._esp32_frame_number += 1
        except OSError as e:
            log.warning("[ESP32] Erreur envoi : %s", e)

    # ─── Rendu ───────────────────────────────────────────────────────────

    def _update_frame(self) -> None:
        if self._led_layer is None:
            return

        total = self._led_layer.total_frames
        if self._frame_idx >= total:
            self._frame_idx = total - 1

        if self._mic_mode and self._mic_source and self._mic_source.is_active:
            ctx = self._mic_source.get_audio_features(self._frame_idx)
        else:
            ctx = self._make_auto_ctx()

        if self._manual_beat:
            ctx["is_beat"] = True
            ctx["energy"] = max(ctx["energy"], 0.85)
            ctx["bass"] = max(ctx["bass"], 0.85)
            self._manual_beat = False

        self._led_layer.live_ctx = ctx

        time_pos = self._frame_idx / FPS

        try:
            from PIL import Image as PILImage

            led_img = self._led_layer.render(self._frame_idx, time_pos)
            led_rgb = led_img.convert("RGB")

            self._send_frame_to_esp32(led_rgb)

            led_scaled = led_rgb.resize(
                (LED_DISPLAY, LED_DISPLAY), PILImage.Resampling.NEAREST
            )
            data = led_scaled.tobytes("raw", "RGB")
            qimg = QImage(
                data,
                LED_DISPLAY,
                LED_DISPLAY,
                3 * LED_DISPLAY,
                QImage.Format.Format_RGB888,
            )
            self._led_label.setPixmap(QPixmap.fromImage(qimg))
        except Exception as e:
            log.error("[Render] frame %d : %s", self._frame_idx, e)

        self._highlight_active_effects(time_pos)
        self._frame_idx += 1

    def _highlight_active_effects(self, time_pos: float) -> None:
        if self._led_layer is None:
            return
        try:
            active_effects = list(self._led_layer.active_effects)
            num = len(active_effects)
            visible: set[str] = set()
            for i, name in enumerate(active_effects):
                if self._led_layer._calculate_effect_alpha(i, time_pos, num) > 0.0:
                    visible.add(name)
        except Exception:
            return

        frozen = frozenset(visible)
        if frozen == self._last_visible:
            return
        self._last_visible = frozen

        for name, cb in self._effect_checkboxes.items():
            cb.setStyleSheet(self._fx_btn_style(checked=cb.isChecked(), active=name in visible))

        for name, rb in self._post_fx_radios.items():
            rb.setStyleSheet(self._fx_btn_style(checked=rb.isChecked(), active=name in visible))

    def _confirm_quit(self) -> None:
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Quit")
        dlg.setText("Quit the application?")
        dlg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dlg.setDefaultButton(QMessageBox.StandardButton.No)
        dlg.setStyleSheet("font-size: 28px;")
        if dlg.exec() == QMessageBox.StandardButton.Yes:
            self.close()

    # ─── Nettoyage ───────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        if self._mic_source:
            self._mic_source.stop()
        if self._esp32_socket:
            self._esp32_socket.close()
        event.accept()


# ─── Entrée ───────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="VJing Panel pour Raspberry Pi")
    parser.add_argument(
        "--esp32",
        default="ledpanel.local",
        metavar="HOST",
        help="IP ou hostname de l'ESP32 (défaut: ledpanel.local)",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

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

    window = RpiVJPanel(esp32_host=args.esp32)
    window.showFullScreen()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
