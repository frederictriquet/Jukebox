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


def test_three_playlist_buttons_right_aligned_in_order(qapp) -> None:  # type: ignore[no-untyped-def]
    """Les 3 boutons playlist sont ferrés à droite et dans l'ordre cohérent."""
    plugin, layout = _make_plugin(qapp)

    stretch_idx = _stretch_index(layout)
    idx1 = _widget_index(layout, plugin.playlist_btn)
    idx2 = _widget_index(layout, plugin.playlist_btn_2)
    idx3 = _widget_index(layout, plugin.playlist_btn_3)

    # Tous après le stretch (ferrés à droite).
    assert stretch_idx >= 0
    assert idx1 > stretch_idx
    # Ordre cohérent : 1re (plus récente) → 2e → 3e, de gauche à droite.
    assert idx1 < idx2 < idx3


def test_playlist_buttons_disabled_and_hidden_initially(qapp) -> None:  # type: ignore[no-untyped-def]
    """Sans playlist récente, les 3 boutons sont désactivés et masqués."""
    plugin, _ = _make_plugin(qapp)

    for btn in (plugin.playlist_btn, plugin.playlist_btn_2, plugin.playlist_btn_3):
        assert btn.isEnabled() is False
        assert btn.isHidden() is True


def test_recent_playlists_populate_buttons_in_order(qapp) -> None:  # type: ignore[no-untyped-def]
    """Les playlists récentes alimentent les boutons, plus récente en premier."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")

    plugin._on_track_added_to_playlist(1, "Alpha")
    # Un seul slot rempli : seul le 1er bouton est actif.
    assert plugin.playlist_btn.isEnabled() is True
    assert plugin.playlist_btn.text() == "→ Alpha"
    assert plugin.playlist_btn_2.isEnabled() is False
    assert plugin.playlist_btn_3.isEnabled() is False

    plugin._on_track_added_to_playlist(2, "Beta")
    plugin._on_track_added_to_playlist(3, "Gamma")
    # Plus récente en tête : Gamma, Beta, Alpha.
    assert plugin.playlist_btn.text() == "→ Gamma"
    assert plugin.playlist_btn_2.text() == "→ Beta"
    assert plugin.playlist_btn_3.text() == "→ Alpha"
    assert plugin._recent_playlists == [(3, "Gamma"), (2, "Beta"), (1, "Alpha")]


def test_recent_playlists_dedup_and_cap(qapp) -> None:  # type: ignore[no-untyped-def]
    """Une playlist réutilisée remonte en tête sans doublon, liste plafonnée à 3."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")

    for pid, name in [(1, "Alpha"), (2, "Beta"), (3, "Gamma")]:
        plugin._on_track_added_to_playlist(pid, name)
    # Réutilisation d'Alpha : elle remonte en tête, pas de doublon.
    plugin._on_track_added_to_playlist(1, "Alpha")
    assert plugin._recent_playlists == [(1, "Alpha"), (3, "Gamma"), (2, "Beta")]

    # Nouvelle playlist : la plus ancienne (Beta) est évincée, cap à 3.
    plugin._on_track_added_to_playlist(4, "Delta")
    assert plugin._recent_playlists == [(4, "Delta"), (1, "Alpha"), (3, "Gamma")]


def test_copy_to_recent_playlist_targets_correct_id(qapp) -> None:  # type: ignore[no-untyped-def]
    """Chaque bouton copie le morceau courant vers la bonne playlist."""
    plugin, _ = _make_plugin(qapp)
    plugin.context.player.current_file = "/music/song.mp3"

    plugin._on_track_added_to_playlist(10, "First")
    plugin._on_track_added_to_playlist(20, "Second")
    plugin._on_track_added_to_playlist(30, "Third")

    add = plugin.context.app._on_add_to_playlist

    plugin._on_copy_to_recent_playlist(0)
    add.assert_called_with("/music/song.mp3", 30)
    plugin._on_copy_to_recent_playlist(1)
    add.assert_called_with("/music/song.mp3", 20)
    plugin._on_copy_to_recent_playlist(2)
    add.assert_called_with("/music/song.mp3", 10)


def test_copy_to_empty_slot_is_noop(qapp) -> None:  # type: ignore[no-untyped-def]
    """Cliquer un slot sans playlist associée ne déclenche aucune copie."""
    plugin, _ = _make_plugin(qapp)
    plugin.context.player.current_file = "/music/song.mp3"

    plugin._on_track_added_to_playlist(10, "First")
    add = plugin.context.app._on_add_to_playlist
    add.reset_mock()

    plugin._on_copy_to_recent_playlist(1)
    add.assert_not_called()


def test_buttons_visibility_follows_mode(qapp) -> None:  # type: ignore[no-untyped-def]
    """La visibilité des boutons suit l'activation/désactivation du mode jukebox."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")
    plugin._on_track_added_to_playlist(1, "Alpha")

    assert plugin.playlist_btn.isHidden() is False

    plugin.deactivate("jukebox")
    assert plugin.playlist_btn.isHidden() is True
