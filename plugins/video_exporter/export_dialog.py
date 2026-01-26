"""Export configuration dialog for video exporter plugin."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QGridLayout,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap

import vlc

from jukebox.core.event_bus import Events

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol


# Resolution presets: name -> (width, height)
RESOLUTION_PRESETS: dict[str, tuple[int, int]] = {
    "1080p": (1920, 1080),
    "720p": (1280, 720),
    "square_1080": (1080, 1080),
    "square_720": (720, 720),
    "vertical": (1080, 1920),
}


class EffectPreviewDialog(QDialog):
    """Dialog for previewing a single VJing effect."""

    def __init__(
        self,
        parent: QWidget | None,
        context: "PluginContextProtocol",
        effect_id: str,
        effect_name: str,
        filepath: Path,
        loop_start: float,
        loop_end: float,
        intensity: float,
        color_palette: str,
        audio_sensitivity: dict[str, float],
        track_metadata: dict[str, Any],
    ) -> None:
        """Initialize effect preview dialog.

        Args:
            parent: Parent widget.
            context: Plugin context for audio player access.
            effect_id: Effect identifier.
            effect_name: Display name of the effect.
            filepath: Path to the audio file.
            loop_start: Loop start position in seconds.
            loop_end: Loop end position in seconds.
            intensity: Effect intensity (0.0-1.0).
            color_palette: Color palette name.
            audio_sensitivity: Audio sensitivity settings.
            track_metadata: Track metadata dictionary.
        """
        super().__init__(parent)
        self.context = context
        self.effect_id = effect_id
        self.effect_name = effect_name
        self.filepath = filepath
        self.loop_start = loop_start
        self.loop_end = loop_end
        self.intensity = intensity
        self.color_palette = color_palette
        self.audio_sensitivity = audio_sensitivity
        self.track_metadata = track_metadata

        # Preview state
        self._vjing_layer = None
        self._audio = None
        self._sr = 22050
        self._fps = 30
        self._playing = False
        self._frame = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_frame)

        # Local VLC player (independent from main app player)
        self._vlc_instance = vlc.Instance()
        self._vlc_player = self._vlc_instance.media_player_new()
        self._vlc_released = False  # Track if VLC resources were released

        self.setWindowTitle(f"Preview: {effect_name}")
        self.setMinimumSize(400, 350)

        self._setup_ui()
        self._load_effect()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        self.setStyleSheet("""
            QDialog { background: #2b2b2b; }
            QLabel { color: #ffffff; }
            QPushButton {
                background: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover { background: #4a4a4a; }
            QPushButton:pressed { background: #0078d4; }
        """)

        layout = QVBoxLayout(self)

        # Preview display
        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(320, 180)
        self.preview_label.setStyleSheet("background: #000; border: 1px solid #555;")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setText("Loading...")
        layout.addWidget(self.preview_label, alignment=Qt.AlignCenter)

        # Time slider
        time_layout = QHBoxLayout()
        self.time_label = QLabel("0.0s")
        self.time_label.setMinimumWidth(40)
        self.time_slider = QSlider(Qt.Horizontal)
        self.time_slider.setRange(0, 100)
        self.time_slider.setValue(0)
        self.time_slider.valueChanged.connect(self._on_time_changed)
        self.duration_label = QLabel("0.0s")
        self.duration_label.setMinimumWidth(40)
        time_layout.addWidget(self.time_label)
        time_layout.addWidget(self.time_slider)
        time_layout.addWidget(self.duration_label)
        layout.addLayout(time_layout)

        # Control buttons
        controls_layout = QHBoxLayout()
        controls_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self._stop_and_close)
        controls_layout.addWidget(close_btn)
        layout.addLayout(controls_layout)

    def _stop_and_close(self) -> None:
        """Stop playback and close the dialog."""
        if self._timer.isActive():
            self._timer.stop()
        
        # Stop VLC (release will happen in closeEvent)
        if not self._vlc_released:
            try:
                self._vlc_player.stop()
            except Exception:
                pass
        
        self.close()

    def _load_effect(self) -> None:
        """Load audio and initialize the effect renderer."""
        try:
            import librosa
            from plugins.video_exporter.layers.vjing_layer import VJingLayer
        except ImportError as e:
            self.preview_label.setText(f"Error: {e}")
            return

        duration = self.loop_end - self.loop_start
        fps = 30  # Fixed FPS for preview
        width, height = 320, 180  # Small preview size

        try:
            # Load audio
            self._audio, self._sr = librosa.load(
                str(self.filepath),
                sr=22050,
                offset=self.loop_start,
                duration=duration,
                mono=True,
            )

            # Create VJingLayer with only this effect active
            # We use a custom preset that only has this effect
            # NOTE: use_gpu=False to ensure palette colors are applied (GPU shaders have hardcoded colors)
            self._vjing_layer = VJingLayer(
                width=width,
                height=height,
                fps=fps,
                audio=self._audio,
                sr=self._sr,
                duration=duration,
                genre="",  # No genre mapping
                preset="_single_effect",  # Custom preset name
                presets={"_single_effect": [self.effect_id]},  # Only this effect
                intensity=self.intensity,
                color_palette=self.color_palette,
                audio_sensitivity=self.audio_sensitivity,
                use_gpu=True,  # GPU shaders now support dynamic palettes
            )

            # Update UI
            total_frames = int(duration * fps)
            self.time_slider.setRange(0, max(1, total_frames - 1))
            self.time_slider.setValue(0)
            self.duration_label.setText(f"{duration:.1f}s")
            self._frame = 0
            self._fps = fps

            # Render first frame
            self._refresh_frame()

            # Auto-start playback
            self._start_playback()

        except Exception as e:
            logging.exception(f"[Effect Preview] Failed to load effect {self.effect_id}")
            self.preview_label.setText(f"Error: {e}")

    def _on_time_changed(self, value: int) -> None:
        """Handle time slider change."""
        if self._vjing_layer is None:
            return

        self._frame = value
        time_pos = value / self._fps
        self.time_label.setText(f"{time_pos:.1f}s")

        # Sync VLC player position (time_pos is relative to loop, add loop_start)
        if not self._vlc_released:
            absolute_time_ms = int((self.loop_start + time_pos) * 1000)
            try:
                self._vlc_player.set_time(absolute_time_ms)
            except Exception:
                pass

        if not self._playing:
            self._refresh_frame()

    def _start_playback(self) -> None:
        """Start preview playback automatically."""
        if self._playing:
            return

        interval = int(1000 / self._fps)

        # Load audio file in local VLC player
        media = self._vlc_instance.media_new(str(self.filepath))
        self._vlc_player.set_media(media)
        # Position at loop start (in milliseconds)
        self._vlc_player.play()
        # Wait a bit for player to initialize, then seek
        QTimer.singleShot(50, lambda: self._vlc_player.set_time(int(self.loop_start * 1000)))

        self._timer.start(interval)
        self._playing = True

    def _update_frame(self) -> None:
        """Update frame (called by timer)."""
        if self._vjing_layer is None:
            return

        self._frame += 1
        max_frame = self.time_slider.maximum()
        if self._frame > max_frame:
            self._frame = 0
            # Reposition audio to loop start
            self._vlc_player.set_time(int(self.loop_start * 1000))

        self.time_slider.blockSignals(True)
        self.time_slider.setValue(self._frame)
        self.time_slider.blockSignals(False)

        time_pos = self._frame / self._fps
        self.time_label.setText(f"{time_pos:.1f}s")

        self._refresh_frame()

    def _refresh_frame(self) -> None:
        """Render and display the current frame."""
        if self._vjing_layer is None:
            return

        try:
            time_pos = self._frame / self._fps

            # Render frame from VJingLayer
            img = self._vjing_layer.render(self._frame, time_pos)

            # Composite onto black background (same as export)
            # This ensures preview matches final video output
            background = Image.new("RGBA", img.size, (0, 0, 0, 255))
            background.paste(img, (0, 0), img)

            # Convert to RGB numpy array
            rgb = background.convert("RGB")
            frame = np.array(rgb, dtype=np.uint8)

            height, width, channels = frame.shape
            bytes_per_line = channels * width
            qimage = QImage(
                frame.data, width, height, bytes_per_line, QImage.Format_RGB888
            )
            pixmap = QPixmap.fromImage(qimage)

            self.preview_label.setPixmap(pixmap)

        except Exception as e:
            logging.warning(f"[Effect Preview] Render failed: {e}")

    def reject(self) -> None:
        """Handle Escape key - stop playback before closing."""
        if self._timer.isActive():
            self._timer.stop()
        
        # Stop VLC (release will happen in closeEvent)
        if not self._vlc_released:
            try:
                self._vlc_player.stop()
            except Exception:
                pass
        
        super().reject()

    def closeEvent(self, event: Any) -> None:
        """Clean up resources when dialog is closed."""
        if self._timer.isActive():
            self._timer.stop()
        
        # Only release VLC resources once
        if not self._vlc_released:
            self._vlc_released = True
            try:
                self._vlc_player.stop()
                self._vlc_player.release()
                self._vlc_instance.release()
            except Exception:
                pass  # Ignore VLC cleanup errors
        
        self._vjing_layer = None
        self._audio = None
        super().closeEvent(event)


class ExportDialog(QDialog):
    """Dialog for configuring and initiating video export."""

    def __init__(
        self,
        parent: QWidget | None,
        context: PluginContextProtocol,
        filepath: Path,
        loop_start: float,
        loop_end: float,
        track_metadata: dict[str, Any],
    ) -> None:
        """Initialize export dialog.

        Args:
            parent: Parent widget.
            context: Plugin context.
            filepath: Path to the audio file.
            loop_start: Loop start position in seconds.
            loop_end: Loop end position in seconds.
            track_metadata: Track metadata dictionary.
        """
        super().__init__(parent)
        self.context = context
        self.filepath = filepath
        self.loop_start = loop_start
        self.loop_end = loop_end
        self.track_metadata = track_metadata
        self.worker = None

        # Preview state
        self._preview_renderer = None
        self._preview_audio = None
        self._preview_sr = 22050
        self._preview_playing = False
        self._preview_frame = 0
        self._preview_timer = QTimer(self)
        self._preview_timer.timeout.connect(self._update_preview_frame)

        # Local VLC player for preview (independent from main app player)
        self._vlc_instance = vlc.Instance()
        self._vlc_player = self._vlc_instance.media_player_new()

        self.setWindowTitle("Export Video")
        self.setMinimumWidth(600)
        self.setMinimumHeight(600)

        self._apply_dark_style()
        self._setup_ui()
        self._load_defaults()

    def _apply_dark_style(self) -> None:
        """Apply dark mode compatible styling."""
        self.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #555;
                background: #2b2b2b;
            }
            QTabBar::tab {
                background: #3c3c3c;
                color: #ffffff;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #0078d4;
            }
            QTabBar::tab:hover:!selected {
                background: #4a4a4a;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555;
                border-radius: 4px;
                margin-top: 12px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QCheckBox {
                spacing: 8px;
                padding: 4px 0;
            }
            QLabel {
                color: #ffffff;
            }
            QComboBox {
                color: #ffffff;
                background: #3c3c3c;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                color: #ffffff;
                background: #3c3c3c;
                selection-background-color: #0078d4;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #555;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #0078d4;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: #0078d4;
                border-radius: 3px;
            }
        """)

    def _get_metadata(self, key: str, default: str = "Unknown") -> str:
        """Get metadata value safely from sqlite3.Row or dict.

        Args:
            key: Metadata key to retrieve.
            default: Default value if key not found.

        Returns:
            Metadata value or default.
        """
        try:
            value = self.track_metadata[key]
            return value if value else default
        except (KeyError, IndexError):
            return default

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Info label
        duration = self.loop_end - self.loop_start
        artist = self._get_metadata("artist")
        title = self._get_metadata("title")
        info_text = f"Exporting: {artist} - {title}\nDuration: {duration:.1f}s"
        info_label = QLabel(info_text)
        info_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(info_label)

        # Tab widget for settings
        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(320)  # Prevent compression when progress appears
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)

        # General tab
        self._create_general_tab()

        # Layers tab
        self._create_layers_tab()

        # Progress section (hidden initially)
        self.progress_widget = QWidget()
        self.progress_widget.setFixedHeight(60)  # Fixed height for progress section
        progress_layout = QVBoxLayout(self.progress_widget)
        progress_layout.setContentsMargins(0, 5, 0, 0)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        progress_layout.addWidget(self.progress_bar)
        self.progress_label = QLabel("Ready to export")
        progress_layout.addWidget(self.progress_label)
        self.progress_widget.setVisible(False)
        layout.addWidget(self.progress_widget)

        # Buttons
        self.button_box = QDialogButtonBox()
        self.export_button = self.button_box.addButton(
            "Export", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.cancel_button = self.button_box.addButton(
            "Cancel", QDialogButtonBox.ButtonRole.RejectRole
        )
        self.button_box.accepted.connect(self._start_export)
        self.button_box.rejected.connect(self._on_cancel)
        layout.addWidget(self.button_box)

    def _create_general_tab(self) -> None:
        """Create the general settings tab."""
        tab = QWidget()
        layout = QFormLayout(tab)

        # Resolution
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(list(RESOLUTION_PRESETS.keys()))
        layout.addRow("Resolution:", self.resolution_combo)

        # FPS
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(15, 60)
        self.fps_spin.setValue(30)
        layout.addRow("FPS:", self.fps_spin)

        # Output directory
        output_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("Select output directory...")
        output_layout.addWidget(self.output_dir_edit)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_output_dir)
        output_layout.addWidget(browse_button)
        layout.addRow("Output Directory:", output_layout)

        # Output filename
        self.filename_edit = QLineEdit()
        self._generate_default_filename()
        layout.addRow("Filename:", self.filename_edit)

        self.tabs.addTab(tab, "General")

    def _create_layers_tab(self) -> None:
        """Create the layers settings tab."""
        # Create scroll area for the tab content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        # Content widget inside scroll area
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)

        # Layer toggles group
        layers_group = QGroupBox("Visual Layers")
        layers_layout = QVBoxLayout(layers_group)
        layers_layout.setSpacing(8)
        layers_layout.setContentsMargins(12, 16, 12, 12)

        self.waveform_check = QCheckBox("Waveform (animated with cursor)")
        layers_layout.addWidget(self.waveform_check)

        self.text_check = QCheckBox("Text Overlay (Artist + Title)")
        layers_layout.addWidget(self.text_check)

        self.dynamics_check = QCheckBox("Dynamics Effects (energy-based)")
        layers_layout.addWidget(self.dynamics_check)

        self.vjing_check = QCheckBox("VJing Effects")
        layers_layout.addWidget(self.vjing_check)

        # VJing preset selector
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("    Preset:"))
        self.vjing_preset_combo = QComboBox()
        self.vjing_preset_combo.addItem("(Use genre mapping)", "")
        for preset in self.context.config.video_exporter.vjing_presets:
            self.vjing_preset_combo.addItem(preset.name, preset.name)
        self.vjing_preset_combo.setToolTip("Select a preset or use genre-based effects")
        preset_layout.addWidget(self.vjing_preset_combo)
        preset_layout.addStretch()
        layers_layout.addLayout(preset_layout)

        # Color palette selector
        palette_layout = QHBoxLayout()
        palette_layout.addWidget(QLabel("    Palette:"))
        self.color_palette_combo = QComboBox()
        palettes = [
            ("neon", "Neon (Pink/Cyan/Yellow)"),
            ("fire", "Fire (Orange/Red/Gold)"),
            ("ice", "Ice (Blue/White)"),
            ("nature", "Nature (Greens)"),
            ("sunset", "Sunset (Coral/Peach)"),
            ("ocean", "Ocean (Turquoise/Cyan)"),
            ("cosmic", "Cosmic (Purple/Violet)"),
            ("retro", "Retro (Mustard/Teal)"),
            ("monochrome", "Monochrome (Grays)"),
            ("rainbow", "Rainbow"),
        ]
        for palette_id, palette_name in palettes:
            self.color_palette_combo.addItem(palette_name, palette_id)
        self.color_palette_combo.setToolTip("Color palette for VJing effects")
        palette_layout.addWidget(self.color_palette_combo)
        palette_layout.addStretch()
        layers_layout.addLayout(palette_layout)

        # Transitions toggle
        self.transitions_check = QCheckBox("    Transitions (cycle entre effets avec fade)")
        self.transitions_check.setChecked(True)  # Default: enabled
        self.transitions_check.setToolTip(
            "Activé: les effets s'affichent un par un avec crossfade\n"
            "Désactivé: tous les effets sont superposés simultanément"
        )
        layers_layout.addWidget(self.transitions_check)

        self.video_bg_check = QCheckBox("Video Background")
        layers_layout.addWidget(self.video_bg_check)

        # Video folder selector (indented under Video Background)
        video_folder_layout = QHBoxLayout()
        video_folder_layout.addSpacing(24)  # Indent
        video_folder_layout.addWidget(QLabel("Folder:"))
        self.video_folder_edit = QLineEdit()
        self.video_folder_edit.setPlaceholderText("Click to select folder...")
        self.video_folder_edit.setReadOnly(True)
        self.video_folder_edit.setCursor(Qt.PointingHandCursor)
        self.video_folder_edit.mousePressEvent = lambda e: self._browse_video_folder()
        video_folder_layout.addWidget(self.video_folder_edit)
        layers_layout.addLayout(video_folder_layout)

        layout.addWidget(layers_group)

        # Effect intensities group
        intensity_group = QGroupBox("Effect Intensities")
        intensity_main_layout = QVBoxLayout(intensity_group)
        intensity_main_layout.setContentsMargins(12, 20, 12, 12)
        intensity_main_layout.setSpacing(8)

        # Global intensity slider at the top
        global_layout = QHBoxLayout()
        global_label = QLabel("Global:")
        global_label.setFixedWidth(60)
        self.global_intensity_slider = QSlider(Qt.Horizontal)
        self.global_intensity_slider.setRange(0, 100)
        self.global_intensity_slider.setValue(100)
        self.global_intensity_slider.setToolTip("Default intensity for all effects")
        self.global_intensity_label = QLabel("100%")
        self.global_intensity_label.setFixedWidth(40)
        self.global_intensity_slider.valueChanged.connect(
            lambda v: self.global_intensity_label.setText(f"{v}%")
        )
        global_layout.addWidget(global_label)
        global_layout.addWidget(self.global_intensity_slider)
        global_layout.addWidget(self.global_intensity_label)
        intensity_main_layout.addLayout(global_layout)

        # Per-effect intensity sliders (all effects grouped by theme)
        self.effect_intensity_sliders: dict[str, QSlider] = {}
        self.effect_intensity_labels: dict[str, QLabel] = {}

        # All effects organized by theme (split into 2 columns)
        effect_groups_left = [
            ("Rythmiques", [
                ("pulse", "Pulse"),
                ("strobe", "Strobe"),
            ]),
            ("Spectraux", [
                ("fft_bars", "FFT Bars"),
                ("fft_rings", "FFT Rings"),
                ("bass_warp", "Bass Warp"),
            ]),
            ("Particules", [
                ("particles", "Particles"),
                ("flow_field", "Flow Field"),
                ("explosion", "Explosion"),
                ("starfield", "Starfield"),
            ]),
            ("Géométriques", [
                ("kaleidoscope", "Kaleidoscope"),
                ("lissajous", "Lissajous"),
                ("tunnel", "Tunnel"),
                ("spiral", "Spiral"),
                ("radar", "Radar"),
            ]),
        ]

        effect_groups_right = [
            ("GPU", [
                ("fractal", "Fractal"),
                ("plasma", "Plasma"),
                ("wormhole", "Wormhole"),
                ("voronoi", "Voronoi"),
                ("metaballs", "Metaballs"),
            ]),
            ("Naturels", [
                ("fire", "Fire"),
                ("water", "Water"),
                ("aurora", "Aurora"),
                ("smoke", "Smoke"),
                ("lightning", "Lightning"),
            ]),
            ("Classiques", [
                ("wave", "Wave"),
                ("neon", "Neon"),
                ("vinyl", "Vinyl"),
            ]),
            ("Post-process", [
                ("chromatic", "Chromatic"),
                ("pixelate", "Pixelate"),
                ("feedback", "Feedback"),
            ]),
        ]

        # Two-column layout for effects
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(20)

        def create_effect_column(groups: list) -> QWidget:
            """Create a column widget with effect groups."""
            column = QWidget()
            col_layout = QVBoxLayout(column)
            col_layout.setContentsMargins(0, 0, 0, 0)
            col_layout.setSpacing(4)

            for group_name, effects in groups:
                # Group header
                header = QLabel(group_name)
                header.setStyleSheet("color: #aaa; font-weight: bold; font-size: 10px;")
                col_layout.addWidget(header)

                for effect_id, effect_name in effects:
                    row_layout = QHBoxLayout()
                    row_layout.setSpacing(4)

                    name_label = QLabel(f"{effect_name}:")
                    name_label.setFixedWidth(75)
                    slider = QSlider(Qt.Horizontal)
                    slider.setRange(0, 100)
                    slider.setValue(100)
                    slider.setMinimumWidth(80)
                    slider.setToolTip(f"Intensity for {effect_name} effect")
                    value_label = QLabel("100%")
                    value_label.setFixedWidth(35)
                    slider.valueChanged.connect(
                        lambda v, lbl=value_label: lbl.setText(f"{v}%")
                    )
                    # Preview button
                    preview_btn = QPushButton("👁")
                    preview_btn.setFixedSize(24, 24)
                    preview_btn.setToolTip(f"Preview {effect_name}")
                    preview_btn.clicked.connect(
                        lambda checked, eid=effect_id, ename=effect_name: self._preview_single_effect(eid, ename)
                    )

                    row_layout.addWidget(name_label)
                    row_layout.addWidget(slider)
                    row_layout.addWidget(value_label)
                    row_layout.addWidget(preview_btn)
                    col_layout.addLayout(row_layout)

                    self.effect_intensity_sliders[effect_id] = slider
                    self.effect_intensity_labels[effect_id] = value_label

            col_layout.addStretch()
            return column

        columns_layout.addWidget(create_effect_column(effect_groups_left))
        columns_layout.addWidget(create_effect_column(effect_groups_right))

        intensity_main_layout.addLayout(columns_layout)
        layout.addWidget(intensity_group)

        # Audio sensitivity group
        sensitivity_group = QGroupBox("Audio Sensitivity")
        sensitivity_layout = QGridLayout(sensitivity_group)
        sensitivity_layout.setContentsMargins(12, 20, 12, 12)
        sensitivity_layout.setVerticalSpacing(8)
        sensitivity_layout.setColumnStretch(1, 1)
        sensitivity_layout.setColumnMinimumWidth(0, 80)
        sensitivity_layout.setColumnMinimumWidth(2, 40)

        self.audio_sensitivity_sliders: dict[str, QSlider] = {}
        self.audio_sensitivity_labels: dict[str, QLabel] = {}

        bands = [
            ("bass", "Bass"),
            ("mid", "Mid"),
            ("treble", "Treble"),
        ]

        for row, (band_id, band_name) in enumerate(bands):
            name_label = QLabel(f"{band_name}:")
            name_label.setFixedHeight(28)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 200)  # 0% to 200%
            slider.setValue(100)  # Default 100%
            slider.setMinimumWidth(150)
            slider.setFixedHeight(28)
            slider.setToolTip(f"Reactivity to {band_name.lower()} frequencies (0-200%)")
            value_label = QLabel("100%")
            value_label.setMinimumWidth(40)
            value_label.setFixedHeight(28)
            slider.valueChanged.connect(
                lambda v, lbl=value_label: lbl.setText(f"{v}%")
            )
            sensitivity_layout.addWidget(name_label, row, 0)
            sensitivity_layout.addWidget(slider, row, 1)
            sensitivity_layout.addWidget(value_label, row, 2)
            self.audio_sensitivity_sliders[band_id] = slider
            self.audio_sensitivity_labels[band_id] = value_label

        layout.addWidget(sensitivity_group)
        layout.addStretch()

        scroll.setWidget(content)
        self.tabs.addTab(scroll, "Layers")

        # Preview tab
        preview_tab = QWidget()
        preview_layout = QVBoxLayout(preview_tab)

        # Preview display
        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(480, 270)
        self.preview_label.setMaximumSize(640, 360)
        self.preview_label.setStyleSheet("background: #1a1a1a; border: 1px solid #555;")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setText("Click 'Load Preview' to start")
        preview_layout.addWidget(self.preview_label, alignment=Qt.AlignCenter)

        # Time slider
        time_layout = QHBoxLayout()
        self.preview_time_label = QLabel("0.0s")
        self.preview_time_label.setMinimumWidth(50)
        self.preview_time_slider = QSlider(Qt.Horizontal)
        self.preview_time_slider.setRange(0, 1000)
        self.preview_time_slider.setValue(0)
        self.preview_time_slider.valueChanged.connect(self._on_preview_time_changed)
        self.preview_duration_label = QLabel("0.0s")
        self.preview_duration_label.setMinimumWidth(50)
        time_layout.addWidget(self.preview_time_label)
        time_layout.addWidget(self.preview_time_slider)
        time_layout.addWidget(self.preview_duration_label)
        preview_layout.addLayout(time_layout)

        # Control buttons
        controls_layout = QHBoxLayout()
        self.preview_load_btn = QPushButton("Load Preview")
        self.preview_load_btn.clicked.connect(self._load_preview)
        self.preview_play_btn = QPushButton("Play")
        self.preview_play_btn.clicked.connect(self._toggle_preview_playback)
        self.preview_play_btn.setEnabled(False)
        self.preview_refresh_btn = QPushButton("Refresh Frame")
        self.preview_refresh_btn.clicked.connect(self._refresh_preview_frame)
        self.preview_refresh_btn.setEnabled(False)
        controls_layout.addWidget(self.preview_load_btn)
        controls_layout.addWidget(self.preview_play_btn)
        controls_layout.addWidget(self.preview_refresh_btn)
        controls_layout.addStretch()
        preview_layout.addLayout(controls_layout)

        # Preview info
        self.preview_info_label = QLabel("Preview uses current settings from other tabs")
        self.preview_info_label.setStyleSheet("color: #888; font-style: italic;")
        preview_layout.addWidget(self.preview_info_label)

        preview_layout.addStretch()
        self.tabs.addTab(preview_tab, "Preview")

    def _load_defaults(self) -> None:
        """Load default values from config."""
        config = self.context.config.video_exporter

        # General
        self.resolution_combo.setCurrentText(config.default_resolution)
        self.fps_spin.setValue(config.default_fps)
        self.output_dir_edit.setText(str(Path(config.output_directory).expanduser()))
        self.video_folder_edit.setText(config.video_clips_folder)

        # Layers
        self.waveform_check.setChecked(config.waveform_enabled)
        self.text_check.setChecked(config.text_enabled)
        self.dynamics_check.setChecked(config.dynamics_enabled)
        self.vjing_check.setChecked(config.vjing_enabled)
        self.video_bg_check.setChecked(config.video_background_enabled)

    def _generate_default_filename(self) -> None:
        """Generate a default filename based on track metadata."""
        artist = self._get_metadata("artist")
        title = self._get_metadata("title")
        # Sanitize filename
        safe_artist = "".join(c if c.isalnum() or c in " -_" else "_" for c in artist)
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
        self.filename_edit.setText(f"{safe_artist} - {safe_title}.mp4")

    def _browse_output_dir(self) -> None:
        """Browse for output directory."""
        current = self.output_dir_edit.text() or str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory", current)
        if directory:
            self.output_dir_edit.setText(directory)

    def _browse_video_folder(self) -> None:
        """Browse for video clips folder."""
        current = self.video_folder_edit.text() or str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Select Video Clips Folder", current)
        if directory:
            self.video_folder_edit.setText(directory)

    def _load_preview(self) -> None:
        """Load audio and initialize preview renderer."""
        try:
            import librosa
            from plugins.video_exporter.renderers.frame_renderer import FrameRenderer
        except ImportError as e:
            self.preview_info_label.setText(f"Error: {e}")
            return

        self.preview_load_btn.setEnabled(False)
        self.preview_info_label.setText("Loading audio...")
        self.preview_label.setText("Loading...")

        # Get preview settings
        duration = self.loop_end - self.loop_start
        fps = self.fps_spin.value()
        resolution = RESOLUTION_PRESETS[self.resolution_combo.currentText()]
        # Use smaller resolution for preview (max 480p)
        scale = min(1.0, 480 / resolution[1])
        preview_width = int(resolution[0] * scale)
        preview_height = int(resolution[1] * scale)

        try:
            # Load audio
            self._preview_audio, self._preview_sr = librosa.load(
                str(self.filepath),
                sr=22050,
                offset=self.loop_start,
                duration=duration,
                mono=True,
            )

            # Build config for renderer
            layers_config = {
                "waveform": self.waveform_check.isChecked(),
                "text": self.text_check.isChecked(),
                "dynamics": self.dynamics_check.isChecked(),
                "vjing": self.vjing_check.isChecked(),
                "video_background": self.video_bg_check.isChecked(),
            }

            waveform_config = {
                "height_ratio": self.context.config.video_exporter.waveform_height_ratio,
                "bass_color": self.context.config.video_exporter.waveform_bass_color,
                "mid_color": self.context.config.video_exporter.waveform_mid_color,
                "treble_color": self.context.config.video_exporter.waveform_treble_color,
                "cursor_color": self.context.config.video_exporter.waveform_cursor_color,
            }

            # Create renderer
            self._preview_renderer = FrameRenderer(
                width=preview_width,
                height=preview_height,
                fps=fps,
                audio=self._preview_audio,
                sr=self._preview_sr,
                duration=duration,
                layers_config=layers_config,
                track_metadata=self.track_metadata,
                video_clips_folder=self.video_folder_edit.text(),
                vjing_mappings={
                    m.letter: m.get_effects()
                    for m in self.context.config.video_exporter.vjing_mappings
                },
                vjing_preset=self.vjing_preset_combo.currentData(),
                vjing_presets={
                    p.name: p.effects
                    for p in self.context.config.video_exporter.vjing_presets
                },
                waveform_config=waveform_config,
                use_gpu=True,  # GPU shaders now support dynamic palettes
                effect_intensities=self._get_effect_intensities(),
                color_palette=self.color_palette_combo.currentData(),
                audio_sensitivity=self._get_audio_sensitivity(),
                transitions_enabled=self.transitions_check.isChecked(),
            )

            # Update UI
            total_frames = int(duration * fps)
            self.preview_time_slider.setRange(0, total_frames - 1)
            self.preview_time_slider.setValue(0)
            self.preview_duration_label.setText(f"{duration:.1f}s")
            self._preview_frame = 0

            # Enable controls
            self.preview_play_btn.setEnabled(True)
            self.preview_refresh_btn.setEnabled(True)
            self.preview_load_btn.setEnabled(True)
            self.preview_load_btn.setText("Reload")
            self.preview_info_label.setText(
                f"Preview ready: {preview_width}x{preview_height} @ {fps}fps"
            )

            # Render first frame
            self._refresh_preview_frame()

        except Exception as e:
            logging.exception("[Export Dialog] Preview load failed")
            self.preview_info_label.setText(f"Error: {e}")
            self.preview_label.setText("Failed to load preview")
            self.preview_load_btn.setEnabled(True)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change - stop preview playback when leaving Preview tab."""
        # Preview tab is at index 2
        if index != 2 and self._preview_playing:
            self._preview_timer.stop()
            self._vlc_player.stop()
            self._preview_playing = False
            self.preview_play_btn.setText("Play")

    def _on_preview_time_changed(self, value: int) -> None:
        """Handle preview time slider change."""
        if self._preview_renderer is None:
            return

        self._preview_frame = value
        fps = self.fps_spin.value()
        time_pos = value / fps
        self.preview_time_label.setText(f"{time_pos:.1f}s")

        # Reposition local VLC player if playing
        if self._preview_playing:
            position_ms = int((self.loop_start + time_pos) * 1000)
            self._vlc_player.set_time(position_ms)

        # Only refresh if not playing (to avoid double rendering)
        if not self._preview_playing:
            self._refresh_preview_frame()

    def _toggle_preview_playback(self) -> None:
        """Toggle preview playback."""
        if self._preview_playing:
            # Stop
            self._preview_timer.stop()
            self._preview_playing = False
            self.preview_play_btn.setText("Play")
            # Pause local VLC player
            self._vlc_player.pause()
        else:
            # Start
            fps = self.fps_spin.value()
            interval = int(1000 / fps)  # milliseconds per frame

            # Load audio file in local VLC player
            media = self._vlc_instance.media_new(str(self.filepath))
            self._vlc_player.set_media(media)
            self._vlc_player.play()
            # Wait a bit for player to initialize, then seek
            preview_time = self._preview_frame / fps
            position_ms = int((self.loop_start + preview_time) * 1000)
            QTimer.singleShot(50, lambda: self._vlc_player.set_time(position_ms))

            self._preview_timer.start(interval)
            self._preview_playing = True
            self.preview_play_btn.setText("Pause")

    def _update_preview_frame(self) -> None:
        """Update preview frame (called by timer)."""
        if self._preview_renderer is None:
            return

        # Advance frame
        self._preview_frame += 1
        max_frame = self.preview_time_slider.maximum()
        if self._preview_frame > max_frame:
            self._preview_frame = 0  # Loop
            # Reposition local VLC player to loop start
            self._vlc_player.set_time(int(self.loop_start * 1000))

        # Update slider (without triggering refresh)
        self.preview_time_slider.blockSignals(True)
        self.preview_time_slider.setValue(self._preview_frame)
        self.preview_time_slider.blockSignals(False)

        # Update time label
        fps = self.fps_spin.value()
        time_pos = self._preview_frame / fps
        self.preview_time_label.setText(f"{time_pos:.1f}s")

        # Render frame
        self._refresh_preview_frame()

    def _refresh_preview_frame(self) -> None:
        """Render and display the current preview frame."""
        if self._preview_renderer is None:
            return

        try:
            fps = self.fps_spin.value()
            time_pos = self._preview_frame / fps

            # Render frame
            frame = self._preview_renderer.render_frame(self._preview_frame, time_pos)

            # Convert numpy array to QPixmap
            height, width, channels = frame.shape
            bytes_per_line = channels * width
            qimage = QImage(
                frame.data, width, height, bytes_per_line, QImage.Format_RGB888
            )
            pixmap = QPixmap.fromImage(qimage)

            # Display
            self.preview_label.setPixmap(pixmap)

        except Exception as e:
            logging.warning(f"[Export Dialog] Preview render failed: {e}")

    def _preview_single_effect(self, effect_id: str, effect_name: str) -> None:
        """Open a preview dialog for a single effect.

        Args:
            effect_id: Effect identifier (e.g., "fractal", "plasma").
            effect_name: Display name of the effect.
        """
        # Get current settings
        intensity = self.effect_intensity_sliders[effect_id].value() / 100.0
        color_palette = self.color_palette_combo.currentData()
        audio_sensitivity = self._get_audio_sensitivity()

        # Create and show the effect preview dialog
        dialog = EffectPreviewDialog(
            parent=self,
            context=self.context,
            effect_id=effect_id,
            effect_name=effect_name,
            filepath=self.filepath,
            loop_start=self.loop_start,
            loop_end=self.loop_end,
            intensity=intensity,
            color_palette=color_palette,
            audio_sensitivity=audio_sensitivity,
            track_metadata=self.track_metadata,
        )
        dialog.exec()

    def _get_effect_intensities(self) -> dict[str, float]:
        """Build effect intensities dictionary from UI sliders.

        Returns:
            Dictionary of effect_name -> intensity (0.0-1.0).
            Only includes effects with non-default intensities.
        """
        global_intensity = self.global_intensity_slider.value() / 100.0
        intensities: dict[str, float] = {}

        for effect_id, slider in self.effect_intensity_sliders.items():
            effect_intensity = slider.value() / 100.0
            # Only include if different from global
            if abs(effect_intensity - global_intensity) > 0.01:
                intensities[effect_id] = effect_intensity

        # Set global intensity for all effects not explicitly set
        # This is handled by VJingLayer using self.intensity as default
        # We store it as "_global" key for reference
        intensities["_global"] = global_intensity

        return intensities

    def _get_audio_sensitivity(self) -> dict[str, float]:
        """Build audio sensitivity dictionary from UI sliders.

        Returns:
            Dictionary of band_name -> sensitivity (0.0-2.0).
        """
        return {
            band_id: slider.value() / 100.0
            for band_id, slider in self.audio_sensitivity_sliders.items()
        }

    def _get_export_config(self) -> dict[str, Any]:
        """Get export configuration from UI.

        Returns:
            Export configuration dictionary.
        """
        resolution = RESOLUTION_PRESETS[self.resolution_combo.currentText()]

        return {
            "filepath": self.filepath,
            "loop_start": self.loop_start,
            "loop_end": self.loop_end,
            "width": resolution[0],
            "height": resolution[1],
            "fps": self.fps_spin.value(),
            "output_path": Path(self.output_dir_edit.text()) / self.filename_edit.text(),
            "track_metadata": self.track_metadata,
            "layers": {
                "waveform": self.waveform_check.isChecked(),
                "text": self.text_check.isChecked(),
                "dynamics": self.dynamics_check.isChecked(),
                "vjing": self.vjing_check.isChecked(),
                "video_background": self.video_bg_check.isChecked(),
            },
            "video_clips_folder": self.video_folder_edit.text(),
            "vjing_mappings": {
                m.letter: m.get_effects()
                for m in self.context.config.video_exporter.vjing_mappings
            },
            "vjing_preset": self.vjing_preset_combo.currentData(),
            "vjing_presets": {
                p.name: p.effects
                for p in self.context.config.video_exporter.vjing_presets
            },
            "color_palette": self.color_palette_combo.currentData(),
            # Waveform layer settings
            "waveform_height_ratio": self.context.config.video_exporter.waveform_height_ratio,
            "waveform_bass_color": self.context.config.video_exporter.waveform_bass_color,
            "waveform_mid_color": self.context.config.video_exporter.waveform_mid_color,
            "waveform_treble_color": self.context.config.video_exporter.waveform_treble_color,
            "waveform_cursor_color": self.context.config.video_exporter.waveform_cursor_color,
            # Effect intensities
            "effect_intensities": self._get_effect_intensities(),
            # Audio sensitivity
            "audio_sensitivity": self._get_audio_sensitivity(),
            # Transitions
            "transitions_enabled": self.transitions_check.isChecked(),
        }

    def closeEvent(self, event: Any) -> None:
        """Clean up resources when dialog is closed."""
        # Stop preview timer
        if self._preview_timer.isActive():
            self._preview_timer.stop()
        # Stop and release local VLC player
        self._vlc_player.stop()
        self._vlc_player.release()
        self._vlc_instance.release()
        # Clear preview renderer
        self._preview_renderer = None
        self._preview_audio = None
        super().closeEvent(event)

    def _start_export(self) -> None:
        """Start the video export process."""
        # Stop preview playback
        if self._preview_timer.isActive():
            self._preview_timer.stop()
        self._vlc_player.stop()
        self._preview_playing = False
        self.preview_play_btn.setText("Play")

        config = self._get_export_config()

        # Validate output directory
        output_dir = Path(self.output_dir_edit.text())
        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logging.error(f"[Video Exporter] Cannot create output directory: {e}")
                self.context.emit(
                    Events.STATUS_MESSAGE,
                    message=f"Cannot create output directory: {e}",
                    color="#FF0000",
                )
                return

        # Show progress
        self.progress_widget.setVisible(True)
        self.export_button.setEnabled(False)
        self.progress_label.setText("Starting export...")

        # Import and create worker
        from plugins.video_exporter.export_worker import VideoExportWorker

        self.worker = VideoExportWorker(config, self.context)
        self.worker.progress.connect(self._on_progress)
        self.worker.status.connect(self._on_status)
        self.worker.finished.connect(self._on_export_finished)
        self.worker.error.connect(self._on_export_error)
        self.worker.start()

    def _on_progress(self, value: int) -> None:
        """Handle progress update.

        Args:
            value: Progress percentage (0-100).
        """
        self.progress_bar.setValue(value)

    def _on_status(self, message: str) -> None:
        """Handle status update.

        Args:
            message: Status message.
        """
        self.progress_label.setText(message)

    def _on_export_finished(self, output_path: str) -> None:
        """Handle export completion.

        Args:
            output_path: Path to the exported video file.
        """
        self.context.emit(
            Events.STATUS_MESSAGE,
            message=f"Video exported: {output_path}",
            color="#00FF00",
        )
        logging.info(f"[Video Exporter] Export complete: {output_path}")
        self.accept()

    def _on_export_error(self, error: str) -> None:
        """Handle export error.

        Args:
            error: Error message.
        """
        self.context.emit(
            Events.STATUS_MESSAGE,
            message=f"Export failed: {error}",
            color="#FF0000",
        )
        logging.error(f"[Video Exporter] Export error: {error}")
        self.progress_label.setText(f"Error: {error}")
        self.export_button.setEnabled(True)

    def _on_cancel(self) -> None:
        """Handle cancel button click."""
        # Stop preview playback
        if self._preview_timer.isActive():
            self._preview_timer.stop()
        self._vlc_player.stop()

        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()
        self.reject()
