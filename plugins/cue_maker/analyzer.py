"""Analyzer worker for shazamix integration."""

from __future__ import annotations

import atexit
import logging
import os

from PySide6.QtCore import QThread, Signal

from plugins.cue_maker.model import CueEntry, EntryStatus

logger = logging.getLogger(__name__)

# Track all live AnalyzeWorker instances.  The atexit handler uses this list
# to force-exit the process when a worker is stuck in non-interruptible C code
# (e.g. librosa.load).  Without this, Python's interpreter finalisation
# destroys the QThread C++ object while the OS thread is still alive, which
# triggers "QThread: Destroyed while thread is still running" and SIGABRT.
_live_workers: list = []


@atexit.register
def _force_exit_if_threads_alive() -> None:
    """Last-resort cleanup: force-exit if any AnalyzeWorker is still running."""
    for worker in _live_workers:
        if worker.isRunning():
            worker.requestInterruption()
            worker.quit()
            if not worker.wait(2000):
                logger.warning(
                    "[Analyzer] Worker still alive at exit, forcing os._exit(0)"
                )
                os._exit(0)


class AnalyzeWorker(QThread):
    """QThread worker for analyzing mixes with shazamix.

    Wraps shazamix Matcher.analyze_mix() with Qt signals for progress updates.
    Runs in background to avoid blocking the UI during long analysis.
    """

    # Signals
    progress = Signal(int, int, str)  # current, total, message
    finished = Signal(list)  # list[CueEntry]
    error = Signal(str)  # error message

    def __init__(
        self,
        mix_path: str,
        db_path: str,
        segment_duration: float = 30.0,
        overlap: float = 15.0,
        max_workers: int = 4,
    ) -> None:
        """Initialize analyzer worker.

        Args:
            mix_path: Path to mix audio file
            db_path: Path to shazamix fingerprint database
            segment_duration: Duration of analysis segments in seconds
            overlap: Overlap between segments in seconds
            max_workers: Number of parallel workers for analysis
        """
        super().__init__()
        self.mix_path = mix_path
        self.db_path = db_path
        self.segment_duration = segment_duration
        self.overlap = overlap
        self.max_workers = max_workers
        _live_workers.append(self)

    def run(self) -> None:
        """Run analysis in background thread.

        Checks the fingerprints cache first. On hit, skips audio loading and
        extraction (the expensive part) and only runs matching. On miss, runs
        the full pipeline and saves the extracted fingerprints for next time.

        Emits progress signals during analysis and finished signal with results.
        Emits error signal if analysis fails.
        """
        try:
            from shazamix.database import FingerprintDB
            from shazamix.fingerprint import Fingerprinter
            from shazamix.matcher import Matcher

            from plugins.cue_maker.cache import (
                load_cached_fingerprints,
                save_fingerprints_cache,
            )

            logger.info("[Analyzer] Starting analysis of %s", self.mix_path)

            # Initialize shazamix
            db = FingerprintDB(self.db_path)
            fingerprinter = Fingerprinter()
            matcher = Matcher(db, fingerprinter)

            # Progress callback — always emit the signal so the UI stays informed
            def progress_callback(current: int, total: int, message: str) -> None:
                logger.info("[Analyzer] %s", message)
                self.progress.emit(current, total, message)

            # Try loading cached fingerprints
            cached_fps = load_cached_fingerprints(self.mix_path)

            # Run analysis (with or without precomputed fingerprints)
            matches, fingerprints = matcher.analyze_mix(
                self.mix_path,
                segment_duration_sec=self.segment_duration,
                overlap_sec=self.overlap,
                progress_callback=progress_callback,
                max_workers=self.max_workers,
                cancelled=self.isInterruptionRequested,
                precomputed_fingerprints=cached_fps,
            )

            if self.isInterruptionRequested():
                logger.info("[Analyzer] Analysis cancelled")
                return

            # Save fingerprints to cache if they were freshly extracted
            if cached_fps is None and fingerprints:
                save_fingerprints_cache(self.mix_path, fingerprints)

            # Convert matches to CueEntry objects
            entries = self._convert_matches(matches)

            logger.info("[Analyzer] Analysis complete: %d matches found", len(entries))
            self.finished.emit(entries)

        except Exception as e:
            logger.error("[Analyzer] Analysis failed: %s", e, exc_info=True)
            self.error.emit(str(e))

    def _convert_matches(self, matches: list) -> list[CueEntry]:
        """Convert shazamix Match objects to CueEntry objects.

        Args:
            matches: List of shazamix Match objects

        Returns:
            List of CueEntry objects
        """
        entries = []

        for match in matches:
            entry = CueEntry(
                start_time_ms=match.query_start_ms,
                artist=match.artist or "Unknown Artist",
                title=match.title or "Unknown Title",
                confidence=match.confidence,
                duration_ms=match.duration_ms,
                status=EntryStatus.PENDING,
                filepath=match.filepath if hasattr(match, "filepath") else "",
                track_id=match.track_id,
                time_stretch_ratio=match.time_stretch_ratio,
            )
            entries.append(entry)

        return entries
