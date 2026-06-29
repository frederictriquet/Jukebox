"""Tests for the loop player plugin UI placement."""

import logging
from unittest.mock import Mock

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from jukebox.ui.components.player_controls import PlayerControls
from plugins.loop_player import PLAYLIST_BUTTON_COUNT, LoopPlayerPlugin


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


def _make_plugin_without_stretch(qapp):  # type: ignore[no-untyped-def]
    """Construit le plugin sur une barre de contrôles dépourvue de ressort."""
    controls = QWidget()
    layout = QHBoxLayout()
    layout.addWidget(QPushButton("a"))
    layout.addWidget(QPushButton("b"))
    controls.setLayout(layout)

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
    playlist_idx = _widget_index(layout, plugin._playlist_buttons[0])
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

    playlist_idx = _widget_index(layout, plugin._playlist_buttons[0])
    timer_idx = _widget_index(layout, timer_widget)

    assert playlist_idx < timer_idx


def test_three_playlist_buttons_right_aligned_in_order(qapp) -> None:  # type: ignore[no-untyped-def]
    """Les 3 boutons playlist sont ferrés à droite et dans l'ordre cohérent."""
    plugin, layout = _make_plugin(qapp)

    stretch_idx = _stretch_index(layout)
    idx1 = _widget_index(layout, plugin._playlist_buttons[0])
    idx2 = _widget_index(layout, plugin._playlist_buttons[1])
    idx3 = _widget_index(layout, plugin._playlist_buttons[2])

    # Tous après le stretch (ferrés à droite).
    assert stretch_idx >= 0
    assert idx1 > stretch_idx
    # Ordre cohérent : 1re (plus récente) → 2e → 3e, de gauche à droite.
    assert idx1 < idx2 < idx3


def test_playlist_buttons_disabled_and_hidden_initially(qapp) -> None:  # type: ignore[no-untyped-def]
    """Sans playlist récente, les 3 boutons sont désactivés et masqués."""
    plugin, _ = _make_plugin(qapp)

    assert len(plugin._playlist_buttons) == 3
    for btn in plugin._playlist_buttons:
        assert btn.isEnabled() is False
        assert btn.isHidden() is True


def test_recent_playlists_populate_buttons_in_order(qapp) -> None:  # type: ignore[no-untyped-def]
    """Les playlists récentes alimentent les boutons, plus récente en premier."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")

    plugin._on_track_added_to_playlist(1, "Alpha")
    # Un seul slot rempli : seul le 1er bouton est actif.
    assert plugin._playlist_buttons[0].isEnabled() is True
    assert plugin._playlist_buttons[0].text() == "→ Alpha"
    assert plugin._playlist_buttons[1].isEnabled() is False
    assert plugin._playlist_buttons[2].isEnabled() is False

    plugin._on_track_added_to_playlist(2, "Beta")
    plugin._on_track_added_to_playlist(3, "Gamma")
    # Plus récente en tête : Gamma, Beta, Alpha.
    assert plugin._playlist_buttons[0].text() == "→ Gamma"
    assert plugin._playlist_buttons[1].text() == "→ Beta"
    assert plugin._playlist_buttons[2].text() == "→ Alpha"
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

    assert plugin._playlist_buttons[0].isHidden() is False

    plugin.deactivate("jukebox")
    assert plugin._playlist_buttons[0].isHidden() is True


def test_buttons_created_without_stretch(qapp) -> None:  # type: ignore[no-untyped-def]
    """Sans ressort dans la barre, les boutons sont quand même créés et ajoutés.

    Garantit que les handlers ne lèvent pas d'AttributeError faute de boutons.
    """
    plugin, layout = _make_plugin_without_stretch(qapp)

    assert _stretch_index(layout) == -1
    assert len(plugin._playlist_buttons) == PLAYLIST_BUTTON_COUNT
    # Loop + 3 boutons playlist ajoutés à la fin (ordre cohérent).
    assert _widget_index(layout, plugin.loop_button) >= 0
    idx = [_widget_index(layout, btn) for btn in plugin._playlist_buttons]
    assert all(i >= 0 for i in idx)
    assert idx == sorted(idx)


def test_handlers_safe_without_stretch(qapp) -> None:  # type: ignore[no-untyped-def]
    """Les handlers fonctionnent sans ressort (pas d'AttributeError)."""
    plugin, _ = _make_plugin_without_stretch(qapp)
    plugin.activate("jukebox")
    plugin.context.player.current_file = "/music/song.mp3"

    plugin._on_track_added_to_playlist(7, "Solo")
    assert plugin._playlist_buttons[0].text() == "→ Solo"

    plugin._on_copy_to_recent_playlist(0)
    plugin.context.app._on_add_to_playlist.assert_called_with("/music/song.mp3", 7)


def test_recent_playlists_capped_to_button_count(qapp) -> None:  # type: ignore[no-untyped-def]
    """La liste des playlists récentes est plafonnée à PLAYLIST_BUTTON_COUNT."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")

    for pid in range(1, PLAYLIST_BUTTON_COUNT + 3):
        plugin._on_track_added_to_playlist(pid, f"P{pid}")

    assert len(plugin._recent_playlists) == PLAYLIST_BUTTON_COUNT


def test_deleted_playlist_dropped_on_change(qapp) -> None:  # type: ignore[no-untyped-def]
    """Une playlist supprimée est retirée des raccourcis sur PLAYLIST_CHANGED."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")

    plugin._on_track_added_to_playlist(1, "Alpha")
    plugin._on_track_added_to_playlist(2, "Beta")
    plugin._on_track_added_to_playlist(3, "Gamma")

    # Beta (id 2) a été supprimée en base.
    plugin.context.database.conn = object()
    plugin.context.database.playlists.get_all.return_value = [
        {"id": 3, "name": "Gamma"},
        {"id": 1, "name": "Alpha"},
    ]
    plugin._on_playlists_changed()

    assert plugin._recent_playlists == [(3, "Gamma"), (1, "Alpha")]
    assert plugin._playlist_buttons[0].text() == "→ Gamma"
    assert plugin._playlist_buttons[1].text() == "→ Alpha"
    # Le 3e slot, désormais vide, est désactivé.
    assert plugin._playlist_buttons[2].isEnabled() is False


def test_renamed_playlist_relabeled_on_change(qapp) -> None:  # type: ignore[no-untyped-def]
    """Une playlist renommée voit son libellé mis à jour sur PLAYLIST_CHANGED."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")

    plugin._on_track_added_to_playlist(1, "Alpha")
    plugin._on_track_added_to_playlist(2, "Beta")

    # Beta (id 2) a été renommée en « Bravo », l'ordre de récence est conservé.
    plugin.context.database.conn = object()
    plugin.context.database.playlists.get_all.return_value = [
        {"id": 1, "name": "Alpha"},
        {"id": 2, "name": "Bravo"},
    ]
    plugin._on_playlists_changed()

    assert plugin._recent_playlists == [(2, "Bravo"), (1, "Alpha")]
    assert plugin._playlist_buttons[0].text() == "→ Bravo"


def test_playlists_changed_noop_when_db_disconnected(qapp) -> None:  # type: ignore[no-untyped-def]
    """Sans connexion DB, le rafraîchissement n'altère pas l'état courant."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")
    plugin._on_track_added_to_playlist(1, "Alpha")

    plugin.context.database.conn = None
    plugin._on_playlists_changed()

    # État inchangé : pas d'appel à get_all, raccourci conservé.
    plugin.context.database.playlists.get_all.assert_not_called()
    assert plugin._recent_playlists == [(1, "Alpha")]


def test_playlists_changed_handles_get_all_error(qapp, caplog) -> None:  # type: ignore[no-untyped-def]
    """Si get_all() lève, le handler logue l'erreur sans planter ni altérer l'état."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")
    plugin._on_track_added_to_playlist(1, "Alpha")
    plugin._on_track_added_to_playlist(2, "Beta")

    # get_all échoue (ex. erreur SQLite) alors que la connexion est établie.
    plugin.context.database.conn = object()
    plugin.context.database.playlists.get_all.side_effect = RuntimeError("DB boom")

    with caplog.at_level(logging.ERROR, logger="plugins.loop_player"):
        plugin._on_playlists_changed()  # ne doit pas propager

    # L'erreur est loguée (pas avalée silencieusement) avec sa trace d'exception.
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert error_records, "aucune erreur loguée"
    assert any("rafraîchissement" in r.getMessage() for r in error_records)
    assert any(r.exc_info is not None for r in error_records)
    # L'état des raccourcis reste cohérent (inchangé).
    assert plugin._recent_playlists == [(2, "Beta"), (1, "Alpha")]
    assert plugin._playlist_buttons[0].text() == "→ Beta"
    assert plugin._playlist_buttons[1].text() == "→ Alpha"
    assert plugin._playlist_buttons[0].isEnabled() is True
    assert plugin._playlist_buttons[1].isEnabled() is True


def test_long_playlist_name_is_elided(qapp) -> None:  # type: ignore[no-untyped-def]
    """Un nom de playlist trop long est tronqué avec une ellipse dans le libellé."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")

    long_name = "Une playlist au nom interminable qui dépasse largement"
    plugin._on_track_added_to_playlist(1, long_name)

    btn = plugin._playlist_buttons[0]
    # Le libellé est tronqué (ellipse) mais le nom complet reste dans l'info-bulle.
    assert "…" in btn.text()
    assert btn.text() != f"→ {long_name}"
    assert long_name in btn.toolTip()
