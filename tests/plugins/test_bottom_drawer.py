"""Tests for BottomDrawer widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from plugins.cue_maker.widgets.bottom_drawer import BottomDrawer

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication
    from pytestqt.qtbot import QtBot


def test_bottom_drawer_creation(qapp: QApplication) -> None:
    """Test that BottomDrawer can be created."""
    drawer = BottomDrawer()
    assert drawer is not None
    assert not drawer.is_open


def test_bottom_drawer_set_content(qapp: QApplication) -> None:
    """Test setting content widget."""
    drawer = BottomDrawer()
    content = QWidget()
    drawer.set_content(content)

    assert drawer._content is not None
    assert content.maximumHeight() == 0


def test_bottom_drawer_toggle(qapp: QApplication, qtbot: QtBot) -> None:
    """Test toggling the drawer open/closed."""
    drawer = BottomDrawer()
    content = QWidget()
    content.setMinimumHeight(100)
    drawer.set_content(content)
    qtbot.addWidget(drawer)

    # Initially closed
    assert not drawer.is_open
    assert content.maximumHeight() == 0

    # Toggle open
    drawer.toggle()
    qtbot.wait(250)  # Wait for animation
    assert drawer.is_open
    assert content.maximumHeight() == BottomDrawer.OPEN_HEIGHT

    # Toggle closed
    drawer.toggle()
    qtbot.wait(250)  # Wait for animation
    assert not drawer.is_open
    assert content.maximumHeight() == 0


def test_bottom_drawer_handle_button(qapp: QApplication, qtbot: QtBot) -> None:
    """Test that handle button is visible and clickable."""
    drawer = BottomDrawer()
    content = QWidget()
    content.setMinimumHeight(100)
    drawer.set_content(content)
    qtbot.addWidget(drawer)
    drawer.show()

    # Check handle exists and has correct height
    assert drawer._handle is not None
    assert drawer._handle.height() == BottomDrawer.HANDLE_HEIGHT
    assert "▲" in drawer._handle.text()
    assert "Library" in drawer._handle.text()

    # Click handle to toggle
    drawer._handle.click()
    qtbot.wait(250)  # Wait for animation
    assert drawer.is_open
    assert "▼" in drawer._handle.text()
    assert "Library" in drawer._handle.text()

    drawer._handle.click()
    qtbot.wait(250)  # Wait for animation
    assert not drawer.is_open
    assert "▲" in drawer._handle.text()
    assert "Library" in drawer._handle.text()


def test_bottom_drawer_open_height(qapp: QApplication) -> None:
    """Test that OPEN_HEIGHT is set correctly."""
    assert BottomDrawer.OPEN_HEIGHT == 350
