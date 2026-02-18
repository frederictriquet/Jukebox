"""Tests for cue maker widget."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pytest
from PySide6.QtWidgets import QMessageBox

from plugins.cue_maker.model import CueEntry, EntryStatus
from plugins.cue_maker.widgets.cue_maker_widget import CueMakerWidget


@pytest.fixture
def mock_context():  # type: ignore
    """Create mock plugin context."""
    context = Mock()
    context.config = Mock()
    context.config.shazamix_db_path = "/fake/db.db"
    context.get_current_track_duration.return_value = 0.0
    return context


@pytest.fixture(autouse=True)
def _no_waveform_worker(monkeypatch):  # type: ignore
    """Prevent waveform worker from starting in tests."""
    monkeypatch.setattr(
        "plugins.cue_maker.widgets.cue_maker_widget.CueMakerWidget._start_waveform_generation",
        lambda self, filepath: None,
    )


class TestCueMakerWidget:
    """Test CueMakerWidget class."""

    def test_initialization(self, qapp, mock_context) -> None:  # type: ignore
        """Test widget initializes correctly."""
        widget = CueMakerWidget(mock_context)

        assert widget.context == mock_context
        assert widget.model is not None
        assert widget.table_view is not None
        assert widget.progress_bar is not None
        assert widget._selected_row == -1

    def test_ui_elements_exist(self, qapp, mock_context) -> None:  # type: ignore
        """Test all major UI elements are created."""
        widget = CueMakerWidget(mock_context)

        # Mix controls
        assert widget.mix_path_label is not None
        assert widget.load_btn is not None
        assert widget.analyze_btn is not None
        assert widget.add_entry_btn is not None
        assert widget.export_btn is not None

        # Entry editor
        assert widget.time_input is not None
        assert widget.artist_input is not None
        assert widget.title_input is not None
        assert widget.delete_btn is not None

    def test_initial_state(self, qapp, mock_context) -> None:  # type: ignore
        """Test widget initial state."""
        widget = CueMakerWidget(mock_context)

        # Analyze button disabled until mix loaded
        assert widget.analyze_btn.isEnabled() is False

        # Export button disabled until confirmed entries
        assert widget.export_btn.isEnabled() is False

        # Editor disabled until row selected
        assert widget.time_input.isEnabled() is False
        assert widget.artist_input.isEnabled() is False
        assert widget.title_input.isEnabled() is False

    def test_mix_load_requested_signal(self, qapp, qtbot, mock_context) -> None:  # type: ignore
        """Test mix_load_requested signal emitted on file selection."""
        widget = CueMakerWidget(mock_context)

        with patch(
            "plugins.cue_maker.widgets.cue_maker_widget.QFileDialog.getOpenFileName"
        ) as mock_dialog:
            mock_dialog.return_value = ("/fake/path/mix.mp3", "")

            with qtbot.waitSignal(widget.mix_load_requested, timeout=1000) as blocker:
                widget._on_load_mix()

            assert blocker.args[0] == "/fake/path/mix.mp3"

    def test_mix_load_updates_ui(self, qapp, mock_context) -> None:  # type: ignore
        """Test loading mix updates UI state."""
        widget = CueMakerWidget(mock_context)

        with patch(
            "plugins.cue_maker.widgets.cue_maker_widget.QFileDialog.getOpenFileName"
        ) as mock_dialog:
            mock_dialog.return_value = ("/path/to/mix.mp3", "")
            widget._on_load_mix()

        assert "mix.mp3" in widget.mix_path_label.text()
        assert widget.analyze_btn.isEnabled() is True
        assert widget.model.sheet.mix_filepath == "/path/to/mix.mp3"

    def test_analyze_requested_signal(self, qapp, qtbot, mock_context) -> None:  # type: ignore
        """Test analyze_requested signal emitted."""
        widget = CueMakerWidget(mock_context)

        # Enable analyze button
        widget.analyze_btn.setEnabled(True)

        with qtbot.waitSignal(widget.analyze_requested, timeout=1000):
            widget.analyze_btn.click()

    def test_on_analysis_complete(self, qapp, mock_context) -> None:  # type: ignore
        """Test on_analysis_complete loads entries into model."""
        widget = CueMakerWidget(mock_context)

        entries = [
            CueEntry(30000, "Artist 1", "Title 1", 0.9, 180000),
            CueEntry(60000, "Artist 2", "Title 2", 0.85, 120000),
        ]

        widget.on_analysis_complete(entries)

        assert widget.model.rowCount() == 2
        assert widget.progress_bar.isVisible() is False
        assert widget.analyze_btn.isEnabled() is True

    def test_on_analysis_error(self, qapp, mock_context) -> None:  # type: ignore
        """Test on_analysis_error shows error dialog."""
        widget = CueMakerWidget(mock_context)

        with patch.object(QMessageBox, "critical") as mock_msgbox:
            widget.on_analysis_error("Test error message")

            mock_msgbox.assert_called_once()
            args = mock_msgbox.call_args[0]
            assert "Test error message" in args[2]

    def test_set_analysis_progress(self, qapp, mock_context) -> None:  # type: ignore
        """Test set_analysis_progress updates progress bar."""
        widget = CueMakerWidget(mock_context)
        widget.show()

        widget.set_analysis_progress(50, 100, "Processing")

        assert widget.progress_bar.isVisible() is True
        assert widget.progress_bar.value() == 50
        assert widget.progress_bar.maximum() == 100

    def test_add_manual_entry(self, qapp, mock_context) -> None:  # type: ignore
        """Test _on_add_manual_entry adds entry to model."""
        widget = CueMakerWidget(mock_context)

        widget._on_add_manual_entry()

        assert widget.model.rowCount() == 1
        entry = widget.model.get_entry(0)
        assert entry is not None
        assert entry.status == EntryStatus.MANUAL

    def test_row_selection_enables_editor(self, qapp, mock_context) -> None:  # type: ignore
        """Test selecting row enables editor fields."""
        widget = CueMakerWidget(mock_context)
        widget.model.load_entries([CueEntry(60000, "Artist", "Title", 0.9, 180000)])

        # Simulate row selection
        idx = widget.model.index(0, 0)
        widget._on_row_selected(idx, Mock())

        assert widget.time_input.isEnabled() is True
        assert widget.artist_input.isEnabled() is True
        assert widget.title_input.isEnabled() is True
        assert widget.time_input.text() == "01:00"
        assert widget.artist_input.text() == "Artist"
        assert widget.title_input.text() == "Title"

    def test_row_deselection_disables_editor(self, qapp, mock_context) -> None:  # type: ignore
        """Test deselecting row disables editor fields."""
        widget = CueMakerWidget(mock_context)
        widget.model.load_entries([CueEntry(60000, "Artist", "Title", 0.9, 180000)])

        # Select then deselect
        idx = widget.model.index(0, 0)
        widget._on_row_selected(idx, Mock())
        assert widget.time_input.isEnabled() is True

        invalid_idx = Mock()
        invalid_idx.isValid.return_value = False
        widget._on_row_selected(invalid_idx, Mock())

        assert widget.time_input.isEnabled() is False
        assert widget.artist_input.isEnabled() is False

    def test_time_edited_updates_model(self, qapp, mock_context) -> None:  # type: ignore
        """Test _on_time_edited updates entry time."""
        widget = CueMakerWidget(mock_context)
        widget.model.load_entries([CueEntry(60000, "A", "T", 0.9, 180000)])

        # Select row
        widget._selected_row = 0
        widget.time_input.setText("02:30")
        widget._on_time_edited()

        assert widget.model.sheet.entries[0].start_time_ms == 150000

    def test_artist_edited_updates_model(self, qapp, mock_context) -> None:  # type: ignore
        """Test _on_artist_edited updates entry artist."""
        widget = CueMakerWidget(mock_context)
        widget.model.load_entries([CueEntry(60000, "Old", "T", 0.9, 180000)])

        widget._selected_row = 0
        widget.artist_input.setText("New Artist")
        widget._on_artist_edited()

        assert widget.model.sheet.entries[0].artist == "New Artist"

    def test_title_edited_updates_model(self, qapp, mock_context) -> None:  # type: ignore
        """Test _on_title_edited updates entry title."""
        widget = CueMakerWidget(mock_context)
        widget.model.load_entries([CueEntry(60000, "A", "Old", 0.9, 180000)])

        widget._selected_row = 0
        widget.title_input.setText("New Title")
        widget._on_title_edited()

        assert widget.model.sheet.entries[0].title == "New Title"

    def test_delete_entry(self, qapp, mock_context) -> None:  # type: ignore
        """Test _on_delete_entry removes entry."""
        widget = CueMakerWidget(mock_context)
        widget.model.load_entries(
            [
                CueEntry(30000, "A1", "T1", 0.9, 180000),
                CueEntry(60000, "A2", "T2", 0.9, 180000),
            ]
        )

        widget._selected_row = 0
        widget._on_delete_entry()

        assert widget.model.rowCount() == 1
        assert widget.model.sheet.entries[0].artist == "A2"

    def test_export_with_no_entries(self, qapp, mock_context) -> None:  # type: ignore
        """Test _on_export warns when no entries exist."""
        widget = CueMakerWidget(mock_context)

        with patch.object(QMessageBox, "warning") as mock_msgbox:
            widget._on_export()

            mock_msgbox.assert_called_once()
            args = mock_msgbox.call_args[0]
            assert "No entries" in args[2]

    def test_export_with_confirmed_entries(self, qapp, mock_context) -> None:  # type: ignore
        """Test _on_export creates CUE file."""
        widget = CueMakerWidget(mock_context)
        widget.model.set_metadata("/path/to/mix.mp3", "Mix", "DJ")

        entry = CueEntry(0, "Artist", "Title", 1.0, 180000)
        widget.model.load_entries([entry])

        with TemporaryDirectory() as tmpdir:
            output_path = str(Path(tmpdir) / "test.cue")

            with patch(
                "plugins.cue_maker.widgets.cue_maker_widget.QFileDialog.getSaveFileName"
            ) as mock_dialog:
                mock_dialog.return_value = (output_path, "")

                with patch.object(QMessageBox, "information") as mock_msgbox:
                    widget._on_export()

                    # Should show success message
                    mock_msgbox.assert_called_once()

            # Verify file was created
            assert Path(output_path).exists()

    def test_export_button_enabled_state(self, qapp, mock_context) -> None:  # type: ignore
        """Test export button enables when entries exist."""
        widget = CueMakerWidget(mock_context)

        # Initially disabled (no entries)
        assert widget.export_btn.isEnabled() is False

        # Load entry
        entry = CueEntry(60000, "A", "T", 0.9, 180000)
        widget.model.load_entries([entry])
        widget._update_export_button()
        assert widget.export_btn.isEnabled() is True

    def test_table_view_configuration(self, qapp, mock_context) -> None:  # type: ignore
        """Test table view is properly configured."""
        widget = CueMakerWidget(mock_context)

        assert widget.table_view.model() == widget.model
        assert widget.table_view.alternatingRowColors() is False
        assert widget.table_view.showGrid() is False
