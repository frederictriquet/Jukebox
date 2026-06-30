"""Tests for BottomDrawer widget.

Le drawer s'ouvre/ferme via une ``QPropertyAnimation`` (200 ms). Les tests
attendent l'état final via ``qtbot.waitUntil`` (polling de la propriété cible)
plutôt qu'un ``qtbot.wait(250)`` à durée fixe : ce dernier ne laissait que ~50 ms
de marge sur l'animation et échouait de façon intermittente en suite complète,
quand la boucle d'évènements partagée (QApplication session) est sous charge —
d'où la dépendance à l'ordre d'exécution.

La fixture ``drawer`` stoppe en teardown toute animation encore active et purge
les suppressions différées, pour qu'aucun timer/objet ne fuite vers les tests
suivants (QUnifiedTimer est global au thread).
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
