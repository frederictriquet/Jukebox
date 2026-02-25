"""Player control widgets."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from jukebox.ui.components.clickable_slider import ClickableSlider


class PlayerControls(QWidget):
    """Playback control widgets."""

    play_pause_clicked = Signal()
    stop_clicked = Signal()
    volume_changed = Signal(int)

    def __init__(self, parent=None, *, play_pause_shortcut: str = "Space", stop_shortcut: str = "Ctrl+S"):  # type: ignore
        """Initialize player controls.

        Args:
            parent: Parent widget
            play_pause_shortcut: Keyboard shortcut text for play/pause
            stop_shortcut: Keyboard shortcut text for stop
        """
        super().__init__(parent)
        self._is_playing = False
        self._play_pause_shortcut = play_pause_shortcut
        self._stop_shortcut = stop_shortcut
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        layout = QHBoxLayout()

        # Playback buttons
        self.play_btn = QPushButton("▶")
        self.stop_btn = QPushButton("⏹")

        self.play_btn.setToolTip(f"Play/Pause ({self._play_pause_shortcut})")
        self.stop_btn.setToolTip(f"Stop ({self._stop_shortcut})")

        self.play_btn.clicked.connect(self.play_pause_clicked.emit)
        self.stop_btn.clicked.connect(self.stop_clicked.emit)

        layout.addWidget(self.play_btn)
        layout.addWidget(self.stop_btn)

        layout.addStretch()

        # Volume slider
        layout.addWidget(QLabel("Volume:"))
        self.volume_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)  # @hardcoded-ok: VLC volume range
        self.volume_slider.setValue(70)
        self.volume_slider.setMaximumWidth(150)  # @hardcoded-ok: standard slider width
        self.volume_slider.valueChanged.connect(self.volume_changed.emit)
        layout.addWidget(self.volume_slider)

        self.setLayout(layout)

    def set_playing_state(self, playing: bool) -> None:
        """Update play button icon based on playback state.

        Args:
            playing: True if currently playing, False otherwise
        """
        self._is_playing = playing
        if playing:
            self.play_btn.setText("⏸")
            self.play_btn.setToolTip(f"Pause ({self._play_pause_shortcut})")
        else:
            self.play_btn.setText("▶")
            self.play_btn.setToolTip(f"Play ({self._play_pause_shortcut})")

    def set_volume(self, volume: int) -> None:
        """Update volume slider (0-100).

        Args:
            volume: Volume level (0 to 100)
        """
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(volume)
        self.volume_slider.blockSignals(False)
