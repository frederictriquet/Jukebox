"""Match audio fingerprints against the database to identify tracks.

The matching algorithm:
1. Extract fingerprints from the query audio (mix segment)
2. Query the database for matching hashes
3. Use temporal coherence to validate matches
4. Return ranked list of matching tracks with confidence scores
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterator

import numpy as np

from .fingerprint import Fingerprinter, Fingerprint
from .database import FingerprintDB


@dataclass
class Match:
    """A detected track match in the mix."""
    track_id: int
    title: str | None
    artist: str | None
    filename: str
    filepath: str
    confidence: float  # 0.0 to 1.0
    query_start_ms: int  # Position in the query/mix
    track_start_ms: int  # Position in the original track
    duration_ms: int  # Estimated duration of the match
    match_count: int  # Number of matching fingerprints
    time_stretch_ratio: float  # Detected tempo change (1.0 = no change)


@dataclass
class CueEntry:
    """A cue sheet entry."""
    start_time_ms: int
    track_id: int
    title: str | None
    artist: str | None
    filename: str
    confidence: float


class Matcher:
    """Match query audio against fingerprint database."""

    def __init__(
        self,
        db: FingerprintDB,
        fingerprinter: Fingerprinter | None = None,
        min_matches: int = 5,  # Minimum matching fingerprints to consider
        time_tolerance_ms: int = 500,  # Tolerance for temporal alignment
        min_confidence: float = 0.1,  # Minimum confidence to report
    ):
        """Initialize matcher.

        Args:
            db: Fingerprint database
            fingerprinter: Fingerprinter instance (uses default if None)
            min_matches: Minimum matching fingerprints to consider a match
            time_tolerance_ms: Tolerance for temporal coherence checking
            min_confidence: Minimum confidence score to report a match
        """
        self.db = db
        self.fingerprinter = fingerprinter or Fingerprinter()
        self.min_matches = min_matches
        self.time_tolerance_ms = time_tolerance_ms
        self.min_confidence = min_confidence

    def identify_track(self, audio_path: str) -> list[Match]:
        """Identify a single audio file against the database.

        Args:
            audio_path: Path to audio file

        Returns:
            List of matches sorted by confidence (highest first)
        """
        # Extract fingerprints from query
        query_fps = self.fingerprinter.extract_fingerprints(audio_path)

        if not query_fps:
            return []

        return self._match_fingerprints(query_fps)

    def analyze_mix(
        self,
        mix_path: str,
        segment_duration_sec: float = 30.0,
        overlap_sec: float = 15.0,
    ) -> list[Match]:
        """Analyze a mix file to identify all tracks used.

        Splits the mix into overlapping segments and identifies each.

        Args:
            mix_path: Path to mix audio file
            segment_duration_sec: Duration of each analysis segment
            overlap_sec: Overlap between segments

        Returns:
            List of all matches found, merged and deduplicated
        """
        import librosa

        # Load full mix
        y, sr = librosa.load(mix_path, sr=self.fingerprinter.sample_rate, mono=True)
        duration_sec = len(y) / sr

        # Calculate segment parameters
        segment_samples = int(segment_duration_sec * sr)
        hop_samples = int((segment_duration_sec - overlap_sec) * sr)

        all_matches: list[Match] = []

        # Process each segment
        position = 0
        while position < len(y):
            segment = y[position:position + segment_samples]

            if len(segment) < sr * 5:  # Skip segments shorter than 5 seconds
                break

            # Extract fingerprints for this segment
            segment_fps = self.fingerprinter.extract_fingerprints_from_array(segment)

            if segment_fps:
                # Adjust time offsets to be relative to mix start
                segment_start_ms = int((position / sr) * 1000)
                adjusted_fps = [
                    Fingerprint(
                        hash=fp.hash,
                        time_offset_ms=fp.time_offset_ms + segment_start_ms,
                        freq_bin=fp.freq_bin,
                    )
                    for fp in segment_fps
                ]

                matches = self._match_fingerprints(adjusted_fps)
                all_matches.extend(matches)

            position += hop_samples

        # Merge and deduplicate matches
        merged = self._merge_matches(all_matches)

        return merged

    def _match_fingerprints(self, query_fps: list[Fingerprint]) -> list[Match]:
        """Match fingerprints against database.

        Uses histogram-based temporal coherence:
        1. For each matching hash, compute time offset (query_time - db_time)
        2. Build histogram of time offsets per track
        3. Peaks in histogram indicate true matches (aligned in time)

        Args:
            query_fps: Query fingerprints

        Returns:
            List of matches
        """
        # Get unique hashes to query
        unique_hashes = list(set(fp.hash for fp in query_fps))
        db_matches = self.db.query_fingerprints(unique_hashes)

        if not db_matches:
            return []

        # Build lookup: hash -> list of query times
        query_times_by_hash: dict[int, list[int]] = defaultdict(list)
        for fp in query_fps:
            query_times_by_hash[fp.hash].append(fp.time_offset_ms)

        # For each track, build histogram of time offsets
        # Key insight: true matches will cluster at the same time offset
        track_offsets: dict[int, list[int]] = defaultdict(list)

        for track_id, db_time_ms, hash_val in db_matches:
            # For each query fingerprint with this hash
            for query_time in query_times_by_hash[hash_val]:
                # Time offset = query_time - db_time
                # True matches: this offset is consistent across many fingerprints
                offset = query_time - db_time_ms
                track_offsets[track_id].append(offset)

        # Analyze each track's offset histogram
        matches: list[Match] = []
        total_query_fps = len(query_fps)

        for track_id, offsets in track_offsets.items():
            if len(offsets) < self.min_matches:
                continue

            # Find clusters of consistent offsets (histogram peaks)
            clusters = self._find_offset_clusters(offsets)

            for cluster_offset, cluster_count, cluster_offsets in clusters:
                if cluster_count < self.min_matches:
                    continue

                # Get track info
                track_info = self.db.get_track_info(track_id)
                if not track_info:
                    continue

                # Calculate confidence:
                # - Based on ratio of matching fingerprints to query total
                # - Bonus for tight temporal clustering
                match_ratio = cluster_count / total_query_fps

                # Tightness: how concentrated are the offsets?
                if len(cluster_offsets) > 1:
                    offset_std = np.std(cluster_offsets)
                    tightness_bonus = max(0, 1 - offset_std / 1000)  # Bonus if std < 1000ms
                else:
                    tightness_bonus = 1.0

                confidence = min(1.0, match_ratio * 10 * (0.5 + 0.5 * tightness_bonus))

                # Estimate query position
                query_start = cluster_offset if cluster_offset > 0 else 0
                track_start = -cluster_offset if cluster_offset < 0 else 0

                # Estimate duration from spread of matching fingerprints
                duration_ms = max(cluster_offsets) - min(cluster_offsets) if cluster_offsets else 0

                match = Match(
                    track_id=track_id,
                    title=track_info.get("title"),
                    artist=track_info.get("artist"),
                    filename=track_info.get("filename", ""),
                    filepath=track_info.get("filepath", ""),
                    confidence=confidence,
                    query_start_ms=query_start,
                    track_start_ms=track_start,
                    duration_ms=duration_ms,
                    match_count=cluster_count,
                    time_stretch_ratio=1.0,  # TODO: estimate from offset drift
                )
                matches.append(match)

        # Sort by confidence (descending), then by match count
        matches.sort(key=lambda m: (-m.confidence, -m.match_count))

        # Filter by minimum confidence
        matches = [m for m in matches if m.confidence >= self.min_confidence]

        return matches

    def _find_offset_clusters(
        self,
        offsets: list[int],
        bin_width_ms: int = 100,
    ) -> list[tuple[int, int, list[int]]]:
        """Find clusters of time offsets using histogram binning.

        Args:
            offsets: List of time offsets in milliseconds
            bin_width_ms: Width of histogram bins

        Returns:
            List of (center_offset, count, offsets_in_cluster) tuples
        """
        if not offsets:
            return []

        # Bin offsets into histogram
        min_offset = min(offsets)
        max_offset = max(offsets)

        # Create bins
        bins: dict[int, list[int]] = defaultdict(list)
        for offset in offsets:
            bin_idx = (offset - min_offset) // bin_width_ms
            bins[bin_idx].append(offset)

        # Find peaks (bins with many entries)
        clusters = []
        for bin_idx, bin_offsets in bins.items():
            if len(bin_offsets) >= self.min_matches:
                center = min_offset + bin_idx * bin_width_ms + bin_width_ms // 2
                clusters.append((center, len(bin_offsets), bin_offsets))

        # Sort by count descending
        clusters.sort(key=lambda x: -x[1])

        return clusters

    def _merge_matches(self, matches: list[Match]) -> list[Match]:
        """Merge overlapping matches for the same track.

        Args:
            matches: List of matches (may have duplicates)

        Returns:
            Merged and deduplicated matches
        """
        if not matches:
            return []

        # Group by track_id
        by_track: dict[int, list[Match]] = defaultdict(list)
        for m in matches:
            by_track[m.track_id].append(m)

        merged: list[Match] = []

        for track_id, track_matches in by_track.items():
            # Sort by query start time
            track_matches.sort(key=lambda m: m.query_start_ms)

            # Merge overlapping matches
            current = track_matches[0]

            for m in track_matches[1:]:
                # Check if overlapping (within 30 seconds)
                if m.query_start_ms - (current.query_start_ms + current.duration_ms) < 30000:
                    # Merge: extend duration, sum match count, average confidence
                    new_end = max(
                        current.query_start_ms + current.duration_ms,
                        m.query_start_ms + m.duration_ms
                    )
                    current = Match(
                        track_id=current.track_id,
                        title=current.title,
                        artist=current.artist,
                        filename=current.filename,
                        filepath=current.filepath,
                        confidence=max(current.confidence, m.confidence),
                        query_start_ms=current.query_start_ms,
                        track_start_ms=current.track_start_ms,
                        duration_ms=new_end - current.query_start_ms,
                        match_count=current.match_count + m.match_count,
                        time_stretch_ratio=(current.time_stretch_ratio + m.time_stretch_ratio) / 2,
                    )
                else:
                    merged.append(current)
                    current = m

            merged.append(current)

        # Sort by query position
        merged.sort(key=lambda m: m.query_start_ms)

        return merged

    def generate_cue_sheet(self, matches: list[Match]) -> list[CueEntry]:
        """Generate a cue sheet from matches.

        Args:
            matches: List of matches (should be sorted by query position)

        Returns:
            List of cue entries
        """
        cues: list[CueEntry] = []

        for m in matches:
            cue = CueEntry(
                start_time_ms=m.query_start_ms,
                track_id=m.track_id,
                title=m.title,
                artist=m.artist,
                filename=m.filename,
                confidence=m.confidence,
            )
            cues.append(cue)

        return cues

    def format_cue_sheet(self, cues: list[CueEntry]) -> str:
        """Format cue sheet as human-readable text.

        Args:
            cues: List of cue entries

        Returns:
            Formatted string
        """
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("CUE SHEET")
        lines.append("=" * 60)
        lines.append("")

        for i, cue in enumerate(cues, 1):
            time_str = self._format_time(cue.start_time_ms)

            if cue.artist and cue.title:
                track_str = f"{cue.artist} - {cue.title}"
            elif cue.title:
                track_str = cue.title
            else:
                track_str = cue.filename

            confidence_str = f"({cue.confidence:.0%})"

            lines.append(f"{i:2d}. [{time_str}] {track_str} {confidence_str}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    def _format_time(self, ms: int) -> str:
        """Format milliseconds as HH:MM:SS or MM:SS."""
        total_seconds = ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
