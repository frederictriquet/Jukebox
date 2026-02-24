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

import numpy as np
import vlc
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
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
LED_PANEL_SIZE = 32  # render resolution for LED panel
LED_PANEL_DISPLAY = 256  # display size (32x32 scaled up with nearest-neighbor)
FPS = 30
DB_PATH = Path.home() / ".jukebox" / "jukebox.db"


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
        btn_row.addWidget(self._btn_play)
        btn_row.addWidget(self._btn_stop)
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

        # Post-processing effects
        post_box = QGroupBox("Post-Processing")
        post_layout = QHBoxLayout(post_box)
        post_layout.setContentsMargins(4, 4, 4, 4)
        post_layout.setSpacing(8)
        for effect_name in post_effects:
            cb = QCheckBox(effect_name)
            cb.setChecked(False)
            cb.toggled.connect(self._on_effect_toggled)
            post_layout.addWidget(cb)
            self._effect_checkboxes[effect_name] = cb
        for effect_name in final_effects:
            cb = QCheckBox(effect_name)
            cb.setChecked(False)
            cb.toggled.connect(self._on_effect_toggled)
            post_layout.addWidget(cb)
            self._effect_checkboxes[effect_name] = cb
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

        # Right panel — previews
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # Main preview (512x512)
        self._preview_label = QLabel()
        self._preview_label.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self._preview_label.setStyleSheet("background: black;")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self._preview_label)

        # LED panel preview (32x32 rendered, displayed at 256x256 with big pixels)
        led_group = QGroupBox("LED Panel (32x32)")
        led_layout = QHBoxLayout(led_group)
        led_layout.setContentsMargins(4, 4, 4, 4)
        self._led_label = QLabel()
        self._led_label.setFixedSize(LED_PANEL_DISPLAY, LED_PANEL_DISPLAY)
        self._led_label.setStyleSheet("background: black;")
        self._led_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        led_layout.addWidget(self._led_label)
        led_layout.addStretch()
        right_layout.addWidget(led_group)

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
        return [name for name, cb in self._effect_checkboxes.items() if cb.isChecked()]

    def _build_layers(self) -> None:
        """Full rebuild of both VJingLayers (expensive — audio analysis + precompute)."""
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

        self.statusBar().showMessage(f"Building VJing layers ({len(checked)} effects)...")
        QApplication.processEvents()

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
        )

        try:
            self._vjing_layer = VJingLayer(width=PREVIEW_SIZE, height=PREVIEW_SIZE, **common)
            self._led_layer = VJingLayer(width=LED_PANEL_SIZE, height=LED_PANEL_SIZE, **common)
            self.statusBar().showMessage(
                f"Ready — {len(checked)} effects, palette={self._current_palette}"
            )
        except Exception as e:
            log.error(f"Failed to create VJingLayer: {e}")
            self._vjing_layer = None
            self._led_layer = None
            self.statusBar().showMessage(f"VJing error: {e}")

    @staticmethod
    def _hot_swap_effects(layer: VJingLayer, effects: list[str]) -> None:
        """Update active effects on an existing layer without re-doing audio analysis.

        Only calls _init_* for effects that are newly added and need state.
        """
        old = set(layer.active_effects)
        layer.active_effects = list(effects)
        layer.presets["_playground"] = list(effects)

        # Initialize state for newly added effects that have an _init_<name> method
        for name in effects:
            if name not in old and hasattr(layer, f"_init_{name}"):
                getattr(layer, f"_init_{name}")()

    def _on_effect_toggled(self, *_args: object) -> None:
        checked = self._get_checked_effects()
        if not checked:
            self._vjing_layer = None
            self._led_layer = None
            self.statusBar().showMessage("No effects selected")
            return
        # Layers destroyed (e.g. after "None") — full rebuild needed
        if self._vjing_layer is None or self._led_layer is None:
            self._build_layers()
            return
        for layer in (self._vjing_layer, self._led_layer):
            self._hot_swap_effects(layer, checked)
        try:
            simul = int(self._simul_combo.currentText())
        except ValueError:
            simul = 3
        for layer in (self._vjing_layer, self._led_layer):
            if layer is not None:
                layer.simultaneous_effects = max(1, min(10, simul))
        self.statusBar().showMessage(f"{len(checked)} effects, palette={self._current_palette}")

    def _on_palette_changed(self, palette_name: str) -> None:
        self._current_palette = palette_name
        for layer in (self._vjing_layer, self._led_layer):
            if layer is not None:
                layer.color_palette_name = palette_name
                layer.color_palette = VJingLayer.COLOR_PALETTES.get(
                    palette_name, VJingLayer.COLOR_PALETTES["neon"]
                )

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
        if self._vjing_layer is None:
            return

        total = self._vjing_layer.total_frames
        if self._frame_idx >= total:
            self._frame_idx = total - 1

        time_pos = self._frame_idx / FPS

        try:
            # Main preview (512x512)
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

        try:
            # LED panel preview (32x32 -> scaled up with nearest-neighbor)
            if self._led_layer is not None:
                from PIL import Image as PILImage

                led_img = self._led_layer.render(self._frame_idx, time_pos)
                led_rgb = led_img.convert("RGB")
                # Nearest-neighbor upscale to preserve big pixel look
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

        self._frame_idx += 1

    # ─── Cleanup ───────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        self._position_timer.stop()
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
