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

    def identify_track(
        self,
        audio_path: str,
        max_duration_sec: float = 60.0,
        sample_fingerprints: int = 500,
    ) -> list[Match]:
        """Identify a single audio file against the database.

        For faster identification, only analyzes a portion of the file
        and samples fingerprints.

        Args:
            audio_path: Path to audio file
            max_duration_sec: Maximum duration to analyze (from middle of track)
            sample_fingerprints: Maximum fingerprints to use for matching

        Returns:
            List of matches sorted by confidence (highest first)
        """
        import librosa

        # Load only a portion of the audio (from middle for better representation)
        y, sr = librosa.load(
            audio_path,
            sr=self.fingerprinter.sample_rate,
            mono=True,
            duration=max_duration_sec * 2,  # Load more, then take middle
        )

        if len(y) == 0:
            return []

        # Take the middle portion if file is longer than max_duration
        total_duration = len(y) / sr
        if total_duration > max_duration_sec:
            # Take middle portion
            samples_to_take = int(max_duration_sec * sr)
            start = (len(y) - samples_to_take) // 2
            y = y[start:start + samples_to_take]

        # Extract fingerprints
        query_fps = self.fingerprinter.extract_fingerprints_from_array(y)

        if not query_fps:
            return []

        # Sample fingerprints if too many (spread evenly across time)
        if len(query_fps) > sample_fingerprints:
            step = len(query_fps) // sample_fingerprints
            query_fps = query_fps[::step][:sample_fingerprints]

        return self._match_fingerprints(query_fps)

    def analyze_mix(
        self,
        mix_path: str,
        segment_duration_sec: float = 30.0,
        overlap_sec: float = 15.0,
        progress_callback: callable | None = None,
        max_workers: int = 4,
    ) -> list[Match]:
        """Analyze a mix file to identify all tracks used.

        Splits the mix into overlapping segments and identifies each in parallel.

        Args:
            mix_path: Path to mix audio file
            segment_duration_sec: Duration of each analysis segment
            overlap_sec: Overlap between segments
            progress_callback: Optional callback(current, total, message) for progress
            max_workers: Number of parallel workers for segment analysis

        Returns:
            List of all matches found, merged and deduplicated
        """
        import librosa
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def log(msg: str) -> None:
            if progress_callback:
                progress_callback(-1, -1, msg)

        log(f"Loading audio file...")

        # Load full mix
        y, sr = librosa.load(mix_path, sr=self.fingerprinter.sample_rate, mono=True)
        duration_sec = len(y) / sr

        log(f"Mix duration: {duration_sec/60:.1f} minutes")

        # Calculate segment parameters
        segment_samples = int(segment_duration_sec * sr)
        hop_samples = int((segment_duration_sec - overlap_sec) * sr)

        # Build list of segments to process
        segments: list[tuple[int, np.ndarray]] = []
        position = 0
        while position < len(y):
            segment = y[position:position + segment_samples]
            if len(segment) < sr * 5:
                break
            segments.append((position, segment))
            position += hop_samples

        total_segments = len(segments)
        log(f"Processing {total_segments} segments with {max_workers} workers...")

        def process_segment(args: tuple[int, np.ndarray]) -> list[Match]:
            """Process a single segment and return matches."""
            pos, segment_data = args
            segment_fps = self.fingerprinter.extract_fingerprints_from_array(segment_data)

            if not segment_fps:
                return []

            # Adjust time offsets to be relative to mix start
            segment_start_ms = int((pos / sr) * 1000)
            adjusted_fps = [
                Fingerprint(
                    hash=fp.hash,
                    time_offset_ms=fp.time_offset_ms + segment_start_ms,
                    freq_bin=fp.freq_bin,
                )
                for fp in segment_fps
            ]

            return self._match_fingerprints(adjusted_fps)

        all_matches: list[Match] = []
        completed = 0

        # Process segments in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_segment, seg): seg[0] for seg in segments}

            for future in as_completed(futures):
                pos = futures[future]
                try:
                    matches = future.result()
                    all_matches.extend(matches)
                except Exception as e:
                    log(f"Error processing segment at {pos/sr:.1f}s: {e}")

                completed += 1
                if progress_callback:
                    progress_callback(completed, total_segments, f"Segment {completed}/{total_segments}")

        log(f"Merging {len(all_matches)} raw matches...")

        # Merge and deduplicate matches
        merged = self._merge_matches(all_matches)

        log(f"Found {len(merged)} unique tracks")

        return merged

    def _match_fingerprints(self, query_fps: list[Fingerprint]) -> list[Match]:
        """Match fingerprints against database using vectorized numpy operations.

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

        # Build lookup: hash -> first query time
        query_time_by_hash: dict[int, int] = {}
        for fp in query_fps:
            if fp.hash not in query_time_by_hash:
                query_time_by_hash[fp.hash] = fp.time_offset_ms

        # Filter db_matches to only those with matching hashes and build arrays
        filtered_matches = [
            (track_id, db_time, hash_val)
            for track_id, db_time, hash_val in db_matches
            if hash_val in query_time_by_hash
        ]

        if not filtered_matches:
            return []

        # Convert to numpy arrays for vectorized operations
        db_track_ids = np.array([m[0] for m in filtered_matches], dtype=np.int32)
        db_times = np.array([m[1] for m in filtered_matches], dtype=np.int32)
        db_hashes = np.array([m[2] for m in filtered_matches], dtype=np.int64)

        # Vectorized: get query times for each db match
        query_times = np.array([query_time_by_hash[h] for h in db_hashes], dtype=np.int32)

        # Compute all offsets at once
        offsets = query_times - db_times

        # Get unique tracks and their best matches
        unique_tracks = np.unique(db_track_ids)

        # For efficiency, only analyze top N tracks by raw match count
        track_counts = [(t, np.sum(db_track_ids == t)) for t in unique_tracks]
        track_counts.sort(key=lambda x: -x[1])
        top_tracks = [t for t, c in track_counts[:100] if c >= self.min_matches]

        matches: list[Match] = []
        total_query_fps = len(query_fps)
        track_info_cache: dict[int, dict | None] = {}

        for track_id_np in top_tracks:
            track_id = int(track_id_np)  # Convert numpy int to Python int

            # Get offsets for this track
            mask = db_track_ids == track_id_np
            track_offsets = offsets[mask]

            if len(track_offsets) < self.min_matches:
                continue

            # Fast histogram using numpy
            bin_width = 100  # ms
            if len(track_offsets) > 0:
                min_off, max_off = track_offsets.min(), track_offsets.max()
                if max_off - min_off < bin_width:
                    # All offsets in one bin
                    best_count = len(track_offsets)
                    best_offset = int(np.median(track_offsets))
                else:
                    bins = np.arange(min_off, max_off + bin_width, bin_width)
                    hist, edges = np.histogram(track_offsets, bins=bins)
                    best_bin = np.argmax(hist)
                    best_count = int(hist[best_bin])
                    best_offset = int(edges[best_bin] + bin_width // 2)

                if best_count < self.min_matches:
                    continue

                # Get track info (cached)
                if track_id not in track_info_cache:
                    track_info_cache[track_id] = self.db.get_track_info(track_id)
                track_info = track_info_cache[track_id]

                if not track_info:
                    continue

                # Calculate confidence
                match_ratio = best_count / total_query_fps
                confidence = min(1.0, match_ratio * 5)  # Simplified scoring

                match = Match(
                    track_id=track_id,
                    title=track_info.get("title"),
                    artist=track_info.get("artist"),
                    filename=track_info.get("filename", ""),
                    filepath=track_info.get("filepath", ""),
                    confidence=confidence,
                    query_start_ms=max(0, best_offset),
                    track_start_ms=max(0, -best_offset),
                    duration_ms=0,
                    match_count=int(best_count),
                    time_stretch_ratio=1.0,
                )
                matches.append(match)

        # Sort by match count (most reliable metric)
        matches.sort(key=lambda m: -m.match_count)

        # Filter by minimum confidence and keep top results
        matches = [m for m in matches if m.confidence >= self.min_confidence][:20]

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
