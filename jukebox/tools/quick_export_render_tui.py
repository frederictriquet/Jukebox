"""Headless TUI for rendering videos from quick-exported loops.

Reads the quick_exports.jsonl written by the "Quick Export" button in the GUI
(plugins/video_exporter/quick_export_worker.py), lets the user pick entries
with checkboxes, renders them with the exact same VideoExportWorker and
config-reading path as the GUI export (SettingsSyncMixin over the real
jukebox.db), and marks rendered entries in the .jsonl. Selected entries can
also be deleted from the list regardless of their render status.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import questionary

from jukebox.core.config import load_config
from jukebox.core.database import Database
from jukebox.core.plugin_manager import PluginContext
from plugins.video_exporter.export_config import (
    build_default_export_config,
    write_video_description,
)
from plugins.video_exporter.export_worker import VideoExportWorker
from plugins.video_exporter.plugin import VideoExporterPlugin
from plugins.video_exporter.quick_export_store import QuickExportEntry, read_entries, write_entries

logger = logging.getLogger("quick_export_render_tui")

DEFAULT_DB_PATH = Path.home() / ".jukebox" / "jukebox.db"

_ACTION_RENDER = "Générer la vidéo"
_ACTION_DELETE = "Supprimer de la liste"
_ACTION_CANCEL = "Annuler"


def build_context(db_path: Path, config_path: Path | None) -> PluginContext:
    """Build a PluginContext wired to the real DB/config, no GUI required.

    Reuses PluginContext + SettingsSyncMixin so config defaults (YAML) and
    per-plugin DB overrides resolve exactly like they do in the running app.
    """
    config = load_config(config_path)
    database = Database(db_path)
    database.connect()
    database.initialize_schema()

    app_stub = SimpleNamespace(database=database, player=None, config=config)
    context = PluginContext(app_stub)

    # Reuses the plugin's own DB-override sync (same code path as the GUI's
    # Events.PLUGIN_SETTINGS_CHANGED handler) instead of re-implementing it.
    plugin = VideoExporterPlugin()
    plugin.context = context
    plugin._sync_settings_from_db()

    return context


def default_jsonl_path(context: PluginContext) -> Path:
    """Return the quick_exports.jsonl path under the configured output directory."""
    return Path(context.config.video_exporter.output_directory).expanduser() / "quick_exports.jsonl"


def _resolve_track(context: PluginContext, entry: QuickExportEntry) -> dict[str, Any] | None:
    """Look up the track by ID first (stable), falling back to filepath."""
    track = context.database.tracks.get_by_id(entry.track_id)
    if track is None:
        track = context.database.tracks.get_by_filepath(entry.filepath)
    return track


def _format_entry(entry: QuickExportEntry, track: dict[str, Any] | None) -> str:
    """Build the checkbox label for one entry."""
    duration = entry.loop_end - entry.loop_start
    if track:
        label = f"{track.get('artist') or '?'} - {track.get('title') or '?'}"
    else:
        label = f"{entry.filepath} (introuvable en DB)"
    status = "rendu" if entry.rendered_at else "en attente"
    return f"{label}  [{entry.loop_start:.1f}s-{entry.loop_end:.1f}s / {duration:.1f}s]  ({status})"


def render_entry(context: PluginContext, entry: QuickExportEntry) -> str | None:
    """Render one entry with VideoExportWorker. Returns the output path, or None on failure."""
    track = _resolve_track(context, entry)
    if track is None:
        print(f"  ✗ Morceau introuvable en base pour {entry.filepath}, ignoré.")
        return None

    config_dict = build_default_export_config(
        filepath=Path(entry.filepath),
        loop_start=entry.loop_start,
        loop_end=entry.loop_end,
        track_metadata=track,
        config=context.config.video_exporter,
    )

    output_path = Path(config_dict["output_path"])
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"  ✗ Impossible de créer le dossier de sortie: {e}")
        return None

    worker = VideoExportWorker(config_dict, context)
    worker.status.connect(lambda msg: print(f"  … {msg}"))
    worker.progress.connect(lambda pct: print(f"\r  … {pct}%", end="", flush=True))

    outcome: dict[str, str] = {}
    worker.finished.connect(lambda path: outcome.__setitem__("output_path", path))
    worker.error.connect(lambda msg: outcome.__setitem__("error", msg))

    worker.run()  # Synchronous: no QThread.start()/event loop needed for a CLI tool.
    print()

    if "error" in outcome:
        print(f"  ✗ Échec du rendu: {outcome['error']}")
        return None

    write_video_description(outcome["output_path"], track, context.config.genre_editor.codes)
    return outcome["output_path"]


def render_selected(
    context: PluginContext,
    jsonl_path: Path,
    entries: list[QuickExportEntry],
    selected: list[int],
) -> None:
    """Render each selected entry, persisting rendered_at/output_path after each success."""
    for i in selected:
        entry = entries[i]
        print(f"Rendu de {entry.filepath} [{entry.loop_start:.1f}s-{entry.loop_end:.1f}s]...")
        output_path = render_entry(context, entry)
        if output_path is not None:
            entry.rendered_at = datetime.now(UTC).isoformat()
            entry.output_path = output_path
            write_entries(jsonl_path, entries)
            print(f"  ✓ Vidéo générée: {output_path}")


def delete_selected(
    jsonl_path: Path,
    entries: list[QuickExportEntry],
    selected: list[int],
) -> list[QuickExportEntry]:
    """Remove the selected entries from the .jsonl, regardless of render status."""
    remaining = [e for i, e in enumerate(entries) if i not in selected]
    write_entries(jsonl_path, remaining)
    return remaining


def run_tui(context: PluginContext, jsonl_path: Path) -> None:
    """Main interactive loop: pick entries, then render or delete them."""
    while True:
        entries = read_entries(jsonl_path)
        if not entries:
            print("Aucune entrée dans le fichier de quick export.")
            return

        choices = [
            questionary.Choice(
                title=_format_entry(e, _resolve_track(context, e)),
                value=i,
                checked=e.rendered_at is None,
            )
            for i, e in enumerate(entries)
        ]
        selected = questionary.checkbox(
            "Sélectionnez une ou plusieurs entrées (espace = cocher, entrée = valider) :",
            choices=choices,
        ).ask()

        if selected is None:  # Ctrl-C
            return
        if not selected:
            if questionary.confirm("Aucune sélection. Quitter ?", default=True).ask() is not False:
                return
            continue

        action = questionary.select(
            f"{len(selected)} entrée(s) sélectionnée(s) — action :",
            choices=[_ACTION_RENDER, _ACTION_DELETE, _ACTION_CANCEL],
        ).ask()

        if action is None or action == _ACTION_CANCEL:
            continue
        if action == _ACTION_DELETE:
            delete_selected(jsonl_path, entries, selected)
            print(f"{len(selected)} entrée(s) supprimée(s).")
            continue
        if action == _ACTION_RENDER:
            render_selected(context, jsonl_path, entries, selected)
            continue


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--jsonl", type=Path, default=None, help="Override the quick_exports.jsonl path"
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Path to jukebox.db")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.yaml")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.WARNING)
    args = parse_args(argv)

    context = build_context(args.db, args.config)
    jsonl_path = args.jsonl or default_jsonl_path(context)

    run_tui(context, jsonl_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
