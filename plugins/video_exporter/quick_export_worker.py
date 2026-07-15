"""Worker thread for upserting a quick-export record, off the UI thread."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from plugins.video_exporter.quick_export_store import QuickExportEntry, read_entries, write_entries


class QuickExportWorker(QThread):
    """Upsert a single quick-export record, deduped by track_id, off the UI thread.

    Re-clicking Quick Export for a track that already has a pending entry
    replaces it (fresh loop bounds/timestamp, cleared render status) instead
    of appending a duplicate line.
    """

    finished = Signal()
    error = Signal(str)

    def __init__(self, jsonl_path: Path, entry: QuickExportEntry) -> None:
        """Initialize the worker.

        Args:
            jsonl_path: Path to the .jsonl file to update.
            entry: The record to insert, or to replace an existing same-track_id record with.
        """
        super().__init__()
        self.jsonl_path = jsonl_path
        self.entry = entry
        self.setObjectName(f"VideoExporter-QuickExportWorker-{entry.track_id}")

    def run(self) -> None:
        """Upsert the entry by track_id and rewrite the .jsonl file."""
        try:
            entries = read_entries(self.jsonl_path)
            existing_index = next(
                (i for i, e in enumerate(entries) if e.track_id == self.entry.track_id), None
            )
            if existing_index is None:
                entries.append(self.entry)
            else:
                entries[existing_index] = self.entry
            write_entries(self.jsonl_path, entries)
        except OSError as e:
            logging.exception("[Quick Export] Failed to write %s", self.jsonl_path)
            self.error.emit(str(e))
            return

        self.finished.emit()
