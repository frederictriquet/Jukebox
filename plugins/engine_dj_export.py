"""Engine DJ playlist export module.

Exports a Jukebox playlist to an Engine DJ database (m.db) by creating
a Playlist entry and its PlaylistEntity linked list.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from jukebox.core.protocols import PluginContextProtocol

logger = logging.getLogger(__name__)


@dataclass
class ResolvedTrack:
    """A track resolved between Jukebox and Engine DJ."""

    position: int
    filename: str
    jukebox_filepath: str
    engine_id: int | None = None
    ambiguous: bool = False
    resolution_note: str = ""


@dataclass
class ExportReport:
    """Pre-export validation report."""

    playlist_name: str
    total_tracks: int
    resolved: list[ResolvedTrack] = field(default_factory=list)
    missing: list[ResolvedTrack] = field(default_factory=list)
    ambiguous: list[ResolvedTrack] = field(default_factory=list)
    existing_playlist_id: int | None = None

    def format(self) -> str:
        """Format report as human-readable text."""
        lines = [f'Playlist "{self.playlist_name}" — {self.total_tracks} tracks']

        resolved_count = len(self.resolved)
        lines.append(f"  ✓ {resolved_count} tracks résolus dans Engine DJ")

        if self.missing:
            lines.append(f"  ✗ {len(self.missing)} tracks non trouvés :")
            for t in self.missing:
                lines.append(f"    - {t.filename}")

        if self.ambiguous:
            lines.append(f"  ⚠ {len(self.ambiguous)} filenames ambigus (doublons Engine DJ) :")
            for t in self.ambiguous:
                lines.append(f"    - {t.filename} → id {t.engine_id} ({t.resolution_note})")

        if self.existing_playlist_id is not None:
            lines.append(
                f'  ⚠ Playlist "{self.playlist_name}" existe déjà dans Engine DJ'
                f" (id {self.existing_playlist_id}) → sera écrasée"
            )
        else:
            lines.append(
                f'  ⚠ Playlist "{self.playlist_name}" inexistante dans Engine DJ → sera créée'
            )

        return "\n".join(lines)

    @property
    def can_export(self) -> bool:
        """Whether there are any resolved tracks to export."""
        return len(self.resolved) > 0


class EngineDJExporter:
    """Exports Jukebox playlists to Engine DJ database."""

    def __init__(self, jukebox_db_path: Path, engine_db_path: Path) -> None:
        self.jukebox_db_path = jukebox_db_path
        self.engine_db_path = engine_db_path

    def validate(self, playlist_id: int, playlist_name: str) -> ExportReport:
        """Validate and build pre-export report."""
        conn = sqlite3.connect(str(self.engine_db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("ATTACH ? AS jukebox", (str(self.jukebox_db_path),))

        try:
            return self._build_report(conn, playlist_id, playlist_name)
        finally:
            conn.close()

    def _build_report(
        self, conn: sqlite3.Connection, playlist_id: int, playlist_name: str
    ) -> ExportReport:
        """Build the export report by resolving tracks."""
        # Step 1: Get playlist tracks from Jukebox only
        jukebox_rows = conn.execute(
            """
            SELECT pt.position, jt.filename, jt.filepath AS jukebox_filepath
            FROM jukebox.playlist_tracks pt
            JOIN jukebox.tracks jt ON jt.id = pt.track_id
            WHERE pt.playlist_id = ?
            ORDER BY pt.position
            """,
            (playlist_id,),
        ).fetchall()

        report = ExportReport(playlist_name=playlist_name, total_tracks=len(jukebox_rows))

        if not jukebox_rows:
            return report

        # Check if playlist already exists in Engine DJ
        existing = conn.execute(
            "SELECT id FROM Playlist WHERE title = ?", (playlist_name,)
        ).fetchone()
        if existing:
            report.existing_playlist_id = existing["id"]

        # Step 2: Batch-resolve Engine DJ matches (with path for duplicate resolution)
        # macOS stores filenames in NFD (decomposed), Engine DJ may use NFC (composed).
        # SQLite compares raw bytes, so we resolve in Python with NFC normalization.

        # Pre-compute NFC filenames and jukebox filepath lookup in a single pass
        unique_nfc: set[str] = set()
        filepath_by_filename: dict[str, str] = {}
        for row in jukebox_rows:
            fn_nfc = unicodedata.normalize("NFC", row["filename"])
            unique_nfc.add(fn_nfc)
            if fn_nfc not in filepath_by_filename:
                filepath_by_filename[fn_nfc] = row["jukebox_filepath"]

        # Fetch all Engine DJ tracks and filter + group in a single pass
        all_engine_rows = conn.execute("SELECT id, filename, path FROM Track").fetchall()
        engine_map: dict[str, list[dict]] = defaultdict(list)
        for er in all_engine_rows:
            fn_nfc = unicodedata.normalize("NFC", er["filename"])
            if fn_nfc in unique_nfc:
                engine_map[fn_nfc].append({"engine_id": er["id"], "path": er["path"]})

        dupe_resolution = self._resolve_duplicates(engine_map, filepath_by_filename)

        # Step 3: Process each track
        # Engine DJ has UNIQUE(listId, databaseUuid, trackId), so deduplicate by filename
        seen_filenames: set[str] = set()
        for row in jukebox_rows:
            fn_nfc = unicodedata.normalize("NFC", row["filename"])
            if fn_nfc in seen_filenames:
                continue
            seen_filenames.add(fn_nfc)

            track = ResolvedTrack(
                position=row["position"],
                filename=row["filename"],
                jukebox_filepath=row["jukebox_filepath"],
            )

            engine_matches = engine_map.get(fn_nfc, [])

            if not engine_matches:
                report.missing.append(track)
            elif len(engine_matches) == 1:
                track.engine_id = engine_matches[0]["engine_id"]
                report.resolved.append(track)
            else:
                # Ambiguous — use pre-resolved result
                resolved_id, note = dupe_resolution.get(
                    fn_nfc, (engine_matches[0]["engine_id"], "")
                )
                track.engine_id = resolved_id
                track.ambiguous = True
                track.resolution_note = note
                report.ambiguous.append(track)
                report.resolved.append(track)

        return report

    def _resolve_duplicates(
        self,
        engine_map: dict[str, list[dict]],
        filepath_by_filename: dict[str, str],
    ) -> dict[str, tuple[int, str]]:
        """Resolve ambiguous filenames. Returns {filename: (engine_id, note)}."""
        resolution: dict[str, tuple[int, str]] = {}

        ambiguous_filenames = [fn for fn, matches in engine_map.items() if len(matches) > 1]
        if not ambiguous_filenames:
            return resolution

        # Pass 1: try path matching (using data already fetched)
        for fn in ambiguous_filenames:
            jukebox_filepath = filepath_by_filename.get(fn, "")
            # Extract monthly subfolder from jukebox path (e.g., "2024-07")
            jukebox_path = Path(jukebox_filepath)
            monthly_parts = [
                p for p in jukebox_path.parts if len(p) == 7 and p[4:5] == "-" and p[:4].isdigit()
            ]

            if monthly_parts:
                monthly = monthly_parts[-1]
                matched = [m for m in engine_map[fn] if monthly in (m["path"] or "")]
                if len(matched) == 1:
                    resolution[fn] = (matched[0]["engine_id"], f"path match {monthly}")
                    continue

        # Pass 2: fallback to most recent dateAdded
        remaining = [fn for fn in ambiguous_filenames if fn not in resolution]
        if remaining:
            # For remaining ambiguous, pick the highest engine_id as proxy for most recent
            # (autoincrement IDs correlate with insertion order)
            for fn in remaining:
                best = max(engine_map[fn], key=lambda m: m["engine_id"])
                resolution[fn] = (best["engine_id"], "le plus récent")

        return resolution

    def export(self, report: ExportReport) -> None:
        """Execute the export based on a validated report."""
        if not report.can_export:
            raise ValueError("No tracks to export")

        # Backup
        backup_path = self.engine_db_path.with_name(self.engine_db_path.name + ".backup")
        shutil.copy2(self.engine_db_path, backup_path)
        logger.info("Engine DJ backup: %s", backup_path)

        conn = sqlite3.connect(str(self.engine_db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        try:
            # Read database UUID
            db_uuid = conn.execute("SELECT uuid FROM Information LIMIT 1").fetchone()["uuid"]

            conn.execute("BEGIN")

            # Handle existing playlist
            if report.existing_playlist_id is not None:
                # Delete existing playlist entities
                conn.execute(
                    "DELETE FROM PlaylistEntity WHERE listId = ?",
                    (report.existing_playlist_id,),
                )
                # Update playlist metadata
                conn.execute(
                    "UPDATE Playlist SET lastEditTime = datetime('now') WHERE id = ?",
                    (report.existing_playlist_id,),
                )
                list_id = report.existing_playlist_id
            else:
                # Create new playlist at end of linked list
                cursor = conn.execute(
                    """
                    INSERT INTO Playlist
                        (title, parentListId, isPersisted, nextListId,
                         lastEditTime, isExplicitlyExported)
                    VALUES (?, 0, 1, 0, datetime('now'), 1)
                    """,
                    (report.playlist_name,),
                )
                list_id = cursor.lastrowid  # type: ignore[assignment]

            # Build track ID list in order
            resolved_track_ids = [t.engine_id for t in report.resolved]

            # Insert PlaylistEntity in reverse order to build linked list
            prev_entity_id = 0
            for engine_track_id in reversed(resolved_track_ids):
                cursor = conn.execute(
                    """
                    INSERT INTO PlaylistEntity
                        (listId, trackId, databaseUuid, nextEntityId, membershipReference)
                    VALUES (?, ?, ?, ?, 0)
                    """,
                    (list_id, engine_track_id, db_uuid, prev_entity_id),
                )
                prev_entity_id = cursor.lastrowid

            # Verify linked list integrity
            self._verify_linked_list(conn, list_id, len(resolved_track_ids))

            conn.execute("COMMIT")
            logger.info(
                "Exported playlist '%s' (%d tracks) to Engine DJ (list_id=%d)",
                report.playlist_name,
                len(resolved_track_ids),
                list_id,
            )

        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                logger.warning("ROLLBACK failed after export error")
            logger.exception("Export failed, rolling back")
            raise
        finally:
            conn.close()

    def _verify_linked_list(
        self, conn: sqlite3.Connection, list_id: int, expected_count: int
    ) -> None:
        """Verify linked list integrity after insertion."""
        # Check exactly one tail (nextEntityId = 0)
        tails = conn.execute(
            "SELECT COUNT(*) FROM PlaylistEntity WHERE listId = ? AND nextEntityId = 0",
            (list_id,),
        ).fetchone()[0]
        if tails != 1:
            raise RuntimeError(f"Linked list integrity error: {tails} tails found (expected 1)")

        # Check total entries matches expected count
        total_entries = conn.execute(
            "SELECT COUNT(*) FROM PlaylistEntity WHERE listId = ?", (list_id,)
        ).fetchone()[0]
        if total_entries != expected_count:
            raise RuntimeError(
                f"Track count mismatch: inserted {total_entries}, expected {expected_count}"
            )

        # Check no dangling references
        dangling = conn.execute(
            """
            SELECT pe.id FROM PlaylistEntity pe
            LEFT JOIN PlaylistEntity pe2 ON pe.nextEntityId = pe2.id
            WHERE pe.listId = ? AND pe.nextEntityId != 0 AND pe2.id IS NULL
            """,
            (list_id,),
        ).fetchone()
        if dangling:
            raise RuntimeError(
                f"Linked list integrity error: dangling reference from entity {dangling[0]}"
            )


class ExportReportDialog(QDialog):
    """Dialog showing the pre-export report and asking for confirmation."""

    def __init__(self, report: ExportReport, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.report = report
        self._init_ui()

    def _init_ui(self) -> None:
        self.setWindowTitle("Export to Engine DJ")
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)

        layout = QVBoxLayout()

        # Report text
        report_text = QTextEdit()
        report_text.setReadOnly(True)
        report_text.setPlainText(self.report.format())
        layout.addWidget(report_text)

        # Status label
        if not self.report.can_export:
            label = QLabel("❌ Aucun track résolu — export impossible.")
            layout.addWidget(label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        if self.report.can_export:
            export_btn = QPushButton(f"Exporter ({len(self.report.resolved)} tracks)")
            export_btn.setDefault(True)
            export_btn.clicked.connect(self._confirm)
            btn_layout.addWidget(export_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _confirm(self) -> None:
        self.accept()


def get_engine_db_path(context: PluginContextProtocol, parent: QWidget | None) -> Path | None:
    """Get Engine DJ database path from config, saved settings, or file dialog."""
    # Check in-memory config (set by conf_manager on save)
    configured_path = context.config.engine_dj.database_path
    if configured_path and Path(configured_path).exists():
        return Path(configured_path)

    # Check saved setting from conf_manager (key: "general"/"engine_dj_database_path")
    saved_path = context.database.settings.get("general", "engine_dj_database_path")
    if saved_path and Path(saved_path).exists():
        return Path(saved_path)

    # Ask user to select m.db
    path, _ = QFileDialog.getOpenFileName(
        parent,
        "Select Engine DJ Database (m.db)",
        str(Path.home()),
        "SQLite Database (m.db);;All Files (*)",
    )
    if not path:
        return None

    # Save using the same key convention as conf_manager
    engine_path = Path(path)
    context.database.settings.save("general", "engine_dj_database_path", str(engine_path))
    context.config.engine_dj.database_path = str(engine_path)  # type: ignore[misc]
    return engine_path


def export_playlist_to_engine_dj(
    context: PluginContextProtocol,
    playlist_id: int,
    playlist_name: str,
    parent: QWidget | None = None,
) -> None:
    """Full export flow: validate, show report, export on confirmation."""
    engine_path = get_engine_db_path(context, parent)
    if not engine_path:
        return

    jukebox_db_path = context.database.db_path

    exporter = EngineDJExporter(
        jukebox_db_path=Path(jukebox_db_path),
        engine_db_path=engine_path,
    )

    try:
        report = exporter.validate(playlist_id, playlist_name)
    except Exception as e:
        QMessageBox.critical(parent, "Erreur", f"Validation échouée :\n{e}")
        return

    # Show report dialog
    dialog = ExportReportDialog(report, parent)
    dialog.exec()

    if dialog.result() != QDialog.DialogCode.Accepted:
        return

    try:
        exporter.export(report)
        QMessageBox.information(
            parent,
            "Export réussi",
            f'Playlist "{playlist_name}" exportée vers Engine DJ\n'
            f"({len(report.resolved)} tracks)",
        )
    except Exception as e:
        QMessageBox.critical(
            parent,
            "Erreur d'export",
            f"L'export a échoué :\n{e}\n\nLe backup a été conservé.",
        )
