"""Tests for BottomDrawer widget.

The drawer opens/closes via a ``QPropertyAnimation`` (200 ms). The tests wait
for the final state via ``qtbot.waitUntil`` (polling the target property)
rather than a fixed-duration ``qtbot.wait(250)``: the latter left only ~50 ms
of margin on the animation and failed intermittently in the full suite, when
the shared event loop (QApplication session) is under load — hence the
dependency on execution order.

The ``drawer`` fixture stops any still-active animation at teardown and flushes
deferred deletions, so that no timer/object leaks into subsequent tests
(QUnifiedTimer is thread-global).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtWidgets import QWidget

from plugins.cue_maker.widgets.bottom_drawer import BottomDrawer

if TYPE_CHECKING:
    from collections.abc import Iterator

    from PySide6.QtWidgets import QApplication
    from pytestqt.qtbot import QtBot


@pytest.fixture
def drawer(qapp: QApplication, qtbot: QtBot) -> Iterator[BottomDrawer]:
    """Provide a BottomDrawer with deterministic teardown (state isolation)."""
    widget = BottomDrawer()
    qtbot.addWidget(widget)
    yield widget
    # Stop any in-flight animation so it does not keep ticking the
    # thread-global QUnifiedTimer and perturb later tests' timing.
    if widget._anim is not None:
        widget._anim.stop()
    # Flush deferred deletions so leaked C++ objects don't accumulate.
    qapp.processEvents()


def test_bottom_drawer_creation(drawer: BottomDrawer) -> None:
    """Test that BottomDrawer can be created."""
    assert drawer is not None
    assert not drawer.is_open


def test_bottom_drawer_set_content(drawer: BottomDrawer) -> None:
    """Test setting content widget."""
    content = QWidget()
    drawer.set_content(content)

    assert drawer._content is not None
    assert content.maximumHeight() == 0


def test_bottom_drawer_toggle(drawer: BottomDrawer, qtbot: QtBot) -> None:
    """Test toggling the drawer open/closed."""
    content = QWidget()
    content.setMinimumHeight(100)
    drawer.set_content(content)

    # Initially closed
    assert not drawer.is_open
    assert content.maximumHeight() == 0

    # Toggle open — wait for the animation to actually reach its end value.
    drawer.toggle()
    assert drawer.is_open
    qtbot.waitUntil(lambda: content.maximumHeight() == BottomDrawer.OPEN_HEIGHT, timeout=2000)

    # Toggle closed
    drawer.toggle()
    assert not drawer.is_open
    qtbot.waitUntil(lambda: content.maximumHeight() == 0, timeout=2000)


def test_bottom_drawer_handle_button(drawer: BottomDrawer, qtbot: QtBot) -> None:
    """Test that handle button is visible and clickable."""
    content = QWidget()
    content.setMinimumHeight(100)
    drawer.set_content(content)
    drawer.show()

    # Check handle exists and has correct height
    assert drawer._handle is not None
    assert drawer._handle.height() == BottomDrawer.HANDLE_HEIGHT
    assert "▲" in drawer._handle.text()
    assert "Library" in drawer._handle.text()

    # Click handle to toggle
    drawer._handle.click()
    qtbot.waitUntil(lambda: content.maximumHeight() == BottomDrawer.OPEN_HEIGHT, timeout=2000)
    assert drawer.is_open
    assert "▼" in drawer._handle.text()
    assert "Library" in drawer._handle.text()

    drawer._handle.click()
    qtbot.waitUntil(lambda: content.maximumHeight() == 0, timeout=2000)
    assert not drawer.is_open
    assert "▲" in drawer._handle.text()
    assert "Library" in drawer._handle.text()


def test_bottom_drawer_open_height() -> None:
    """Test that OPEN_HEIGHT is set correctly."""
    assert BottomDrawer.OPEN_HEIGHT == 350
