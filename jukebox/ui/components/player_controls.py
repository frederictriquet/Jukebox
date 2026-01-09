"""Player control widgets."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QWidget

from jukebox.ui.components.clickable_slider import ClickableSlider


class PlayerControls(QWidget):
    """Playback control widgets."""

    play_clicked = Signal()
    pause_clicked = Signal()
    stop_clicked = Signal()
    volume_changed = Signal(int)
    position_changed = Signal(float)

    def __init__(self, parent=None):  # type: ignore
        """Initialize player controls.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        layout = QHBoxLayout()

        # Playback buttons
        self.play_btn = QPushButton("▶")
        self.pause_btn = QPushButton("⏸")
        self.stop_btn = QPushButton("⏹")

        self.play_btn.setToolTip("Play (Space)")
        self.pause_btn.setToolTip("Pause (Ctrl+P)")
        self.stop_btn.setToolTip("Stop (Ctrl+S)")

        self.play_btn.clicked.connect(self.play_clicked.emit)
        self.pause_btn.clicked.connect(self.pause_clicked.emit)
        self.stop_btn.clicked.connect(self.stop_clicked.emit)

        layout.addWidget(self.play_btn)
        layout.addWidget(self.pause_btn)
        layout.addWidget(self.stop_btn)

        # Position slider
        layout.addWidget(QLabel("Position:"))
        self.position_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.sliderMoved.connect(
            lambda val: self.position_changed.emit(val / 1000.0)
        )
        layout.addWidget(self.position_slider)

        # Volume slider
        layout.addWidget(QLabel("Volume:"))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setMaximumWidth(150)
        self.volume_slider.valueChanged.connect(self.volume_changed.emit)
        layout.addWidget(self.volume_slider)

        self.setLayout(layout)

    def set_position(self, position: float) -> None:
        """Update position slider (0.0-1.0).

        Args:
            position: Position in track (0.0 to 1.0)
        """
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(int(position * 1000))
        self.position_slider.blockSignals(False)

    def set_volume(self, volume: int) -> None:
        """Update volume slider (0-100).

        Args:
            volume: Volume level (0 to 100)
        """
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(volume)
        self.volume_slider.blockSignals(False)
