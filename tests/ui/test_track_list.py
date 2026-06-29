"""Tests for track list widget."""

from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSortFilterProxyModel, Qt

from jukebox.core.database import Database
from jukebox.ui.components.track_list import TrackList, TrackListModel


class TestTrackList:
    """Test TrackList widget."""

    def test_initialization(self, qapp):  # type: ignore
        """Test track list initializes correctly."""
        track_list = TrackList()
        assert track_list is not None
        assert track_list.count() == 0

    def test_add_track_without_metadata(self, qapp):  # type: ignore
        """Test adding track without metadata."""
        track_list = TrackList()
        path = Path("/tmp/test.mp3")

        track_list.add_track(path)

        assert track_list.count() == 1
        assert track_list.item(0).text() == "test.mp3"

    def test_add_track_with_metadata(self, qapp):  # type: ignore
        """Test adding track with metadata."""
        track_list = TrackList()
        path = Path("/tmp/test.mp3")

        track_list.add_track(path, "My Song", "My Artist")

        assert track_list.count() == 1
        assert track_list.item(0).text() == "My Artist - My Song"

    def test_add_multiple_tracks(self, qapp):  # type: ignore
        """Test adding multiple tracks."""
        track_list = TrackList()
        paths = [Path(f"/tmp/track{i}.mp3") for i in range(5)]

        track_list.add_tracks(paths)

        assert track_list.count() == 5

    def test_clear_tracks(self, qapp):  # type: ignore
        """Test clearing tracks."""
        track_list = TrackList()
        track_list.add_track(Path("/tmp/test.mp3"))

        track_list.clear_tracks()

        assert track_list.count() == 0

    def test_get_selected_track(self, qapp):  # type: ignore
        """Test getting selected track."""
        track_list = TrackList()
        path = Path("/tmp/test.mp3")
        track_list.add_track(path)

        # Select first item
        track_list.setCurrentRow(0)

        selected = track_list.get_selected_track()
        assert selected == path

    def test_track_model_property(self, qapp):  # type: ignore
        """Test track_model property returns source model."""
        track_list = TrackList()

        # track_model should return TrackListModel directly
        assert track_list.track_model is not None
        assert track_list.track_model == track_list._track_model

    def test_set_proxy_model(self, qapp):  # type: ignore
        """Test set_proxy_model installs proxy between source and view."""
        track_list = TrackList()
        path = Path("/tmp/test.mp3")
        track_list.add_track(path)

        # Create a proxy
        proxy = QSortFilterProxyModel()

        # Install proxy
        track_list.set_proxy_model(proxy)

        # Verify proxy is now the view's model
        assert track_list.model() == proxy
        # Verify proxy's source is the track model
        assert proxy.sourceModel() == track_list.track_model
        # Verify track is still accessible
        assert track_list.count() == 1

    def test_remove_proxy_model(self, qapp):  # type: ignore
        """Test remove_proxy_model restores direct source model."""
        track_list = TrackList()
        path = Path("/tmp/test.mp3")
        track_list.add_track(path)

        # Install then remove proxy
        proxy = QSortFilterProxyModel()
        track_list.set_proxy_model(proxy)
        track_list.remove_proxy_model()

        # Verify source model is now view's model
        assert track_list.model() == track_list.track_model
        assert track_list.count() == 1

    def test_select_track_by_filepath_without_proxy(self, qapp):  # type: ignore
        """Test select_track_by_filepath works without proxy."""
        track_list = TrackList()
        path1 = Path("/tmp/track1.mp3")
        path2 = Path("/tmp/track2.mp3")
        track_list.add_track(path1)
        track_list.add_track(path2)

        # Select second track by filepath
        track_list.select_track_by_filepath(path2)

        # Verify selection
        selected = track_list.get_selected_track()
        assert selected == path2

    def test_select_track_by_filepath_with_proxy(self, qapp):  # type: ignore
        """Test select_track_by_filepath works with proxy model."""
        track_list = TrackList()
        path1 = Path("/tmp/track1.mp3")
        path2 = Path("/tmp/track2.mp3")
        track_list.add_track(path1, genre="H")
        track_list.add_track(path2, genre="W")

        # Install a proxy that filters on genre column
        # In jukebox mode (default): ["waveform", "artist", "title", "genre", ...]
        genre_col = track_list.track_model.cell_renderer.columns.index("genre")
        proxy = QSortFilterProxyModel()
        proxy.setFilterKeyColumn(genre_col)
        proxy.setFilterFixedString("H")
        track_list.set_proxy_model(proxy)

        # Select first track (which passes filter)
        track_list.select_track_by_filepath(path1)

        # Verify selection works through proxy
        selected = track_list.get_selected_track()
        assert selected == path1

    def test_select_track_by_filepath_not_found(self, qapp):  # type: ignore
        """Test select_track_by_filepath handles missing filepath gracefully."""
        track_list = TrackList()
        path1 = Path("/tmp/track1.mp3")
        track_list.add_track(path1)

        # Try to select non-existent track (should not crash)
        track_list.select_track_by_filepath(Path("/tmp/nonexistent.mp3"))

        # No selection should be made
        # (original selection remains, or no selection if none was set)

    def test_count_with_proxy(self, qapp):  # type: ignore
        """Test count() returns filtered count with proxy."""
        track_list = TrackList()
        track_list.add_track(Path("/tmp/track1.mp3"), genre="H")
        track_list.add_track(Path("/tmp/track2.mp3"), genre="W")
        track_list.add_track(Path("/tmp/track3.mp3"), genre="H")

        # Without proxy: 3 tracks
        assert track_list.count() == 3

        # With proxy filtering for "H": 2 tracks
        genre_col = track_list.track_model.cell_renderer.columns.index("genre")
        proxy = QSortFilterProxyModel()
        proxy.setFilterKeyColumn(genre_col)
        proxy.setFilterFixedString("H")
        track_list.set_proxy_model(proxy)

        assert track_list.count() == 2


class TestCommentColumn:
    """Tests for the editable comment column (jukebox mode only)."""

    def test_comment_column_present_in_jukebox_mode(self, qapp):  # type: ignore
        """The comment column exists in jukebox mode."""
        model = TrackListModel(mode="jukebox")
        assert "comment" in model.cell_renderer.columns

    def test_comment_column_absent_in_curating_mode(self, qapp):  # type: ignore
        """The comment column is not shown in curating mode."""
        model = TrackListModel(mode="curating")
        assert "comment" not in model.cell_renderer.columns

    def test_comment_cell_is_editable_in_jukebox_mode(self, qapp):  # type: ignore
        """The comment cell carries the editable flag in jukebox mode."""
        model = TrackListModel(mode="jukebox")
        model.add_track(Path("/tmp/song.mp3"))
        comment_col = model.cell_renderer.columns.index("comment")
        index = model.index(0, comment_col)
        assert bool(model.flags(index) & Qt.ItemFlag.ItemIsEditable)

    def test_other_cells_are_not_editable(self, qapp):  # type: ignore
        """Non-comment cells stay read-only in jukebox mode."""
        model = TrackListModel(mode="jukebox")
        model.add_track(Path("/tmp/song.mp3"))
        artist_col = model.cell_renderer.columns.index("artist")
        index = model.index(0, artist_col)
        assert not (model.flags(index) & Qt.ItemFlag.ItemIsEditable)

    def test_comment_display_from_loaded_track(self, qapp):  # type: ignore
        """A loaded track's comment is shown in the comment column."""
        model = TrackListModel(mode="jukebox")
        model.load_tracks_batch([{"filepath": "/tmp/song.mp3", "comment": "Banger"}])
        comment_col = model.cell_renderer.columns.index("comment")
        index = model.index(0, comment_col)
        assert model.data(index, Qt.ItemDataRole.DisplayRole) == "Banger"
        assert model.data(index, Qt.ItemDataRole.EditRole) == "Banger"

    def _make_model_with_db(self, tmp_path):
        """Build a jukebox-mode model backed by a real DB with one track."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()
        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"fake mp3")
        track_id = db.tracks.add(
            {"filepath": str(audio), "filename": "song.mp3", "title": "Song"},
            mode="jukebox",
        )
        model = TrackListModel(database=db, mode="jukebox")
        model.load_tracks_batch(db.tracks.get_all(mode="jukebox"))
        return db, model, audio, track_id

    def test_set_comment_updates_db_and_tag(self, qapp, tmp_path):  # type: ignore
        """Editing the comment writes to both the database and the file tag."""
        db, model, audio, track_id = self._make_model_with_db(tmp_path)
        comment_col = model.cell_renderer.columns.index("comment")
        index = model.index(0, comment_col)

        with patch("jukebox.utils.tag_writer.save_audio_tags", return_value=True) as mock_save:
            updated = model.setData(index, "Great track", Qt.ItemDataRole.EditRole)

        assert updated is True
        mock_save.assert_called_once_with(str(audio), {"comment": "Great track"})
        db_track = db.tracks.get_by_id(track_id)
        assert db_track is not None
        assert db_track["comment"] == "Great track"
        assert model.data(index, Qt.ItemDataRole.DisplayRole) == "Great track"
        db.close()

    def test_set_comment_no_change_returns_false(self, qapp, tmp_path):  # type: ignore
        """Setting the same comment value is a no-op and skips the tag write."""
        db, model, audio, _ = self._make_model_with_db(tmp_path)
        comment_col = model.cell_renderer.columns.index("comment")
        index = model.index(0, comment_col)

        with patch("jukebox.utils.tag_writer.save_audio_tags", return_value=True) as mock_save:
            # Current comment is empty; setting empty again must be a no-op.
            updated = model.setData(index, "", Qt.ItemDataRole.EditRole)

        assert updated is False
        mock_save.assert_not_called()
        db.close()

    def test_set_comment_tag_failure_leaves_db_unchanged(self, qapp, tmp_path, caplog):  # type: ignore
        """[M32] A failed tag write must NOT touch the DB nor the in-memory model.

        Le tag fichier est écrit en premier : si l'écriture échoue, la base de
        données et le modèle restent inchangés (pas de divergence DB/fichier),
        l'erreur est loguée (pas d'échec silencieux) et setData renvoie False.
        """
        import logging

        db, model, audio, track_id = self._make_model_with_db(tmp_path)
        comment_col = model.cell_renderer.columns.index("comment")
        index = model.index(0, comment_col)

        with (
            patch("jukebox.utils.tag_writer.save_audio_tags", return_value=False),
            caplog.at_level(logging.ERROR),
        ):
            updated = model.setData(index, "With error", Qt.ItemDataRole.EditRole)

        assert updated is False  # Écriture du tag échouée → édition refusée
        db_track = db.tracks.get_by_id(track_id)
        assert db_track is not None
        # La DB ne doit PAS avoir été modifiée.
        assert (db_track["comment"] or "") == ""
        # Le modèle en mémoire ne doit pas non plus refléter la valeur échouée.
        assert (model.tracks[0].get("comment") or "") == ""
        assert any("tag comment" in rec.message for rec in caplog.records)
        db.close()

    def test_set_comment_emits_metadata_updated_event(self, qapp, tmp_path):  # type: ignore
        """A successful inline edit notifies other views via TRACK_METADATA_UPDATED."""
        from jukebox.core.event_bus import EventBus, Events

        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()
        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"fake mp3")
        db.tracks.add(
            {"filepath": str(audio), "filename": "song.mp3", "title": "Song"},
            mode="jukebox",
        )
        event_bus = EventBus()
        model = TrackListModel(database=db, event_bus=event_bus, mode="jukebox")
        model.load_tracks_batch(db.tracks.get_all(mode="jukebox"))
        comment_col = model.cell_renderer.columns.index("comment")
        index = model.index(0, comment_col)

        with (
            patch("jukebox.utils.tag_writer.save_audio_tags", return_value=True),
            patch.object(event_bus, "emit") as mock_emit,
        ):
            updated = model.setData(index, "Nice", Qt.ItemDataRole.EditRole)

        assert updated is True
        assert mock_emit.call_count == 1
        call_args, call_kwargs = mock_emit.call_args
        assert call_args == (Events.TRACK_METADATA_UPDATED,)
        assert str(call_kwargs["filepath"]) == str(audio)
        db.close()

    def test_set_comment_ignored_in_curating_mode(self, qapp):  # type: ignore
        """Comment editing is rejected when the model is in curating mode."""
        # No database: avoids spawning the curating-mode duplicate-check worker.
        model = TrackListModel(mode="curating")
        model.load_tracks_batch([{"filepath": "/tmp/song.mp3"}])
        # Curating has no comment column; editing column 0 must be refused.
        index = model.index(0, 0)
        with patch("jukebox.utils.tag_writer.save_audio_tags", return_value=True) as mock_save:
            updated = model.setData(index, "Nope", Qt.ItemDataRole.EditRole)
        assert updated is False
        mock_save.assert_not_called()

    def test_existing_comment_displayed_via_add_track(self, qapp, tmp_path):  # type: ignore
        """add_track loads a pre-existing comment from the DB (not a blank cell)."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()
        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"fake mp3")
        db.tracks.add(
            {"filepath": str(audio), "filename": "song.mp3", "comment": "Pre-existing"},
            mode="jukebox",
        )
        model = TrackListModel(database=db, mode="jukebox")
        model.add_track(audio)
        comment_col = model.cell_renderer.columns.index("comment")
        index = model.index(0, comment_col)
        assert model.data(index, Qt.ItemDataRole.DisplayRole) == "Pre-existing"
        db.close()

    def test_existing_comment_displayed_after_get_all(self, qapp, tmp_path):  # type: ignore
        """A comment stored in DB shows up when reloading via get_all/load_tracks_batch."""
        db = Database(tmp_path / "test.db")
        db.connect()
        db.initialize_schema()
        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"fake mp3")
        db.tracks.add(
            {"filepath": str(audio), "filename": "song.mp3", "comment": "Loaded"},
            mode="jukebox",
        )
        model = TrackListModel(database=db, mode="jukebox")
        model.load_tracks_batch(db.tracks.get_all(mode="jukebox"))
        comment_col = model.cell_renderer.columns.index("comment")
        index = model.index(0, comment_col)
        assert model.data(index, Qt.ItemDataRole.DisplayRole) == "Loaded"
        db.close()

    def test_set_comment_logs_when_db_row_missing(self, qapp, tmp_path, caplog):  # type: ignore
        """A successful tag write but an unresolved DB id is logged, not swallowed."""
        import logging

        db, model, audio, track_id = self._make_model_with_db(tmp_path)
        # Supprime la ligne en base : l'id n'est plus résolvable.
        db.tracks.delete(track_id)
        model.tracks[0]["_db_id"] = None
        comment_col = model.cell_renderer.columns.index("comment")
        index = model.index(0, comment_col)

        with (
            patch("jukebox.utils.tag_writer.save_audio_tags", return_value=True),
            caplog.at_level(logging.ERROR),
        ):
            updated = model.setData(index, "Orphan", Qt.ItemDataRole.EditRole)

        # Le tag fichier a été écrit : l'édition réussit côté modèle, mais
        # l'impossibilité de persister en base est loguée (pas d'échec silencieux).
        assert updated is True
        assert any("introuvable" in rec.message for rec in caplog.records)
        db.close()

    def test_set_comment_logs_when_db_update_fails(self, qapp, tmp_path, caplog):  # type: ignore
        """update_metadata returning False is logged instead of being ignored."""
        import logging

        db, model, audio, _ = self._make_model_with_db(tmp_path)
        comment_col = model.cell_renderer.columns.index("comment")
        index = model.index(0, comment_col)

        with (
            patch("jukebox.utils.tag_writer.save_audio_tags", return_value=True),
            patch.object(db.tracks, "update_metadata", return_value=False),
            caplog.at_level(logging.ERROR),
        ):
            updated = model.setData(index, "Whatever", Qt.ItemDataRole.EditRole)

        assert updated is True
        assert any("mise à jour du commentaire en base" in rec.message for rec in caplog.records)
        db.close()

    def test_set_comment_rejected_when_filepath_none(self, qapp, caplog):  # type: ignore
        """A row without a filepath cannot persist a comment: edit is refused and logged."""
        import logging

        model = TrackListModel(mode="jukebox")
        # Ligne sans filepath, insérée directement pour ne pas déclencher le
        # background check (qui appellerait Path(None)).
        model.tracks = [{"filepath": None, "comment": ""}]
        comment_col = model.cell_renderer.columns.index("comment")
        index = model.index(0, comment_col)

        with (
            patch("jukebox.utils.tag_writer.save_audio_tags", return_value=True) as mock_save,
            caplog.at_level(logging.ERROR),
        ):
            updated = model.setData(index, "No path", Qt.ItemDataRole.EditRole)

        assert updated is False
        mock_save.assert_not_called()
        assert (model.tracks[0].get("comment") or "") == ""
        assert any("filepath manquant" in rec.message for rec in caplog.records)


class TestCommentColumnSorting:
    """Tests for sorting the comment column (jukebox mode)."""

    def _make_model_with_comments(self, comments):
        """Build a jukebox-mode model loaded with tracks carrying the given comments.

        Each comment is keyed to a unique filepath so the resulting order can be
        read back from the comment values themselves.
        """
        model = TrackListModel(mode="jukebox")
        tracks = [
            {"filepath": f"/tmp/track_{i}.mp3", "comment": comment}
            for i, comment in enumerate(comments)
        ]
        model.load_tracks_batch(tracks)
        return model

    @staticmethod
    def _comments_in_order(model):
        """Return the comment of each row in current model order."""
        return [track.get("comment") or "" for track in model.tracks]

    def test_comment_sort_ascending(self, qapp):  # type: ignore
        """Clicking the comment header sorts by comment, not by date_added."""
        model = self._make_model_with_comments(["charlie", "alpha", "bravo"])
        comment_col = model.cell_renderer.columns.index("comment")

        model.sort(comment_col, Qt.SortOrder.AscendingOrder)

        assert self._comments_in_order(model) == ["alpha", "bravo", "charlie"]

    def test_comment_sort_descending(self, qapp):  # type: ignore
        """Descending order reverses the alphabetical comment order."""
        model = self._make_model_with_comments(["charlie", "alpha", "bravo"])
        comment_col = model.cell_renderer.columns.index("comment")

        model.sort(comment_col, Qt.SortOrder.DescendingOrder)

        assert self._comments_in_order(model) == ["charlie", "bravo", "alpha"]

    def test_comment_sort_is_case_insensitive(self, qapp):  # type: ignore
        """Sorting ignores case (e.g. 'apple' before 'Banana')."""
        model = self._make_model_with_comments(["Banana", "apple", "Cherry"])
        comment_col = model.cell_renderer.columns.index("comment")

        model.sort(comment_col, Qt.SortOrder.AscendingOrder)

        assert self._comments_in_order(model) == ["apple", "Banana", "Cherry"]

    def test_comment_sort_empty_values_last(self, qapp):  # type: ignore
        """Empty comments are grouped at the end in ascending order."""
        model = self._make_model_with_comments(["zulu", "", "alpha", "   "])
        comment_col = model.cell_renderer.columns.index("comment")

        model.sort(comment_col, Qt.SortOrder.AscendingOrder)

        ordered = self._comments_in_order(model)
        # Les deux premiers sont les commentaires non vides, triés alphabétiquement.
        assert ordered[:2] == ["alpha", "zulu"]
        # Les deux derniers sont les commentaires vides (chaîne vide ou blancs).
        assert all(c.strip() == "" for c in ordered[2:])

    def test_comment_sort_toggles_with_order(self, qapp):  # type: ignore
        """Alternating the order produces opposite (non-empty) orderings."""
        model = self._make_model_with_comments(["bravo", "alpha", "charlie"])
        comment_col = model.cell_renderer.columns.index("comment")

        model.sort(comment_col, Qt.SortOrder.AscendingOrder)
        ascending = self._comments_in_order(model)

        model.sort(comment_col, Qt.SortOrder.DescendingOrder)
        descending = self._comments_in_order(model)

        assert ascending == list(reversed(descending))
