"""Export configuration dialog for video exporter plugin."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
from PySide6.QtCore import Qt

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

        self.setWindowTitle("Export Video")
        self.setMinimumWidth(500)
        self.setMinimumHeight(520)

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
        intensity_group.setMinimumHeight(320)  # Ensure enough height for all sliders
        intensity_layout = QGridLayout(intensity_group)
        intensity_layout.setContentsMargins(12, 20, 12, 12)
        intensity_layout.setVerticalSpacing(8)
        intensity_layout.setColumnStretch(1, 1)  # Slider column stretches
        intensity_layout.setColumnMinimumWidth(0, 80)  # Label column min width
        intensity_layout.setColumnMinimumWidth(2, 40)  # Percentage column min width

        row = 0

        # Global intensity slider
        global_label = QLabel("Global:")
        global_label.setFixedHeight(28)
        self.global_intensity_slider = QSlider(Qt.Horizontal)
        self.global_intensity_slider.setRange(0, 100)
        self.global_intensity_slider.setValue(70)
        self.global_intensity_slider.setMinimumWidth(150)
        self.global_intensity_slider.setFixedHeight(28)
        self.global_intensity_slider.setToolTip("Default intensity for all effects")
        self.global_intensity_label = QLabel("70%")
        self.global_intensity_label.setMinimumWidth(40)
        self.global_intensity_label.setFixedHeight(28)
        self.global_intensity_slider.valueChanged.connect(
            lambda v: self.global_intensity_label.setText(f"{v}%")
        )
        intensity_layout.addWidget(global_label, row, 0)
        intensity_layout.addWidget(self.global_intensity_slider, row, 1)
        intensity_layout.addWidget(self.global_intensity_label, row, 2)
        row += 1

        # Per-effect intensity sliders (main GPU effects)
        self.effect_intensity_sliders: dict[str, QSlider] = {}
        self.effect_intensity_labels: dict[str, QLabel] = {}

        gpu_effects = [
            ("fractal", "Fractal"),
            ("plasma", "Plasma"),
            ("wormhole", "Wormhole"),
            ("voronoi", "Voronoi"),
            ("metaballs", "Metaballs"),
            ("fire", "Fire"),
            ("smoke", "Smoke"),
        ]

        for effect_id, effect_name in gpu_effects:
            name_label = QLabel(f"{effect_name}:")
            name_label.setFixedHeight(28)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(70)
            slider.setMinimumWidth(150)
            slider.setFixedHeight(28)
            slider.setToolTip(f"Intensity for {effect_name} effect")
            value_label = QLabel("70%")
            value_label.setMinimumWidth(40)
            value_label.setFixedHeight(28)
            slider.valueChanged.connect(
                lambda v, lbl=value_label: lbl.setText(f"{v}%")
            )
            intensity_layout.addWidget(name_label, row, 0)
            intensity_layout.addWidget(slider, row, 1)
            intensity_layout.addWidget(value_label, row, 2)
            self.effect_intensity_sliders[effect_id] = slider
            self.effect_intensity_labels[effect_id] = value_label
            row += 1

        layout.addWidget(intensity_group)
        layout.addStretch()

        scroll.setWidget(content)
        self.tabs.addTab(scroll, "Layers")

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
            # Waveform layer settings
            "waveform_height_ratio": self.context.config.video_exporter.waveform_height_ratio,
            "waveform_bass_color": self.context.config.video_exporter.waveform_bass_color,
            "waveform_mid_color": self.context.config.video_exporter.waveform_mid_color,
            "waveform_treble_color": self.context.config.video_exporter.waveform_treble_color,
            "waveform_cursor_color": self.context.config.video_exporter.waveform_cursor_color,
            # Effect intensities
            "effect_intensities": self._get_effect_intensities(),
        }

    def _start_export(self) -> None:
        """Start the video export process."""
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
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()
        self.reject()
