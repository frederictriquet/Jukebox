"""Tests for the loop player plugin UI placement."""

import logging
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from jukebox.ui.components.player_controls import PlayerControls
from plugins.loop_player import PLAYLIST_BUTTON_COUNT, LoopPlayerPlugin


class _FakeUIBuilder:
    """Minimal UIBuilder: actually inserts into the layout, mocks the rest."""

    def __init__(self, main_window) -> None:  # type: ignore[no-untyped-def]
        self.main_window = main_window

    def insert_widget_in_layout(self, layout, index, widget) -> None:  # type: ignore[no-untyped-def]
        layout.insertWidget(index, widget)

    def get_or_create_menu(self, name):  # type: ignore[no-untyped-def]
        return Mock()

    def add_menu_separator(self, menu) -> None:  # type: ignore[no-untyped-def]
        ...

    def add_menu_action(self, *args, **kwargs) -> None: ...  # type: ignore[no-untyped-def]


def _stretch_index(layout) -> int:  # type: ignore[no-untyped-def]
    """Return the index of the spacer (stretch) in the layout."""
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item and item.spacerItem():
            return i
    return -1


def _widget_index(layout, widget) -> int:  # type: ignore[no-untyped-def]
    """Return the index of a given widget in the layout."""
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item and item.widget() is widget:
            return i
    return -1


def _make_plugin(qapp):  # type: ignore[no-untyped-def]
    """Build the plugin registered on real PlayerControls."""
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
    """Build the plugin on a controls bar that has no stretch."""
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
    """The playlist button must be right-aligned (after the stretch)."""
    plugin, layout = _make_plugin(qapp)

    stretch_idx = _stretch_index(layout)
    playlist_idx = _widget_index(layout, plugin._playlist_buttons[0])
    loop_idx = _widget_index(layout, plugin.loop_button)

    assert stretch_idx >= 0
    # The loop button stays on the left, the playlist button goes to the right of the stretch.
    assert loop_idx < stretch_idx
    assert playlist_idx > stretch_idx


def test_playlist_button_before_timer(qapp) -> None:  # type: ignore[no-untyped-def]
    """The playlist button is placed just before the replay timer.

    We simulate the later insertion of the timer widget (like track_info, just
    before the Volume label) and verify that the playlist button precedes it.
    """
    plugin, layout = _make_plugin(qapp)

    # Locate the "Volume:" label to insert the timer just before it, as the
    # track_info plugin loaded after loop_player would do.
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
    """The 3 playlist buttons are right-aligned and in consistent order."""
    plugin, layout = _make_plugin(qapp)

    stretch_idx = _stretch_index(layout)
    idx1 = _widget_index(layout, plugin._playlist_buttons[0])
    idx2 = _widget_index(layout, plugin._playlist_buttons[1])
    idx3 = _widget_index(layout, plugin._playlist_buttons[2])

    # All after the stretch (right-aligned).
    assert stretch_idx >= 0
    assert idx1 > stretch_idx
    # Consistent order: 1st (most recent) → 2nd → 3rd, left to right.
    assert idx1 < idx2 < idx3


def test_playlist_buttons_disabled_and_hidden_initially(qapp) -> None:  # type: ignore[no-untyped-def]
    """With no recent playlist, the 3 buttons are disabled and hidden."""
    plugin, _ = _make_plugin(qapp)

    assert len(plugin._playlist_buttons) == 3
    for btn in plugin._playlist_buttons:
        assert btn.isEnabled() is False
        assert btn.isHidden() is True


def test_recent_playlists_populate_buttons_in_order(qapp) -> None:  # type: ignore[no-untyped-def]
    """Recent playlists populate the buttons, most recent first."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")

    plugin._on_track_added_to_playlist(1, "Alpha")
    # Only one slot filled: only the 1st button is enabled.
    assert plugin._playlist_buttons[0].isEnabled() is True
    assert plugin._playlist_buttons[0].text() == "→ Alpha"
    assert plugin._playlist_buttons[1].isEnabled() is False
    assert plugin._playlist_buttons[2].isEnabled() is False

    plugin._on_track_added_to_playlist(2, "Beta")
    plugin._on_track_added_to_playlist(3, "Gamma")
    # Most recent at the top: Gamma, Beta, Alpha.
    assert plugin._playlist_buttons[0].text() == "→ Gamma"
    assert plugin._playlist_buttons[1].text() == "→ Beta"
    assert plugin._playlist_buttons[2].text() == "→ Alpha"
    assert plugin._recent_playlists == [(3, "Gamma"), (2, "Beta"), (1, "Alpha")]


def test_recent_playlists_dedup_and_cap(qapp) -> None:  # type: ignore[no-untyped-def]
    """A reused playlist moves back to the top without duplicate, list capped at 3."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")

    for pid, name in [(1, "Alpha"), (2, "Beta"), (3, "Gamma")]:
        plugin._on_track_added_to_playlist(pid, name)
    # Reusing Alpha: it moves back to the top, no duplicate.
    plugin._on_track_added_to_playlist(1, "Alpha")
    assert plugin._recent_playlists == [(1, "Alpha"), (3, "Gamma"), (2, "Beta")]

    # New playlist: the oldest (Beta) is evicted, cap at 3.
    plugin._on_track_added_to_playlist(4, "Delta")
    assert plugin._recent_playlists == [(4, "Delta"), (1, "Alpha"), (3, "Gamma")]


def test_copy_to_recent_playlist_targets_correct_id(qapp) -> None:  # type: ignore[no-untyped-def]
    """Each button copies the current track to the right playlist."""
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
    """Clicking a slot with no associated playlist triggers no copy."""
    plugin, _ = _make_plugin(qapp)
    plugin.context.player.current_file = "/music/song.mp3"

    plugin._on_track_added_to_playlist(10, "First")
    add = plugin.context.app._on_add_to_playlist
    add.reset_mock()

    plugin._on_copy_to_recent_playlist(1)
    add.assert_not_called()


def test_buttons_visibility_follows_mode(qapp) -> None:  # type: ignore[no-untyped-def]
    """Button visibility follows the activation/deactivation of jukebox mode."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")
    plugin._on_track_added_to_playlist(1, "Alpha")

    assert plugin._playlist_buttons[0].isHidden() is False

    plugin.deactivate("jukebox")
    assert plugin._playlist_buttons[0].isHidden() is True


def test_buttons_created_without_stretch(qapp) -> None:  # type: ignore[no-untyped-def]
    """With no stretch in the bar, the buttons are still created and added.

    Guarantees that the handlers do not raise AttributeError due to missing buttons.
    """
    plugin, layout = _make_plugin_without_stretch(qapp)

    assert _stretch_index(layout) == -1
    assert len(plugin._playlist_buttons) == PLAYLIST_BUTTON_COUNT
    # Loop + 3 playlist buttons added at the end (consistent order).
    assert _widget_index(layout, plugin.loop_button) >= 0
    idx = [_widget_index(layout, btn) for btn in plugin._playlist_buttons]
    assert all(i >= 0 for i in idx)
    assert idx == sorted(idx)


def test_handlers_safe_without_stretch(qapp) -> None:  # type: ignore[no-untyped-def]
    """The handlers work without a stretch (no AttributeError)."""
    plugin, _ = _make_plugin_without_stretch(qapp)
    plugin.activate("jukebox")
    plugin.context.player.current_file = "/music/song.mp3"

    plugin._on_track_added_to_playlist(7, "Solo")
    assert plugin._playlist_buttons[0].text() == "→ Solo"

    plugin._on_copy_to_recent_playlist(0)
    plugin.context.app._on_add_to_playlist.assert_called_with("/music/song.mp3", 7)


def test_recent_playlists_capped_to_button_count(qapp) -> None:  # type: ignore[no-untyped-def]
    """The recent playlists list is capped at PLAYLIST_BUTTON_COUNT."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")

    for pid in range(1, PLAYLIST_BUTTON_COUNT + 3):
        plugin._on_track_added_to_playlist(pid, f"P{pid}")

    assert len(plugin._recent_playlists) == PLAYLIST_BUTTON_COUNT


def test_deleted_playlist_dropped_on_change(qapp) -> None:  # type: ignore[no-untyped-def]
    """A deleted playlist is removed from the shortcuts on PLAYLIST_CHANGED."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")

    plugin._on_track_added_to_playlist(1, "Alpha")
    plugin._on_track_added_to_playlist(2, "Beta")
    plugin._on_track_added_to_playlist(3, "Gamma")

    # Beta (id 2) was deleted from the database.
    plugin.context.database.conn = object()
    plugin.context.database.playlists.get_all.return_value = [
        {"id": 3, "name": "Gamma"},
        {"id": 1, "name": "Alpha"},
    ]
    plugin._on_playlists_changed()

    assert plugin._recent_playlists == [(3, "Gamma"), (1, "Alpha")]
    assert plugin._playlist_buttons[0].text() == "→ Gamma"
    assert plugin._playlist_buttons[1].text() == "→ Alpha"
    # The 3rd slot, now empty, is disabled.
    assert plugin._playlist_buttons[2].isEnabled() is False


def test_renamed_playlist_relabeled_on_change(qapp) -> None:  # type: ignore[no-untyped-def]
    """A renamed playlist has its label updated on PLAYLIST_CHANGED."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")

    plugin._on_track_added_to_playlist(1, "Alpha")
    plugin._on_track_added_to_playlist(2, "Beta")

    # Beta (id 2) was renamed to "Bravo", the recency order is preserved.
    plugin.context.database.conn = object()
    plugin.context.database.playlists.get_all.return_value = [
        {"id": 1, "name": "Alpha"},
        {"id": 2, "name": "Bravo"},
    ]
    plugin._on_playlists_changed()

    assert plugin._recent_playlists == [(2, "Bravo"), (1, "Alpha")]
    assert plugin._playlist_buttons[0].text() == "→ Bravo"


def test_playlists_changed_noop_when_db_disconnected(qapp) -> None:  # type: ignore[no-untyped-def]
    """With no DB connection, the refresh does not alter the current state."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")
    plugin._on_track_added_to_playlist(1, "Alpha")

    plugin.context.database.conn = None
    plugin._on_playlists_changed()

    # State unchanged: no call to get_all, shortcut preserved.
    plugin.context.database.playlists.get_all.assert_not_called()
    assert plugin._recent_playlists == [(1, "Alpha")]


def test_playlists_changed_handles_get_all_error(qapp, caplog) -> None:  # type: ignore[no-untyped-def]
    """If get_all() raises, the handler logs the error without crashing or altering state."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")
    plugin._on_track_added_to_playlist(1, "Alpha")
    plugin._on_track_added_to_playlist(2, "Beta")

    # get_all fails (e.g. SQLite error) while the connection is established.
    plugin.context.database.conn = object()
    plugin.context.database.playlists.get_all.side_effect = RuntimeError("DB boom")

    with caplog.at_level(logging.ERROR, logger="plugins.loop_player"):
        plugin._on_playlists_changed()  # must not propagate

    # The error is logged (not silently swallowed) with its exception traceback.
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert error_records, "aucune erreur loguée"
    assert any("rafraîchissement" in r.getMessage() for r in error_records)
    assert any(r.exc_info is not None for r in error_records)
    # The shortcut state remains consistent (unchanged).
    assert plugin._recent_playlists == [(2, "Beta"), (1, "Alpha")]
    assert plugin._playlist_buttons[0].text() == "→ Beta"
    assert plugin._playlist_buttons[1].text() == "→ Alpha"
    assert plugin._playlist_buttons[0].isEnabled() is True
    assert plugin._playlist_buttons[1].isEnabled() is True


def test_add_to_playlist_refreshes_buttons_once(qapp) -> None:  # type: ignore[no-untyped-def]
    """A mutation (PLAYLIST_CHANGED + TRACK_ADDED_TO_PLAYLIST) refreshes only once.

    Reproduces the emission order of MainWindow._on_add_to_playlist: a single add
    triggers both events, but the buttons and get_all() must only be invoked
    once (no double refresh and no redundant DB query).
    """
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")
    # Seed a recent playlist (the bump does not call get_all()).
    plugin._on_track_added_to_playlist(1, "Alpha")

    plugin.context.database.conn = object()
    plugin.context.database.playlists.get_all.return_value = [{"id": 1, "name": "Alpha"}]
    plugin.context.database.playlists.get_all.reset_mock()

    with patch.object(
        plugin, "_refresh_playlist_buttons", wraps=plugin._refresh_playlist_buttons
    ) as refresh_spy:
        # Real order: PLAYLIST_CHANGED then TRACK_ADDED_TO_PLAYLIST.
        plugin._on_playlists_changed()
        plugin._on_track_added_to_playlist(1, "Alpha")

    assert refresh_spy.call_count == 1
    assert plugin.context.database.playlists.get_all.call_count == 1
    # Visible behavior unchanged: the button reflects the recent playlist.
    assert plugin._playlist_buttons[0].text() == "→ Alpha"
    assert plugin._recent_playlists == [(1, "Alpha")]


def test_long_playlist_name_is_elided(qapp) -> None:  # type: ignore[no-untyped-def]
    """A playlist name that is too long is truncated with an ellipsis in the label."""
    plugin, _ = _make_plugin(qapp)
    plugin.activate("jukebox")

    long_name = "Une playlist au nom interminable qui dépasse largement"
    plugin._on_track_added_to_playlist(1, long_name)

    btn = plugin._playlist_buttons[0]
    # The label is truncated (ellipsis) but the full name remains in the tooltip.
    assert "…" in btn.text()
    assert btn.text() != f"→ {long_name}"
    assert long_name in btn.toolTip()
