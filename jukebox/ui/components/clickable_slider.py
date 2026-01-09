"""Clickable slider that seeks on click."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider


class ClickableSlider(QSlider):
    """Slider that jumps to click position."""

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Handle mouse press - jump to clicked position."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Calculate value from click position
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            groove = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self
            )

            if self.orientation() == Qt.Orientation.Horizontal:
                slider_length = groove.width()
                slider_min = groove.x()
                pos = event.position().x()
            else:
                slider_length = groove.height()
                slider_min = groove.y()
                pos = event.position().y()

            # Calculate new value
            value = int(
                self.minimum()
                + (self.maximum() - self.minimum()) * (pos - slider_min) / slider_length
            )

            self.setValue(value)
            self.sliderMoved.emit(value)

        super().mousePressEvent(event)
