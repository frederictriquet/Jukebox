"""Duplicate detection for curating mode.

Checks curating tracks against the jukebox library using a three-pass strategy:
  1. Exact match on normalized (artist, title)
  2. Parse 'Artist - Title' from filename → exact match
  3. Fuzzy filename match via token-accelerated SequenceMatcher
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from pathlib import Path
from typing import Any


class DuplicateStatus(Enum):
    """Duplicate detection result levels."""

    GREEN = "green"  # Not a duplicate
    ORANGE = "orange"  # Possible duplicate
    RED = "red"  # Certain duplicate


@dataclass
class DuplicateResult:
    """Result of a duplicate check."""

    status: DuplicateStatus
    match_info: str | None  # Display string for the matched jukebox track


class DuplicateChecker:
    """Checks curating tracks for duplicates against the jukebox library.

    Maintains an in-memory index of jukebox tracks for fast lookups.
    Call rebuild_index() whenever jukebox tracks change.
    """

    FUZZY_THRESHOLD = 0.8
    MIN_TOKEN_LENGTH = 3  # Ignore short words in fuzzy matching

    def __init__(self, db_path: Path) -> None:
        """Initialize the checker (index is built lazily on first check).

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path
        # (artist_norm, title_norm) -> display string "Artist - Title"
        self._exact_index: dict[tuple[str, str], str] = {}
        # title_norm -> display string (for title-only matching, O(1) lookup)
        self._title_index: dict[str, str] = {}
        # list of (filename_norm, display_string) for fuzzy matching
        self._filenames: list[tuple[str, str]] = []
        # inverted index: token -> list of indices in self._filenames
        self._token_index: dict[str, list[int]] = {}
        self._index_built = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, track: dict[str, Any]) -> DuplicateResult:
        """Check if a track is a duplicate of a jukebox track.

        Args:
            track: Track dict with at least "artist", "title", "filename" keys.

        Returns:
            DuplicateResult with status and optional match description.
        """
        self._ensure_index()

        artist = track.get("artist") or ""
        title = track.get("title") or ""
        filename = track.get("filename") or ""

        # Pass 1 — Exact (artist, title) match
        artist_norm = self._normalize(artist)
        title_norm = self._normalize(title)
        if artist_norm and title_norm:
            match = self._exact_index.get((artist_norm, title_norm))
            if match:
                return DuplicateResult(DuplicateStatus.RED, match)

        # Pass 2 — Parse filename → exact/partial match
        if filename:
            result = self._check_by_filename_parse(filename)
            if result:
                return result

        # Pass 3 — Fuzzy filename match (token-accelerated)
        if filename:
            result = self._check_by_fuzzy_filename(filename)
            if result:
                return result

        return DuplicateResult(DuplicateStatus.GREEN, None)

    def rebuild_index(self) -> None:
        """Rebuild the jukebox index from the database."""
        if self._build_index():
            self._index_built = True
            logging.debug("[DuplicateChecker] Index rebuilt")

    def invalidate_index(self) -> None:
        """Mark the index as stale so it rebuilds lazily on next check."""
        self._index_built = False

    def _ensure_index(self) -> None:
        """Build the index on first use (lazy initialization)."""
        if not self._index_built and self._build_index():
            self._index_built = True

    def recheck_tracks(self, tracks: list[dict[str, Any]]) -> bool:
        """Recheck all tracks in-place and update their duplicate fields.

        Args:
            tracks: List of track dicts to update.

        Returns:
            True if any track's status changed.
        """
        changed = False
        for track in tracks:
            result = self.check(track)
            new_status = result.status.value
            new_match = result.match_info
            if (
                track.get("duplicate_status") != new_status
                or track.get("duplicate_match") != new_match
            ):
                track["duplicate_status"] = new_status
                track["duplicate_match"] = new_match
                changed = True
        return changed

    # ------------------------------------------------------------------
    # Private — Index construction
    # ------------------------------------------------------------------

    def _build_index(self) -> bool:
        """Load all jukebox tracks into the in-memory index.

        Opens its own SQLite connection so it can safely run in any thread.

        Returns:
            True if the index was built successfully, False on error.
        """
        self._exact_index.clear()
        self._title_index.clear()
        self._filenames.clear()
        self._token_index.clear()

        try:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT filepath, artist, title FROM tracks WHERE mode = 'jukebox'"
                ).fetchall()
            finally:
                conn.close()
        except Exception as e:
            logging.error(f"[DuplicateChecker] Failed to load jukebox tracks: {e}")
            return False

        for track in rows:
            artist = track["artist"] or ""
            title = track["title"] or ""
            filename = Path(track["filepath"]).name if track["filepath"] else ""

            display = self._make_display(artist, title, filename)

            # Exact index (only when both artist and title are present)
            artist_norm = self._normalize(artist)
            title_norm = self._normalize(title)
            if artist_norm and title_norm:
                self._exact_index[(artist_norm, title_norm)] = display
                # Title-only index (first match wins; used for partial matching)
                if title_norm not in self._title_index:
                    self._title_index[title_norm] = display

            # Filename index for fuzzy matching
            filename_norm = self._normalize_filename(filename)
            if filename_norm:
                idx = len(self._filenames)
                self._filenames.append((filename_norm, display))
                # Build inverted token index
                for token in self._tokenize(filename_norm):
                    if token not in self._token_index:
                        self._token_index[token] = []
                    self._token_index[token].append(idx)

        logging.debug(
            f"[DuplicateChecker] Index built: {len(self._exact_index)} exact, "
            f"{len(self._title_index)} titles, {len(self._filenames)} filenames"
        )
        return True

    # ------------------------------------------------------------------
    # Private — Matching passes
    # ------------------------------------------------------------------

    def _check_by_filename_parse(self, filename: str) -> DuplicateResult | None:
        """Pass 2: parse 'Artist - Title' from filename and look up."""
        parsed_artist, parsed_title = self._parse_filename(filename)
        parsed_artist_norm = self._normalize(parsed_artist)
        parsed_title_norm = self._normalize(parsed_title)

        if parsed_artist_norm and parsed_title_norm:
            # Full artist+title extracted → try exact match
            match = self._exact_index.get((parsed_artist_norm, parsed_title_norm))
            if match:
                return DuplicateResult(DuplicateStatus.RED, match)

        if parsed_title_norm and not parsed_artist_norm:
            # Only title extracted → O(1) title-only lookup
            match = self._title_index.get(parsed_title_norm)
            if match:
                return DuplicateResult(DuplicateStatus.ORANGE, match)

        return None

    def _check_by_fuzzy_filename(self, filename: str) -> DuplicateResult | None:
        """Pass 3: fuzzy filename match using token-accelerated SequenceMatcher.

        Algorithm:
            1. Tokenize the query filename (words ≥ MIN_TOKEN_LENGTH).
            2. Use the inverted token index to collect candidates that share tokens
               with the query (avoids O(n) full-scan over the whole library).
            3. Prefer candidates sharing ≥ 2 tokens; fall back to single-token
               candidates (capped at 50) when nothing better is found.
            4. Run SequenceMatcher only on the candidate set and return the best
               match if its ratio ≥ FUZZY_THRESHOLD.
        """
        filename_norm = self._normalize_filename(filename)
        if not filename_norm:
            return None

        tokens = self._tokenize(filename_norm)
        if not tokens:
            return None

        # Count how many tokens each candidate shares with the query
        candidate_hits: dict[int, int] = {}
        for token in tokens:
            for idx in self._token_index.get(token, []):
                candidate_hits[idx] = candidate_hits.get(idx, 0) + 1

        # Require at least 2 shared tokens (avoids noisy single-token matches)
        candidates = [idx for idx, hits in candidate_hits.items() if hits >= 2]

        # If too few multi-token candidates, fall back to single-token but cap at 50
        if not candidates:
            candidates = list(candidate_hits.keys())[:50]

        best_ratio = 0.0
        best_display: str | None = None
        for idx in candidates:
            jb_filename_norm, jb_display = self._filenames[idx]
            ratio = SequenceMatcher(None, filename_norm, jb_filename_norm).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_display = jb_display

        if best_ratio >= self.FUZZY_THRESHOLD and best_display:
            return DuplicateResult(DuplicateStatus.ORANGE, best_display)

        return None

    # ------------------------------------------------------------------
    # Private — Normalization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(text: str) -> str:
        """Lowercase, strip whitespace, remove punctuation, collapse spaces.

        Note: underscores are preserved here (kept by \\w) because artist/title
        metadata rarely contains underscores as separators.  Contrast with
        _normalize_filename, which treats underscores as word separators.
        """
        no_punct = re.sub(r"[^\w\s]", "", text.lower().strip())
        return re.sub(r"\s+", " ", no_punct)

    @staticmethod
    def _normalize_filename(filename: str) -> str:
        """Remove extension, replace separators (including underscore) with spaces, lowercase."""
        stem = Path(filename).stem
        # Use [^a-z0-9] so underscores are treated as separators (not kept like \w does)
        return re.sub(r"[^a-z0-9]", " ", stem.lower()).strip()

    @staticmethod
    def _parse_filename(filename: str) -> tuple[str, str]:
        """Parse 'Artist - Title' from a filename stem.

        Returns:
            (artist, title) tuple. Artist may be empty if no ' - ' separator found.
        """
        stem = Path(filename).stem
        if " - " in stem:
            parts = stem.split(" - ", 1)
            return (parts[0].strip(), parts[1].strip())
        return ("", stem.strip())

    def _tokenize(self, text: str) -> set[str]:
        """Split normalized text into tokens, filtering short words.

        Expects text already normalized (only [a-z0-9 ]).
        """
        return {word for word in re.split(r"\s+", text) if len(word) >= self.MIN_TOKEN_LENGTH}

    @staticmethod
    def _make_display(artist: str, title: str, filename: str) -> str:
        """Build a display string for a jukebox track."""
        if artist and title:
            return f"{artist} - {title}"
        if title:
            return title
        return filename
