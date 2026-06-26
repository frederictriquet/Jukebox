"""Tests for the loop player plugin UI placement."""

from unittest.mock import Mock

from PySide6.QtWidgets import QLabel

from jukebox.ui.components.player_controls import PlayerControls
from plugins.loop_player import LoopPlayerPlugin


class _FakeUIBuilder:
    """UIBuilder minimal : insère réellement dans le layout, mock le reste."""

    def __init__(self, main_window) -> None:  # type: ignore[no-untyped-def]
        self.main_window = main_window

    def insert_widget_in_layout(self, layout, index, widget) -> None:  # type: ignore[no-untyped-def]
        layout.insertWidget(index, widget)

    def get_or_create_menu(self, name):  # type: ignore[no-untyped-def]
        return Mock()

    def add_menu_separator(self, menu) -> None:  # type: ignore[no-untyped-def]
        ...

    def add_menu_action(self, *args, **kwargs) -> None: ...


def _stretch_index(layout) -> int:  # type: ignore[no-untyped-def]
    """Retourne l'index du spacer (stretch) dans le layout."""
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item and item.spacerItem():
            return i
    return -1


def _widget_index(layout, widget) -> int:  # type: ignore[no-untyped-def]
    """Retourne l'index d'un widget donné dans le layout."""
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item and item.widget() is widget:
            return i
    return -1


def _make_plugin(qapp):  # type: ignore[no-untyped-def]
    """Construit le plugin enregistré sur des PlayerControls réels."""
    controls = PlayerControls()
    main_window = Mock()
    main_window.controls = controls

    context = Mock()
    context.app = main_window
    context.config.loop_player.duration = 10.0

    plugin = LoopPlayerPlugin()
    plugin.context = context
    plugin.register_ui(_FakeUIBuilder(main_window))
    return plugin, controls.layout()


def test_playlist_button_is_right_aligned(qapp) -> None:  # type: ignore[no-untyped-def]
    """Le bouton playlist doit être ferré à droite (après le stretch)."""
    plugin, layout = _make_plugin(qapp)

    stretch_idx = _stretch_index(layout)
    playlist_idx = _widget_index(layout, plugin.playlist_btn)
    loop_idx = _widget_index(layout, plugin.loop_button)

    assert stretch_idx >= 0
    # Le bouton loop reste à gauche, le bouton playlist passe à droite du stretch.
    assert loop_idx < stretch_idx
    assert playlist_idx > stretch_idx


def test_playlist_button_before_timer(qapp) -> None:  # type: ignore[no-untyped-def]
    """Le bouton playlist se place juste avant le timer de replay.

    On simule l'insertion ultérieure du widget timer (comme track_info, juste
    avant le label Volume) et on vérifie que le bouton playlist le précède.
    """
    plugin, layout = _make_plugin(qapp)

    # Localise le label "Volume:" pour insérer le timer juste avant, comme le
    # ferait le plugin track_info chargé après loop_player.
    volume_label_idx = -1
    for i in range(layout.count()):
        item = layout.itemAt(i)
        widget = item.widget() if item else None
        if isinstance(widget, QLabel) and widget.text() == "Volume:":
            volume_label_idx = i
            break
    assert volume_label_idx >= 0

    timer_widget = QLabel("00:00 / 00:00")
    layout.insertWidget(volume_label_idx, timer_widget)

    playlist_idx = _widget_index(layout, plugin.playlist_btn)
    timer_idx = _widget_index(layout, timer_widget)

    assert playlist_idx < timer_idx
