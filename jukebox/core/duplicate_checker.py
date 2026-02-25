"""Duplicate detection for curating mode.

Checks curating tracks against the jukebox library using a three-pass strategy:
  1. Exact match on normalized (artist, title)
  2. Parse 'Artist - Title' from filename → exact match
  3. Fuzzy filename match via token-accelerated SequenceMatcher
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jukebox.core.database import Database


class DuplicateStatus(Enum):
    """Duplicate detection result levels."""

    GREEN = "green"   # Not a duplicate
    ORANGE = "orange"  # Possible duplicate
    RED = "red"        # Certain duplicate


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

    def __init__(self, database: Database) -> None:
        """Initialize the checker (index is built lazily on first check).

        Args:
            database: Database instance (for loading jukebox tracks).
        """
        self._database = database
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
        self._build_index()
        self._index_built = True
        logging.debug("[DuplicateChecker] Index rebuilt")

    def _ensure_index(self) -> None:
        """Build the index on first use (lazy initialization)."""
        if not self._index_built:
            self._build_index()
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
            if track.get("duplicate_status") != new_status or track.get("duplicate_match") != new_match:
                track["duplicate_status"] = new_status
                track["duplicate_match"] = new_match
                changed = True
        return changed

    # ------------------------------------------------------------------
    # Private — Index construction
    # ------------------------------------------------------------------

    def _build_index(self) -> None:
        """Load all jukebox tracks into the in-memory index."""
        self._exact_index.clear()
        self._title_index.clear()
        self._filenames.clear()
        self._token_index.clear()

        try:
            jukebox_tracks = self._database.tracks.get_all(mode="jukebox")
        except Exception as e:
            logging.error(f"[DuplicateChecker] Failed to load jukebox tracks: {e}")
            return

        for track in jukebox_tracks:
            artist = track.get("artist") or ""
            title = track.get("title") or ""
            filename = track.get("filename") or ""

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
        """Pass 3: fuzzy filename match using token-accelerated SequenceMatcher."""
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
        """Lowercase, strip whitespace, remove punctuation."""
        return re.sub(r"[^\w\s]", "", text.lower().strip())

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
        return {
            word
            for word in re.split(r"\s+", text)
            if len(word) >= self.MIN_TOKEN_LENGTH
        }

    @staticmethod
    def _make_display(artist: str, title: str, filename: str) -> str:
        """Build a display string for a jukebox track."""
        if artist and title:
            return f"{artist} - {title}"
        if title:
            return title
        return filename
