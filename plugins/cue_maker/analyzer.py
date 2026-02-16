"""Analyzer worker for shazamix integration."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from plugins.cue_maker.model import CueEntry, EntryStatus

logger = logging.getLogger(__name__)


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

    def run(self) -> None:
        """Run analysis in background thread.

        Emits progress signals during analysis and finished signal with results.
        Emits error signal if analysis fails.
        """
        try:
            from shazamix.fingerprint import (  # type: ignore[attr-defined]
                FingerprintDB,
                Fingerprinter,
            )
            from shazamix.matcher import Matcher

            logger.info("[Analyzer] Starting analysis of %s", self.mix_path)

            # Initialize shazamix
            db = FingerprintDB(self.db_path)
            fingerprinter = Fingerprinter()
            matcher = Matcher(db, fingerprinter)

            # Progress callback
            def progress_callback(current: int, total: int, message: str) -> None:
                if current < 0:
                    # Log message
                    logger.debug("[Analyzer] %s", message)
                else:
                    # Progress update
                    self.progress.emit(current, total, message)

            # Run analysis
            matches = matcher.analyze_mix(
                self.mix_path,
                segment_duration_sec=self.segment_duration,
                overlap_sec=self.overlap,
                progress_callback=progress_callback,
                max_workers=self.max_workers,
            )

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
