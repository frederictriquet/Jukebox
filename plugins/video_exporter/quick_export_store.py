"""Read/write helpers for the quick-export .jsonl file.

Appended to by QuickExportWorker (quick_export_worker.py) when the user clicks
"Quick Export" in the GUI; read, updated and pruned by the headless
quick-export renderer (jukebox/tools/quick_export_render_tui.py).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class QuickExportEntry:
    """A single loop queued for later, batched video export."""

    track_id: int
    filepath: str
    loop_start: float
    loop_end: float
    exported_at: str
    rendered_at: str | None = None
    output_path: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuickExportEntry:
        """Build an entry from a parsed JSON line.

        `rendered_at`/`output_path` default to None so entries written by the
        original QuickExportWorker (before these fields existed) still load.
        """
        return cls(
            track_id=data["track_id"],
            filepath=data["filepath"],
            loop_start=data["loop_start"],
            loop_end=data["loop_end"],
            exported_at=data["exported_at"],
            rendered_at=data.get("rendered_at"),
            output_path=data.get("output_path"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize back to a plain dict for JSON encoding."""
        return asdict(self)


def read_entries(jsonl_path: Path) -> list[QuickExportEntry]:
    """Read all entries from the .jsonl file.

    Returns an empty list if the file doesn't exist yet. Malformed lines are
    logged and skipped rather than failing the whole read.
    """
    if not jsonl_path.exists():
        return []

    entries: list[QuickExportEntry] = []
    for line_num, raw_line in enumerate(
        jsonl_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            entries.append(QuickExportEntry.from_dict(json.loads(line)))
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logging.warning(
                "[Quick Export] Skipping malformed line %d in %s: %s", line_num, jsonl_path, e
            )

    return entries


def write_entries(jsonl_path: Path, entries: list[QuickExportEntry]) -> None:
    """Atomically rewrite the .jsonl file with the given entries.

    Writes to a temp file and renames over the original so a crash mid-write
    never leaves a truncated/corrupt .jsonl behind.
    """
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = jsonl_path.with_suffix(jsonl_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
    os.replace(tmp_path, jsonl_path)
