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
import faulthandler
import random
import socket
import struct
import sys
import threading
from collections import deque
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

try:
    from PIL import Image as PILImage

    HAS_PIL = True
except ImportError:
    PILImage = None  # type: ignore[assignment,misc]
    HAS_PIL = False

from PySide6.QtCore import QObject, Qt, QTimer, Slot
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

# ── Blocage des C extensions ARM64 bugguées ──────────────────────────────────
# noise._perlin / noise._simplex et moderngl.mgl ont des bugs d'initialisation
# (PyInit_*) sur ARM64 qui corrompent le refcount de None même sans être appelés.
# On injecte des faux modules dans sys.modules AVANT que vjing_layer.py ne fasse
# `from noise import pnoise2, snoise2` (niveau module), afin que les vraies
# C extensions ne soient jamais chargées.
import types as _types


class _BlockedModule(_types.ModuleType):
    """Module fantôme : tout accès d'attribut lève ImportError → fallbacks activés."""

    def __getattr__(self, name: str) -> object:
        # Les dunders (__file__, __spec__…) doivent lever AttributeError (standard
        # Python) pour que getattr(m, "__file__", None) fonctionne correctement.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        raise ImportError(f"Module {self.__name__!r} bloqué sur ARM64")


for _blocked in ("noise", "moderngl", "PIL._imagingft"):
    if _blocked not in sys.modules:
        sys.modules[_blocked] = _BlockedModule(_blocked)


from video_exporter.layers.vjing_layer import VJingLayer  # noqa: E402

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)



LED_SIZE = 64
LED_DISPLAY = 256
FPS = 30
MIC_SR = 22050
MIC_BLOCK_SIZE = 2048
MIC_DURATION = 60    # buffer 60s — réduit la mémoire de ~24Mo à ~0.5Mo

ESP32_PORT = 5005
ESP32_CHUNK_SIZE = 1024
ESP32_TOTAL_CHUNKS = LED_SIZE * LED_SIZE * 3 // ESP32_CHUNK_SIZE  # always 12

_AUTO_CTX_FFT = np.full(32, 0.4, dtype=np.float32)


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


def _list_input_devices() -> list[tuple[int, str]]:
    """Retourne [(index, nom)] des périphériques d'entrée audio disponibles."""
    if not HAS_SOUNDDEVICE:
        return []
    try:
        devices = sd.query_devices()
        return [
            (i, d["name"])
            for i, d in enumerate(devices)
            if d["max_input_channels"] > 0
        ]
    except Exception:
        return []


class MicrophoneSource:
    """Capture microphone temps réel avec extraction de features audio.

    Utilise le mode polling (stream.read) plutôt qu'un callback Python.
    Le callback sounddevice s'exécute dans un thread C PortAudio qui acquiert
    le GIL pour appeler Python — sur ARM64 avec numpy cela provoque des
    corruptions de refcount (none_dealloc fatal). Le polling élimine ce thread.
    """

    def __init__(self, sr: int = MIC_SR, block_size: int = MIC_BLOCK_SIZE) -> None:
        self.sr = sr
        self.block_size = block_size

        n_fft = block_size * 2
        self._n_fft = n_fft
        # Buffer glissant : on concatène les derniers blocs lus pour avoir n_fft samples
        self._ring = np.zeros(n_fft, dtype=np.float32)
        self._stream: sd.InputStream | None = None

        self._last_beat_frame = -100
        self._bass_history: deque[float] = deque(maxlen=30)
        self._running_max: float = 1e-6

        self._n_bands = 32
        self._ctx: dict = {
            "energy": 0.0, "bass": 0.0, "mid": 0.0,
            "treble": 0.0, "fft": np.zeros(self._n_bands, dtype=np.float32),
            "is_beat": False,
        }
        self._init_freq_slices(sr)

    def _init_freq_slices(self, sr: int) -> None:
        """(Re)calcule les slices FFT pour le sample rate donné."""
        freqs = np.fft.rfftfreq(self._n_fft, 1.0 / sr)
        n_bins = len(freqs)
        self._bass_sl = slice(int(np.searchsorted(freqs, 20)),  int(np.searchsorted(freqs, 250)))
        self._mid_sl  = slice(int(np.searchsorted(freqs, 250)), int(np.searchsorted(freqs, 4000)))
        self._treble_sl = slice(int(np.searchsorted(freqs, 4000)), None)
        self._band_edges = np.linspace(0, n_bins, self._n_bands + 1, dtype=int)
        self._band_counts = np.maximum(np.diff(self._band_edges).astype(np.float32), 1)

    def start(self, device: int | str | None = None) -> None:
        if not HAS_SOUNDDEVICE:
            raise RuntimeError("sounddevice not installed (uv sync --extra video)")
        actual_sr = self.sr
        if device is not None:
            try:
                dev_info = sd.query_devices(device)
                native_sr = int(dev_info.get("default_samplerate", self.sr))
                if native_sr != self.sr:
                    log.info(
                        "[Mic] SR natif device=%s : %d Hz (au lieu de %d) — adaptation",
                        device, native_sr, self.sr,
                    )
                    actual_sr = native_sr
            except Exception:
                pass
        # Pas de callback= : mode polling, sounddevice bufferise en interne
        self._stream = sd.InputStream(
            device=device,
            samplerate=actual_sr,
            channels=1,
            blocksize=self.block_size,
            dtype="float32",
            latency="low",
        )
        self._stream.start()
        if actual_sr != self.sr:
            self.sr = actual_sr
            self._init_freq_slices(actual_sr)
        log.info("[Mic] Démarré (polling) device=%s %d Hz block=%d", device, self.sr, self.block_size)

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            log.info("[Mic] Arrêté")

    @property
    def is_active(self) -> bool:
        return self._stream is not None and self._stream.active

    def _poll(self) -> None:
        """Lit les samples disponibles et met à jour le buffer glissant (thread Qt)."""
        if self._stream is None:
            return
        available = self._stream.read_available
        if available <= 0:
            return
        data, _ = self._stream.read(available)   # (available, 1) float32
        samples = data[:, 0]
        n = len(samples)
        if n >= self._n_fft:
            # Plus de samples que le buffer : garder les plus récents
            self._ring[:] = samples[-self._n_fft:]
        else:
            # Décaler et ajouter
            self._ring[:-n] = self._ring[n:]
            self._ring[-n:] = samples

    def get_audio_features(self, frame_idx: int) -> dict:
        self._poll()  # lit les nouveaux samples depuis sounddevice (thread Qt, pas de callback)

        fft_full = np.abs(np.fft.rfft(self._ring))

        # RMS par bande via np.dot (évite ** 2 + mean séparés)
        def _rms(sl: slice) -> float:
            v = fft_full[sl]
            return float(np.sqrt(np.dot(v, v) / max(len(v), 1)))

        bass_e = _rms(self._bass_sl)
        mid_e  = _rms(self._mid_sl)
        treble_e = _rms(self._treble_sl)

        peak = max(bass_e, mid_e, treble_e)
        self._running_max = max(peak * 1.2, self._running_max * 0.998)
        norm = max(self._running_max, 1e-6)
        bass_n   = min(1.0, bass_e   / norm)
        mid_n    = min(1.0, mid_e    / norm)
        treble_n = min(1.0, treble_e / norm)
        energy = (bass_n + mid_n + treble_n) / 3.0

        # 32 bandes vectorisées (np.add.reduceat = une seule passe C)
        bands: np.ndarray = self._ctx["fft"]
        np.add.reduceat(fft_full, self._band_edges[:-1], out=bands)
        bands /= self._band_counts
        max_band = float(np.max(bands))
        if max_band > 0:
            bands /= max_band

        self._bass_history.append(bass_n)
        avg_bass = sum(self._bass_history) / len(self._bass_history)
        is_beat = bass_n > max(0.5, avg_bass * 1.5) and (
            frame_idx - self._last_beat_frame
        ) >= 7
        if is_beat:
            self._last_beat_frame = frame_idx

        # Mise à jour du dict pré-alloué (pas de nouvelle allocation)
        self._ctx["energy"]  = energy
        self._ctx["bass"]    = bass_n
        self._ctx["mid"]     = mid_n
        self._ctx["treble"]  = treble_n
        self._ctx["is_beat"] = is_beat
        return self._ctx


# ─── Layer live (micro) ───────────────────────────────────────────────────────


class LiveVJingLayer(VJingLayer):
    """VJingLayer sans analyse audio : reçoit les features frame par frame.

    fft_data est un array 2D numpy (n × 32) au lieu d'une liste de tableaux :
    même API d'accès (fft_data[i]), mais ~10× moins de mémoire et pas d'overhead GC.
    """

    live_ctx: dict | None = None

    def _precompute(self) -> None:
        n = self.total_frames
        self.energy       = np.zeros(n, dtype=np.float32)
        self.bass_energy  = np.zeros(n, dtype=np.float32)
        self.mid_energy   = np.zeros(n, dtype=np.float32)
        self.treble_energy = np.zeros(n, dtype=np.float32)
        # Array 2D continu au lieu d'une liste de 108 000 objets numpy
        self.fft_data: np.ndarray = np.zeros((n, 32), dtype=np.float32)  # type: ignore[assignment]
        self.beats: list[int] = []
        self._beats_set: set[int] = set()
        self._has_frequency_bands = True

        for name in self.active_effects:
            init_fn = getattr(self, f"_init_{name}", None)
            if init_fn:
                init_fn()

        h, w = self.height, self.width

        if self._pending_gpu_init:
            self._init_gpu_renderer()

    def render(self, frame_idx: int, time_pos: float) -> "Image.Image":  # type: ignore[name-defined] # noqa: F821
        if self.live_ctx is not None:
            # Wrapping : frame_idx tourne dans [0, total_frames) indéfiniment
            safe = frame_idx % self.total_frames
            ctx = self.live_ctx
            self.energy[safe]       = ctx["energy"]
            self.bass_energy[safe]  = ctx["bass"]
            self.mid_energy[safe]   = ctx["mid"]
            self.treble_energy[safe] = ctx["treble"]
            self.fft_data[safe]     = ctx["fft"]
            if ctx["is_beat"] and (not self.beats or self.beats[-1] != frame_idx):
                self.beats.append(frame_idx)
                self._beats_set.add(frame_idx)
                if len(self.beats) > 300:
                    evicted = self.beats[:-300]
                    self.beats = self.beats[-300:]
                    self._beats_set -= set(evicted)
        return super().render(frame_idx, time_pos)


# ─── VU Meter ────────────────────────────────────────────────────────────────
# QProgressBar pur C++ (non sous-classé en Python) : shiboken6 ne fait aucun
# lookup de virtual-override Python lors des repaints → élimine le crash
# none_dealloc ARM64 causé par ce lookup sur les sous-classes Python de QWidget.

# VU Meter via QLabel (pas QProgressBar) :
# QProgressBar.setValue() émet valueChanged(int) → shiboken6 ARM64 corrompt None.
# QLabel.setStyleSheet() avec qlineargradient dynamique :
#   - coordonnées relatives au widget entier (pas à un ::chunk) → dégradé correct
#   - aucun signal émis → pas de dispatch ARM64 bugué
# Mise à jour par paliers de 20 (0-1000) pour ~5-10 setStyleSheet/s max.
_VU_LABEL_BORDER = "QLabel { border: 1px solid #333; border-radius: 0px; "


def _compute_vu_colors() -> list[tuple[int, int, int]]:
    """Précalcule la couleur RGB pour chaque valeur VU 0–1000 (vert→jaune→rouge)."""
    colors: list[tuple[int, int, int]] = []
    for v in range(1001):
        t = v / 1000.0
        if t <= 0.60:
            r = int(t / 0.60 * 170)
            colors.append((r, 170, 0))
        elif t <= 0.85:
            tt = (t - 0.60) / 0.25
            colors.append((int(170 + tt * 85), int(170 * (1 - tt)), 0))
        else:
            tt = (t - 0.85) / 0.15
            colors.append((255, int(100 * (1 - tt)), 0))
    return colors


_VU_COLORS: list[tuple[int, int, int]] = _compute_vu_colors()


def _vu_label_style(vu: int) -> str:
    """Construit le style QLabel pour la valeur VU donnée (0-1000).

    Gradient vert→jaune→rouge sur la partie remplie, fond sombre sur le reste.
    Les coordonnées qlineargradient sont relatives au QLabel entier.
    """
    if vu <= 0:
        return _VU_LABEL_BORDER + "background: #1a1a1a; }"
    split = vu / 1000.0
    r, g, b = _VU_COLORS[vu]
    # Stops du gradient jusqu'au split (couleurs en position absolue dans la barre)
    stops: list[str] = ["stop:0.000 rgb(0,170,0)"]
    if split > 0.600:
        stops.append("stop:0.600 rgb(170,170,0)")
    if split > 0.850:
        stops.append("stop:0.850 rgb(255,100,0)")
    stops.append(f"stop:{split:.3f} rgb({r},{g},{b})")
    # Transition abrupte vers le fond sombre
    if split < 0.999:
        dark = min(split + 0.002, 1.0)
        stops.append(f"stop:{dark:.3f} #1a1a1a")
        stops.append("stop:1.000 #1a1a1a")
    return (
        f"{_VU_LABEL_BORDER}"
        f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {', '.join(stops)}); }}"
    )


def _make_vu_meter(parent: QWidget | None = None) -> QLabel:
    """Crée un QLabel stylé en VU meter.

    Utilise un QLabel plutôt qu'un QProgressBar : setValue() sur QProgressBar
    émet valueChanged(int) qui passe par shiboken6 ARM64 et corrompt None.
    """
    bar = QLabel(parent)
    bar.setFixedHeight(20)
    bar.setStyleSheet(_vu_label_style(0))
    return bar


# ─── Fenêtre principale ───────────────────────────────────────────────────────


class RpiVJPanel(QObject):
    """App VJing pour Raspberry Pi — micro continu → LED 64×64 → ESP32.

    Hérite de QObject (pas de QMainWindow) : la fenêtre est un QMainWindow
    pur C++ stocké dans self._win. Cela évite que shiboken6 ARM64 vérifie les
    surcharges Python pour chaque événement Qt (paintEvent, resizeEvent, …) sur
    la fenêtre principale — ces vérifications corrompent le refcount de None.
    """

    def __init__(self, esp32_host: str = "ledpanel.local") -> None:
        super().__init__()
        # Fenêtre principale pure C++ — aucun sous-classement Python
        self._win = QMainWindow()
        self._win.setWindowTitle("VJ Panel")
        self._win.setMinimumSize(900, 700)

        self._esp32_host = esp32_host
        self._esp32_ip: str | None = None  # resolved once in background thread
        self._esp32_socket: socket.socket | None = None
        self._esp32_frame_number: int = 0
        self._esp32_enabled: bool = False
        # Buffers ESP32 pré-alloués (évite 12 concaténations bytes par frame)
        _hdr = 8  # struct ">IHH" = I(4) + H(2) + H(2)
        self._esp32_bufs = [bytearray(_hdr + ESP32_CHUNK_SIZE) for _ in range(ESP32_TOTAL_CHUNKS)]
        for _i, _buf in enumerate(self._esp32_bufs):
            struct.pack_into(">H", _buf, 4, _i)                 # chunk index (fixe)
            struct.pack_into(">H", _buf, 6, ESP32_TOTAL_CHUNKS)  # total chunks (fixe)

        self._led_layer: LiveVJingLayer | None = None
        self._mic_source: MicrophoneSource | None = None
        self._frame_idx: int = 0       # boucle à total_frames (indexation énergie)
        self._abs_frame_idx: int = 0   # monotone, jamais remis à zéro (time_pos transitions)
        self._current_palette = "neon"

        self._manual_beat = False
        self._mic_mode = True  # False = mode auto sans micro
        self._last_visible: frozenset[str] = frozenset()
        self._esp32_status_pending: str | None = None  # mis à jour depuis thread de fond
        self._last_vu_int: int = 0

        # Facteur d'upscale pour la preview (LED_DISPLAY / LED_SIZE = 4)
        self._upscale = LED_DISPLAY // LED_SIZE
        # Indices pré-calculés pour l'upscale (nearest-neighbor 4×) sans allocation intermédiaire
        self._upscale_idx = np.arange(LED_SIZE, dtype=np.intp).repeat(self._upscale)
        # Buffer display partagé bytearray ↔ numpy ↔ QImage (zéro copie, zéro allocation)
        # bytearray est le seul propriétaire de la mémoire ; numpy et QImage n'en font que
        # des vues. QImage et QPixmap sont créés une seule fois (pas de dealloc shiboken6
        # ARM64) ; QPixmap.convertFromImage() les met à jour sur place chaque frame.
        self._display_rawbuf = bytearray(LED_DISPLAY * LED_DISPLAY * 3)
        self._display_arr = np.frombuffer(self._display_rawbuf, dtype=np.uint8).reshape(
            LED_DISPLAY, LED_DISPLAY, 3
        )
        # QImage pointe directement sur _display_rawbuf — créé une seule fois, jamais libéré
        self._display_qimage = QImage(
            self._display_rawbuf, LED_DISPLAY, LED_DISPLAY, 3 * LED_DISPLAY,
            QImage.Format.Format_RGB888,
        )
        # QPixmap mis à jour en place via convertFromImage() — créé une seule fois
        self._display_qpixmap = QPixmap(LED_DISPLAY, LED_DISPLAY)
        # Contexte auto pré-alloué (évite dict allocation à 30fps)
        self._auto_ctx: dict = {
            "energy": 0.5, "bass": 0.4, "mid": 0.5,
            "treble": 0.3, "fft": _AUTO_CTX_FFT, "is_beat": False,
        }

        self._timer = QTimer()
        self._timer.setInterval(1000 // FPS)
        self._timer.timeout.connect(self._update_frame)

        self._setup_ui()
        self._open_esp32_socket()
        self._start_mic()

    # ─── UI ──────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        self._win.setCentralWidget(central)
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

        self._post_fx_group.buttonToggled.connect(self._on_post_fx_toggled)
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

        esp32_row = QHBoxLayout()
        self._esp32_status = QLabel(f"ESP32: {self._esp32_host}")
        self._esp32_status.setStyleSheet("color: #888;")
        esp32_row.addWidget(self._esp32_status)
        esp32_row.addStretch()
        self._btn_esp32 = QPushButton("Send OFF")
        self._btn_esp32.setFixedHeight(36)
        self._btn_esp32.setStyleSheet(
            "QPushButton { background: #2a2a2a; color: #888; font-weight: bold; "
            "font-size: 15px; border: 2px solid #444; border-radius: 6px; padding: 0 10px; }"
        )
        self._btn_esp32.clicked.connect(self._toggle_esp32)
        esp32_row.addWidget(self._btn_esp32)
        right_layout.addLayout(esp32_row)

        # Volume gauge
        vol_row = QHBoxLayout()
        vol_lbl = QLabel("Vol:")
        vol_lbl.setStyleSheet("font-size: 20px; color: #aaa;")
        vol_lbl.setFixedWidth(44)
        vol_row.addWidget(vol_lbl)
        self._volume_bar = _make_vu_meter()
        vol_row.addWidget(self._volume_bar)
        right_layout.addLayout(vol_row)

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

        # Sélecteur de périphérique audio
        device_row = QHBoxLayout()
        self._device_combo = QComboBox()
        self._device_combo.setStyleSheet("font-size: 20px; min-height: 44px;")
        self._device_indices: list[int] = []
        self._refresh_device_list()
        device_row.addWidget(self._device_combo)
        btn_refresh = QPushButton("⟳")
        btn_refresh.setFixedSize(48, 44)
        btn_refresh.setStyleSheet(
            "QPushButton { font-size: 22px; background: #2a2a2a; color: #aaa; "
            "border: 1px solid #555; border-radius: 4px; }"
            "QPushButton:pressed { background: #444; }"
        )
        btn_refresh.clicked.connect(self._refresh_device_list)
        device_row.addWidget(btn_refresh)
        right_layout.addLayout(device_row)

        # Mode mic / auto
        self._btn_mic_mode = QPushButton("Mic ON")
        self._btn_mic_mode.setFixedHeight(48)
        self._btn_mic_mode.setStyleSheet(
            "QPushButton { background: #1a4a1a; color: #4f4; font-weight: bold; "
            "font-size: 15px; border: 2px solid #2a6a2a; border-radius: 6px; }"
        )
        self._btn_mic_mode.clicked.connect(self._toggle_mic_mode)
        right_layout.addWidget(self._btn_mic_mode)

        # Bouton passage effet suivant
        self._next_effect_btn = QPushButton("NEXT EFFECT ▶")
        self._next_effect_btn.setFixedHeight(100)
        self._next_effect_btn.setStyleSheet("""
            QPushButton {
                background: #1a1a3a;
                color: #66aaff;
                font-size: 28px;
                font-weight: bold;
                border: 2px solid #3355aa;
                border-radius: 8px;
            }
            QPushButton:pressed {
                background: #2244cc;
                color: white;
                border-color: #4488ff;
            }
        """)
        self._next_effect_btn.clicked.connect(self._on_next_effect)
        right_layout.addWidget(self._next_effect_btn)

        # Zone de tap beat (tactile)
        self._beat_btn = QPushButton("TAP BEAT")
        self._beat_btn.setFixedHeight(240)
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

        self._win.statusBar().showMessage("Starting microphone…")

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

    _STYLE_MIC_ON = (
        "QPushButton { background: #1a4a1a; color: #4f4; font-weight: bold; "
        "font-size: 15px; border: 2px solid #2a6a2a; border-radius: 6px; }"
    )
    _STYLE_MIC_OFF = (
        "QPushButton { background: #2a2a2a; color: #888; font-weight: bold; "
        "font-size: 15px; border: 2px solid #444; border-radius: 6px; }"
    )

    # ─── Mode mic / auto ─────────────────────────────────────────────────

    def _toggle_mic_mode(self) -> None:
        self._mic_mode = not self._mic_mode
        if self._mic_mode:
            self._btn_mic_mode.setText("Mic ON")
            self._btn_mic_mode.setStyleSheet(self._STYLE_MIC_ON)
            # Démarre uniquement le matériel mic — ne reconstruit PAS le layer
            # (sinon random.shuffle change l'ordre des effets en cours)
            if not HAS_SOUNDDEVICE:
                self._mic_mode = False
                self._btn_mic_mode.setText("Auto (no mic)")
                self._btn_mic_mode.setStyleSheet(self._STYLE_MIC_OFF)
                self._win.statusBar().showMessage("ERROR: sounddevice not installed — auto mode")
                return
            device = self._selected_device()
            self._mic_source = MicrophoneSource(sr=MIC_SR, block_size=MIC_BLOCK_SIZE)
            try:
                self._mic_source.start(device=device)
                self._win.statusBar().showMessage(
                    f"Mic active — device={device if device is not None else 'default'}, "
                    f"palette={self._current_palette}"
                )
            except Exception as e:
                log.error("Mic : %s", e)
                self._mic_mode = False
                self._btn_mic_mode.setText("Auto (no mic)")
                self._btn_mic_mode.setStyleSheet(self._STYLE_MIC_OFF)
                self._mic_source = None
                self._win.statusBar().showMessage(f"Mic error: {e} — auto mode")
        else:
            self._btn_mic_mode.setText("Auto (no mic)")
            self._btn_mic_mode.setStyleSheet(self._STYLE_MIC_OFF)
            if self._mic_source:
                self._mic_source.stop()
                self._mic_source = None

    def _make_auto_ctx(self) -> dict:
        """Retourne le contexte audio synthétique pré-alloué (pas de nouvelle allocation)."""
        self._auto_ctx["is_beat"] = False
        return self._auto_ctx

    # ─── Mic ─────────────────────────────────────────────────────────────

    def _refresh_device_list(self) -> None:
        """Recharge la liste des périphériques d'entrée dans le combo."""
        devices = _list_input_devices()
        self._device_combo.blockSignals(True)
        current_idx = (
            self._device_indices[self._device_combo.currentIndex()]
            if self._device_indices and self._device_combo.currentIndex() >= 0
            else None
        )
        self._device_combo.clear()
        self._device_indices = []
        # Option "défaut système"
        self._device_combo.addItem("(défaut système)")
        self._device_indices.append(-1)
        for idx, name in devices:
            self._device_combo.addItem(f"{idx}: {name}")
            self._device_indices.append(idx)
            # Pré-sélectionner USB/dongle si détecté
            if current_idx is None and any(
                kw in name.lower() for kw in ("usb", "audio device", "dongle", "card")
            ):
                self._device_combo.setCurrentIndex(len(self._device_indices) - 1)
        self._device_combo.blockSignals(False)

    def _selected_device(self) -> int | None:
        """Retourne l'index sounddevice sélectionné, ou None pour le défaut."""
        combo_idx = self._device_combo.currentIndex()
        if combo_idx < 0 or combo_idx >= len(self._device_indices):
            return None
        dev = self._device_indices[combo_idx]
        return None if dev == -1 else dev

    def _start_mic(self) -> None:
        if not HAS_SOUNDDEVICE:
            self._win.statusBar().showMessage("ERROR: sounddevice not installed — auto mode")
            self._switch_to_auto_mode()
            return

        device = self._selected_device()
        self._mic_source = MicrophoneSource(sr=MIC_SR, block_size=MIC_BLOCK_SIZE)
        try:
            self._mic_source.start(device=device)
        except Exception as e:
            log.error("Mic : %s", e)
            self._win.statusBar().showMessage(f"Mic error: {e} — auto mode")
            self._switch_to_auto_mode()
            return

        self._build_live_layer()
        self._frame_idx = 0
        self._timer.start()
        self._win.statusBar().showMessage(
            f"Mic active — {len(self._effect_checkboxes)} effects, palette={self._current_palette}"
        )

    def _switch_to_auto_mode(self) -> None:
        self._mic_mode = False
        self._btn_mic_mode.setText("Auto (no mic)")
        self._btn_mic_mode.setStyleSheet(self._STYLE_MIC_OFF)
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
            self._win.statusBar().showMessage("No effect selected")
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
            self._win.statusBar().showMessage(f"Layer error: {e}")

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

    def _on_post_fx_toggled(self, *_args: object) -> None:
        for btn in self._post_fx_group.buttons():
            btn.setStyleSheet(self._fx_btn_style(checked=btn.isChecked(), active=False))
        self._on_effect_toggled()

    def _on_effect_toggled(self, *_args: object) -> None:
        self._last_visible = frozenset()  # force style refresh sur le prochain frame
        # Feedback visuel immédiat : met à jour checked/unchecked sans attendre le timer
        for name, cb in self._effect_checkboxes.items():
            cb.setStyleSheet(self._fx_btn_style(checked=cb.isChecked(), active=False))

        checked = self._get_checked_effects()
        if not checked:
            self._led_layer = None
            self._win.statusBar().showMessage("No effect selected")
            return

        try:
            simul = int(self._simul_combo.currentText())
        except ValueError:
            simul = 1

        time_pos = self._abs_frame_idx / FPS

        if self._led_layer is not None:
            self._hot_swap_effects(checked, time_pos)
            self._led_layer.simultaneous_effects = max(1, min(10, simul))
        else:
            self._build_live_layer()

        self._win.statusBar().showMessage(
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

    # ─── Effet suivant ────────────────────────────────────────────────────

    def _on_next_effect(self) -> None:
        """Déclenche immédiatement la transition vers l'effet suivant.

        Avance _effect_phase_offset jusqu'au début de la fenêtre de transition
        (cycle - fade), ce qui démarre le fondu croisé sans saut brutal.
        """
        if self._led_layer is None:
            return
        layer = self._led_layer
        cycle = layer.effect_cycle_duration
        fade = layer.transition_duration
        time_pos = self._abs_frame_idx / FPS
        num_effects = len(layer.active_effects)
        if num_effects < 2:
            return
        total_cycle = cycle * num_effects
        t = (time_pos + layer._effect_phase_offset) % total_cycle
        pos_in_window = t % cycle
        # Avancer jusqu'au début de la fenêtre de transition (cycle - fade)
        delta = (cycle - fade) - pos_in_window
        if delta < 0:
            delta += cycle  # déjà dans la fenêtre → aller au prochain cycle
        layer._effect_phase_offset += delta

    # ─── ESP32 ───────────────────────────────────────────────────────────

    def _open_esp32_socket(self) -> None:
        self._esp32_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._esp32_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
        self._esp32_socket.setblocking(False)
        log.info("[ESP32] Socket UDP ouvert → %s:%d", self._esp32_host, ESP32_PORT)

    def _resolve_esp32_host(self) -> None:
        """Résout le hostname ESP32 en arrière-plan.
        Met à jour l'UI via _esp32_status_pending (lu dans _update_frame, thread Qt)."""
        self._esp32_status.setText(f"ESP32: {self._esp32_host} (resolving…)")
        self._esp32_ip = None

        def _resolve() -> None:
            try:
                ip = socket.gethostbyname(self._esp32_host)
                self._esp32_ip = ip
                log.info("[ESP32] Résolu : %s → %s", self._esp32_host, ip)
                self._esp32_status_pending = f"ESP32: {ip}:{ESP32_PORT}"
            except OSError as e:
                log.warning("[ESP32] Résolution échouée : %s", e)
                self._esp32_status_pending = f"ESP32: {self._esp32_host} (unreachable)"

        threading.Thread(target=_resolve, daemon=True).start()

    def _toggle_esp32(self) -> None:
        self._esp32_enabled = not self._esp32_enabled
        if self._esp32_enabled:
            self._btn_esp32.setText("Send ON")
            self._btn_esp32.setStyleSheet(
                "QPushButton { background: #1a4a1a; color: #4f4; font-weight: bold; "
                "font-size: 15px; border: 2px solid #2a6a2a; border-radius: 6px; padding: 0 10px; }"
            )
            self._resolve_esp32_host()
        else:
            self._btn_esp32.setText("Send OFF")
            self._btn_esp32.setStyleSheet(
                "QPushButton { background: #2a2a2a; color: #888; font-weight: bold; "
                "font-size: 15px; border: 2px solid #444; border-radius: 6px; padding: 0 10px; }"
            )

    def _send_frame_to_esp32(self, arr64: np.ndarray) -> None:
        """Envoie le frame 64×64 RGB en 12 chunks UDP.

        arr64 : array numpy uint8 (64, 64, 3) — pas de copie supplémentaire.
        """
        if self._esp32_socket is None or not self._esp32_enabled or self._esp32_ip is None:
            return
        try:
            raw = arr64.tobytes()
            dest = (self._esp32_ip, ESP32_PORT)
            fn = self._esp32_frame_number
            for i, buf in enumerate(self._esp32_bufs):
                struct.pack_into(">I", buf, 0, fn)
                buf[8:] = raw[i * ESP32_CHUNK_SIZE : (i + 1) * ESP32_CHUNK_SIZE]
                self._esp32_socket.sendto(buf, dest)
            self._esp32_frame_number += 1
        except OSError as e:
            log.warning("[ESP32] Erreur envoi : %s", e)

    # ─── Rendu ───────────────────────────────────────────────────────────

    @Slot()
    def _update_frame(self) -> None:
        # Mise à jour status ESP32 depuis thread de fond (thread-safe)
        if self._esp32_status_pending is not None:
            self._esp32_status.setText(self._esp32_status_pending)
            self._esp32_status_pending = None

        if self._led_layer is None:
            return

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
        vu = max(0, min(1000, int(ctx["bass"] * 1000)))
        if vu != self._last_vu_int:
            old_bucket = self._last_vu_int // 20
            self._last_vu_int = vu
            if vu // 20 != old_bucket:
                self._volume_bar.setStyleSheet(_vu_label_style(vu))

        # time_pos monotone (jamais remis à zéro) → transitions sans hard cut
        time_pos = self._abs_frame_idx / FPS

        try:
            led_img = self._led_layer.render(self._frame_idx, time_pos)
            arr_rgba = np.asarray(led_img, dtype=np.uint8)  # view sur buffer PIL, pas de copie
            arr64 = (arr_rgba[:, :, :3] * (arr_rgba[:, :, 3:4].astype(np.float32) / 255.0)).astype(
                np.uint8
            )
            idx = self._upscale_idx
            np.copyto(self._display_arr, arr64[idx][:, idx])
            self._send_frame_to_esp32(arr64)
            self._display_qpixmap.convertFromImage(self._display_qimage)
            self._led_label.setPixmap(self._display_qpixmap)
        except Exception as e:
            log.error("[Render] frame %d : %s", self._frame_idx, e)
        self._highlight_active_effects(time_pos)
        total = self._led_layer.total_frames if self._led_layer else 1
        self._frame_idx = (self._frame_idx + 1) % total
        self._abs_frame_idx += 1

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
        except Exception as e:
            log.warning("[Highlight] %s", e)
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
        dlg = QMessageBox(self._win)
        dlg.setWindowTitle("Quit")
        dlg.setText("Quit the application?")
        dlg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dlg.setDefaultButton(QMessageBox.StandardButton.No)
        dlg.setStyleSheet("font-size: 28px;")
        if dlg.exec() == QMessageBox.StandardButton.Yes:
            self._win.close()

    # ─── Nettoyage ───────────────────────────────────────────────────────

    @Slot()
    def _cleanup(self) -> None:
        """Nettoyage à la fermeture — connecté à QApplication.aboutToQuit."""
        self._timer.stop()
        if self._mic_source:
            self._mic_source.stop()
        if self._esp32_socket:
            self._esp32_socket.close()


# ─── Entrée ───────────────────────────────────────────────────────────────────


def main() -> None:
    # Active le traceback Python pour les crash C-level (SIGABRT, SIGSEGV…)
    faulthandler.enable()

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
    app.aboutToQuit.connect(window._cleanup)
    window._win.showFullScreen()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
