"""Tests for cue maker widget."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pytest
from PySide6.QtWidgets import QMessageBox

from plugins.cue_maker.model import CueEntry
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
        assert widget.export_btn is not None

    def test_initial_state(self, qapp, mock_context) -> None:  # type: ignore
        """Test widget initial state."""
        widget = CueMakerWidget(mock_context)

        # Analyze button disabled until mix loaded
        assert widget.analyze_btn.isEnabled() is False

        # Export button disabled until confirmed entries
        assert widget.export_btn.isEnabled() is False

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

    def test_on_waveform_error(self, qapp, mock_context) -> None:  # type: ignore
        """Test _on_waveform_error shows warning dialog and emits status message."""
        widget = CueMakerWidget(mock_context)

        with patch.object(QMessageBox, "warning") as mock_msgbox:
            widget._on_waveform_error("Waveform generation failed: Out of memory")

            # Should show QMessageBox.warning
            mock_msgbox.assert_called_once()
            args = mock_msgbox.call_args[0]
            assert "Waveform generation failed: Out of memory" in args[2]

        # Should also emit status message
        mock_context.emit.assert_called_with(
            "status_message", message="Waveform error: Waveform generation failed: Out of memory"
        )

    def test_set_analysis_progress(self, qapp, mock_context) -> None:  # type: ignore
        """Test set_analysis_progress updates progress bar."""
        widget = CueMakerWidget(mock_context)
        widget.show()

        widget.set_analysis_progress(50, 100, "Processing")

        assert widget.progress_bar.isVisible() is True
        assert widget.progress_bar.value() == 50
        assert widget.progress_bar.maximum() == 100

    def test_export_with_no_entries(self, qapp, mock_context) -> None:  # type: ignore
        """Test _on_export warns when no confirmed entries exist."""
        widget = CueMakerWidget(mock_context)

        with patch.object(QMessageBox, "warning") as mock_msgbox:
            widget._on_export()

            mock_msgbox.assert_called_once()
            args = mock_msgbox.call_args[0]
            assert "No confirmed entries" in args[2]

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

    def test_import_cue_button_exists(self, qapp, mock_context) -> None:  # type: ignore
        """Test import CUE button is created."""
        widget = CueMakerWidget(mock_context)
        assert widget.import_cue_btn is not None
        assert "Import CUE" in widget.import_cue_btn.text()

    def test_import_cue_shows_confirmation_dialog(self, qapp, mock_context) -> None:  # type: ignore
        """Test import CUE shows warning dialog before proceeding."""
        widget = CueMakerWidget(mock_context)

        with (
            patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No),
            patch(
                "plugins.cue_maker.widgets.cue_maker_widget.QFileDialog.getOpenFileName"
            ) as mock_file_dialog,
        ):
            widget._on_import_cue()
            # File dialog should NOT be shown if user cancels
            mock_file_dialog.assert_not_called()

    def test_import_cue_loads_entries_from_file(self, qapp, mock_context) -> None:  # type: ignore
        """Test import CUE parses file and loads entries."""
        widget = CueMakerWidget(mock_context)

        cue_content = """FILE "mix.mp3" MP3
  TRACK 01 AUDIO
    PERFORMER "Artist 1"
    TITLE "Title 1"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    PERFORMER "Artist 2"
    TITLE "Title 2"
    INDEX 01 03:05:00
"""
        with TemporaryDirectory() as tmpdir:
            cue_path = Path(tmpdir) / "test.cue"
            cue_path.write_text(cue_content, encoding="utf-8")

            with (
                patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes),
                patch(
                    "plugins.cue_maker.widgets.cue_maker_widget.QFileDialog.getOpenFileName",
                    return_value=(str(cue_path), ""),
                ),
                patch.object(QMessageBox, "information"),
            ):
                widget._on_import_cue()

            # Verify entries were loaded
            assert widget.model.rowCount() == 2
            entry1 = widget.model.get_entry(0)
            assert entry1 is not None
            assert entry1.artist == "Artist 1"
            assert entry1.title == "Title 1"

    def test_import_cue_handles_parse_error(self, qapp, mock_context) -> None:  # type: ignore
        """Test import CUE shows error dialog on parse failure."""
        widget = CueMakerWidget(mock_context)

        cue_content = "INVALID CUE FILE"
        with TemporaryDirectory() as tmpdir:
            cue_path = Path(tmpdir) / "bad.cue"
            cue_path.write_text(cue_content, encoding="utf-8")

            with (
                patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes),
                patch(
                    "plugins.cue_maker.widgets.cue_maker_widget.QFileDialog.getOpenFileName",
                    return_value=(str(cue_path), ""),
                ),
                patch.object(QMessageBox, "critical") as mock_critical,
            ):
                widget._on_import_cue()
                # Should show error dialog
                mock_critical.assert_called_once()

    def test_load_mix_file_clears_existing_state(self, qapp, mock_context) -> None:  # type: ignore
        """Test loading new mix clears previous cuesheet and state."""
        mock_context.player = Mock()
        mock_context.player.is_playing.return_value = False

        widget = CueMakerWidget(mock_context)

        # Add some entries
        entry1 = CueEntry(0, "Old Artist", "Old Title", 1.0, 60000)
        widget.model.load_entries([entry1])
        widget._selected_row = 0
        widget._mix_duration_s = 180.0

        # Load new mix
        widget._load_mix_file("/path/to/new_mix.mp3")

        # State should be reset
        assert widget.model.rowCount() == 0
        assert widget._selected_row == -1
        assert widget._mix_duration_s == 0.0

    def test_load_mix_file_stops_playback(self, qapp, mock_context) -> None:  # type: ignore
        """Test loading mix stops current playback."""
        mock_context.player = Mock()
        mock_context.player.is_playing.return_value = True

        widget = CueMakerWidget(mock_context)
        widget._is_mix_playing = True

        widget._load_mix_file("/path/to/mix.mp3")

        # Player should be stopped
        mock_context.player.stop.assert_called_once()
        assert widget._is_mix_playing is False

    def test_entry_double_click_seeks_to_start(self, qapp, mock_context) -> None:  # type: ignore
        """Test double-clicking entry seeks to its start time."""
        mock_context.player = Mock()
        mock_context.player.current_file = None
        mock_context.player.is_playing.return_value = False

        widget = CueMakerWidget(mock_context)
        widget.model.set_metadata("/path/to/mix.mp3", "Mix", "")
        widget._mix_duration_s = 600.0  # 10 minutes

        # Add entry at 3 minutes (180s)
        entry = CueEntry(180000, "Artist", "Title", 1.0, 120000)
        widget.model.load_entries([entry])

        # Simulate double-click on row 0
        index = widget.model.index(0, 0)
        widget._on_entry_double_clicked(index)

        # Should load and play mix
        mock_context.player.load.assert_called_once()
        mock_context.player.play.assert_called_once()

    def test_entry_double_click_invalid_index(self, qapp, mock_context) -> None:  # type: ignore
        """Test double-click on invalid index does nothing."""
        mock_context.player = Mock()

        widget = CueMakerWidget(mock_context)

        # Create invalid index
        invalid_index = widget.model.index(99, 0)
        widget._on_entry_double_clicked(invalid_index)

        # Should not crash, player should not be called
        mock_context.player.load.assert_not_called()

    def test_update_region_color_changes_brush(self, qapp, mock_context) -> None:  # type: ignore
        """Test region color changes when cursor enters/exits."""
        widget = CueMakerWidget(mock_context)
        widget.waveform_widget.expected_length = 1000

        # Create a mock region
        mock_region = Mock()
        mock_region.getRegion.return_value = (200, 400)
        widget._highlight_region = mock_region

        # Cursor outside region
        widget._update_region_color(0.1)  # Position 100 (outside 200-400)
        assert widget._cursor_inside_region is False
        assert mock_region.setBrush.called

        # Cursor inside region
        mock_region.setBrush.reset_mock()
        widget._update_region_color(0.3)  # Position 300 (inside 200-400)
        assert widget._cursor_inside_region is True
        assert mock_region.setBrush.called

    def test_update_region_color_no_region(self, qapp, mock_context) -> None:  # type: ignore
        """Test update region color handles missing region gracefully."""
        widget = CueMakerWidget(mock_context)
        widget._highlight_region = None

        # Should not crash
        widget._update_region_color(0.5)
        assert widget._cursor_inside_region is None

    def test_cursor_inside_region_initialized_as_none(self, qapp, mock_context) -> None:  # type: ignore
        """Test cursor inside region tracking is initialized to None."""
        widget = CueMakerWidget(mock_context)
        assert widget._cursor_inside_region is None

    def test_create_waveform_logs_debug_on_config_fallback(
        self, qapp, caplog
    ) -> None:  # type: ignore
        """Test _create_waveform logs debug when waveform config is unavailable."""
        # Create context without waveform config (AttributeError will be raised)
        context = Mock()
        context.config = Mock()
        context.config.shazamix_db_path = "/fake/db.db"
        context.get_current_track_duration.return_value = 0.0
        # Delete waveform attribute to trigger AttributeError
        del context.config.waveform

        with caplog.at_level("DEBUG"):
            _widget = CueMakerWidget(context)  # noqa: F841

        # Should log debug message about using defaults
        assert any(
            "Waveform config not available, using defaults" in record.message
            for record in caplog.records
        )
