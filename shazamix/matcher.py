"""Match audio fingerprints against the database to identify tracks.

The matching algorithm:
1. Extract fingerprints from the query audio (mix segment)
2. Query the database for matching hashes
3. Use temporal coherence to validate matches
4. Return ranked list of matching tracks with confidence scores
"""

from __future__ import annotations

import logging
import math
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



def _extract_segment_fps(
    segment_data: np.ndarray,
    segment_start_ms: int,
    fp_kwargs: dict,
) -> list[Fingerprint]:
    """Extract fingerprints from one segment. Runs in subprocess."""
    fingerprinter = Fingerprinter(**fp_kwargs)
    fps = fingerprinter.extract_fingerprints_from_array(segment_data)
    return [
        Fingerprint(
            hash=fp.hash,
            time_offset_ms=fp.time_offset_ms + segment_start_ms,
            freq_bin=fp.freq_bin,
        )
        for fp in fps
    ]


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
            y = y[start : start + samples_to_take]

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
        cancelled: callable | None = None,
        precomputed_fingerprints: list[list[Fingerprint]] | None = None,
    ) -> tuple[list[Match], list[list[Fingerprint]]]:
        """Analyze a mix file to identify all tracks used.

        Splits the mix into overlapping segments, extracts fingerprints in
        parallel using ProcessPoolExecutor, then matches globally across all
        segments with tempo-aware search.

        Args:
            mix_path: Path to mix audio file
            segment_duration_sec: Duration of each analysis segment
            overlap_sec: Overlap between segments
            progress_callback: Optional callback(current, total, message) for progress
            max_workers: Number of parallel workers for segment analysis
            cancelled: Optional callable returning True if analysis should be aborted
            precomputed_fingerprints: If provided, skip audio loading and fingerprint
                extraction; use these segment-grouped fingerprints directly for matching.

        Returns:
            Tuple of (matches, segment-grouped fingerprints for caching)
        """
        import logging

        from concurrent.futures import ProcessPoolExecutor, as_completed

        logger = logging.getLogger(__name__)

        def is_cancelled() -> bool:
            return cancelled is not None and cancelled()

        def log(msg: str) -> None:
            if progress_callback:
                progress_callback(-1, -1, msg)

        # Fast path: reuse precomputed fingerprints (skip audio + extraction)
        if precomputed_fingerprints is not None:
            log(f"Using cached fingerprints ({len(precomputed_fingerprints)} segments), matching...")
            matches = self._match_global(
                precomputed_fingerprints, progress_callback=progress_callback
            )
            log(f"Found {len(matches)} unique tracks")
            return matches, precomputed_fingerprints

        import librosa

        log("Loading audio file...")

        # Decode via ffmpeg to avoid libsndfile ARM64 crash in non-main
        # threads (mpg123 getcpuflags + setjmp bug).  Manual decode also
        # avoids the librosa audioread deprecation warning.
        import audioread.ffdec

        target_sr = self.fingerprinter.sample_rate
        with audioread.ffdec.FFmpegAudioFile(mix_path) as aro:
            sr_native = aro.samplerate
            n_channels = aro.channels
            frames = []
            for buf in aro:
                frames.append(np.frombuffer(buf, dtype=np.int16))
            y = np.concatenate(frames).astype(np.float32) / 32768.0
            if n_channels > 1:
                y = y.reshape(-1, n_channels).mean(axis=1)

        if sr_native != target_sr:
            y = librosa.resample(y, orig_sr=sr_native, target_sr=target_sr)
        sr = target_sr
        duration_sec = len(y) / sr

        log(f"Mix duration: {duration_sec/60:.1f} minutes")

        if is_cancelled():
            return [], []

        # Calculate segment parameters
        segment_samples = int(segment_duration_sec * sr)
        hop_samples = int((segment_duration_sec - overlap_sec) * sr)

        # Build list of segments to process
        segments: list[tuple[int, np.ndarray]] = []
        position = 0
        while position < len(y):
            segment = y[position : position + segment_samples]
            if len(segment) < sr * 5:
                break
            segments.append((position, segment))
            position += hop_samples

        total_segments = len(segments)
        log(f"Extracting {total_segments} segments with {max_workers} workers...")

        # Phase 1 — Extraction with ProcessPoolExecutor (CPU-bound)
        fp_kwargs = {
            "sample_rate": self.fingerprinter.sample_rate,
            "hop_length": self.fingerprinter.hop_length,
            "n_bins": self.fingerprinter.n_bins,
            "bins_per_octave": self.fingerprinter.bins_per_octave,
            "peak_neighborhood": self.fingerprinter.peak_neighborhood,
            "target_zone": self.fingerprinter.target_zone,
            "fan_out": self.fingerprinter.fan_out,
        }

        # segment_fps_list[i] = list of adjusted fps for segment i
        segment_fps_list: list[list[Fingerprint]] = [[] for _ in range(total_segments)]
        completed = 0

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {}
            for idx, (pos, seg_data) in enumerate(segments):
                if is_cancelled():
                    break
                segment_start_ms = int((pos / sr) * 1000)
                future = executor.submit(
                    _extract_segment_fps, seg_data, segment_start_ms, fp_kwargs
                )
                future_to_idx[future] = idx

            for future in as_completed(future_to_idx):
                if is_cancelled():
                    # Cancel remaining futures
                    for f in future_to_idx:
                        f.cancel()
                    return [], []

                idx = future_to_idx[future]
                segment_fps_list[idx] = future.result()
                completed += 1
                if progress_callback:
                    progress_callback(
                        completed, total_segments, f"Extracting {completed}/{total_segments}"
                    )

        if is_cancelled():
            return [], []

        total_fps = sum(len(seg) for seg in segment_fps_list)
        log(f"Matching {total_fps} fingerprints ({total_segments} segments)...")

        # Phase 2 — Global tempo-aware matching across all segments
        matches = self._match_global(
            segment_fps_list, progress_callback=progress_callback
        )

        log(f"Found {len(matches)} unique tracks")

        return matches, segment_fps_list

    def _match_global(
        self,
        segment_fps_list: list[list[Fingerprint]],
        progress_callback: callable | None = None,
    ) -> list[Match]:
        """Match all segments globally with tempo-aware search.

        Accumulates all (query_time, db_time) pairs per track across ALL
        segments, then runs tempo search on the combined data. Uses a
        statistical significance test to separate real matches from random
        hash collisions.

        Args:
            segment_fps_list: List of fingerprint lists, one per segment
            progress_callback: Optional callback(current, total, message)

        Returns:
            List of matches (no merge needed — already global)
        """
        logger = logging.getLogger(__name__)

        def log(msg: str) -> None:
            if progress_callback:
                progress_callback(-1, -1, msg)

        # 1. Collect ALL unique hashes across all segments
        all_unique_hashes: set[int] = set()
        for seg_fps in segment_fps_list:
            for fp in seg_fps:
                all_unique_hashes.add(fp.hash)

        if not all_unique_hashes:
            return []

        # 2. Single bulk DB query
        log(f"Querying DB with {len(all_unique_hashes):,} unique hashes...")
        all_db_matches = self.db.query_fingerprints(list(all_unique_hashes))
        logger.info("[Matcher] Global: DB returned %d results", len(all_db_matches))

        if not all_db_matches:
            return []

        # Index DB results by hash
        db_by_hash: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for track_id, time_offset_ms, hash_val in all_db_matches:
            db_by_hash[hash_val].append((track_id, time_offset_ms))

        # 3. Collect all (track_id, query_time, db_time) triples across segments
        #    Pre-group by track_id for efficiency
        log("Building match candidates...")
        track_data: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for seg_fps in segment_fps_list:
            qt_by_hash: dict[int, int] = {}
            for fp in seg_fps:
                if fp.hash not in qt_by_hash:
                    qt_by_hash[fp.hash] = fp.time_offset_ms
            for hash_val, qt in qt_by_hash.items():
                if hash_val in db_by_hash:
                    for db_tid, db_time in db_by_hash[hash_val]:
                        track_data[db_tid].append((qt, db_time))

        # 4. Sort candidate tracks by triple count
        candidate_tracks = [
            (tid, len(pairs))
            for tid, pairs in track_data.items()
            if len(pairs) >= self.min_matches
        ]
        candidate_tracks.sort(key=lambda x: -x[1])

        total_candidates = len(candidate_tracks)
        log(f"Analyzing {total_candidates:,} candidate tracks...")

        # Stretch ratios to try
        stretch_ratios = np.arange(0.920, 1.081, 0.005)
        num_ratios = len(stretch_ratios)
        bin_width = 200  # ms

        matches: list[Match] = []
        track_info_cache: dict[int, dict | None] = {}

        for idx, (track_id, raw_count) in enumerate(candidate_tracks):
            pairs = track_data[track_id]

            arr = np.array(pairs, dtype=np.float64)
            t_qt = arr[:, 0]
            t_dt = arr[:, 1]
            n_pairs = len(pairs)

            # Tempo search: find best stretch ratio
            best_peak = 0
            best_ratio = 1.0
            best_center = 0

            for ratio in stretch_ratios:
                adjusted = t_qt - t_dt * ratio
                adj_min, adj_max = adjusted.min(), adjusted.max()

                if adj_max - adj_min < bin_width:
                    peak = len(adjusted)
                    center = int(np.median(adjusted))
                else:
                    bins = np.arange(adj_min, adj_max + bin_width, bin_width)
                    hist, _ = np.histogram(adjusted, bins=bins)
                    peak_idx = int(np.argmax(hist))
                    peak = int(hist[peak_idx])
                    center = int(bins[peak_idx] + bin_width // 2)

                if peak > best_peak:
                    best_peak = peak
                    best_ratio = float(ratio)
                    best_center = center

            # Statistical significance test (3x noise threshold)
            offset_range_ms = float(
                t_qt.max() - t_qt.min() + t_dt.max() - t_dt.min()
            )
            num_bins = max(offset_range_ms / bin_width, 1.0)
            lam = n_pairs / num_bins
            log_term = math.log(num_bins * num_ratios)
            noise_threshold = lam + 3.0 * math.sqrt(max(lam * log_term, 0.0))
            required = max(3.0 * noise_threshold, 15.0)

            if best_peak < required:
                continue

            # Build cluster around peak
            adjusted = t_qt - t_dt * best_ratio
            half_tol = self.time_tolerance_ms
            cluster_mask = (adjusted >= best_center - half_tol) & (
                adjusted <= best_center + half_tol
            )
            cluster_count = int(cluster_mask.sum())

            cluster_qt = t_qt[cluster_mask]
            cluster_dt = t_dt[cluster_mask]

            query_start_ms = int(cluster_qt.min())
            duration_ms = int(cluster_qt.max() - cluster_qt.min())
            track_start_ms = int(cluster_dt.min())

            # Require cross-segment evidence
            if duration_ms < 15000:
                continue

            # Get track info
            if track_id not in track_info_cache:
                track_info_cache[track_id] = self.db.get_track_info(track_id)
            track_info = track_info_cache[track_id]
            if not track_info:
                continue

            # Confidence: how far above noise the peak is
            significance = best_peak / noise_threshold if noise_threshold > 0 else 0
            confidence = min(1.0, (significance - 1.0) / 4.0)

            match = Match(
                track_id=track_id,
                title=track_info.get("title"),
                artist=track_info.get("artist"),
                filename=track_info.get("filename", ""),
                filepath=track_info.get("filepath", ""),
                confidence=confidence,
                query_start_ms=query_start_ms,
                track_start_ms=max(0, track_start_ms),
                duration_ms=duration_ms,
                match_count=cluster_count,
                time_stretch_ratio=best_ratio,
            )
            matches.append(match)

            if progress_callback and (idx + 1) % 100 == 0:
                progress_callback(
                    idx + 1, total_candidates, f"Matching {idx + 1}/{total_candidates}"
                )

        if progress_callback:
            progress_callback(
                total_candidates, total_candidates,
                f"Matching {total_candidates}/{total_candidates}",
            )

        # Sort by confidence (most significant first)
        matches.sort(key=lambda m: -m.confidence)

        logger.info("[Matcher] Global: %d tracks identified", len(matches))
        return matches

    def _match_segments(
        self,
        segment_fps_list: list[list[Fingerprint]],
        progress_callback: callable | None = None,
    ) -> list[Match]:
        """Match each segment's fingerprints independently against the database.

        Performs a single bulk DB query for all unique hashes across all segments,
        then dispatches results per segment for temporal coherence analysis.
        This avoids repeated DB round-trips (the main bottleneck).

        Args:
            segment_fps_list: List of fingerprint lists, one per segment
            progress_callback: Optional callback(current, total, message)

        Returns:
            List of raw matches from all segments
        """
        import logging
        from collections import defaultdict

        logger = logging.getLogger(__name__)

        total = len(segment_fps_list)

        # Collect ALL unique hashes across all segments
        all_unique_hashes: set[int] = set()
        for seg_fps in segment_fps_list:
            for fp in seg_fps:
                all_unique_hashes.add(fp.hash)

        if not all_unique_hashes:
            return []

        # Single bulk DB query
        logger.info(
            "[Matcher] Querying DB with %d unique hashes from %d segments...",
            len(all_unique_hashes),
            total,
        )
        all_db_matches = self.db.query_fingerprints(list(all_unique_hashes))
        logger.info("[Matcher] DB returned %d results", len(all_db_matches))

        if not all_db_matches:
            return []

        # Index DB results by hash for fast per-segment dispatch
        db_by_hash: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for track_id, time_offset_ms, hash_val in all_db_matches:
            db_by_hash[hash_val].append((track_id, time_offset_ms))

        # Match each segment independently using the pre-fetched DB results
        all_matches: list[Match] = []
        for i, seg_fps in enumerate(segment_fps_list):
            if seg_fps:
                matches = self._match_fingerprints_with_db(seg_fps, db_by_hash)
                if matches:
                    logger.info(
                        "[Matcher] Segment %d/%d: %d fps -> %d matches",
                        i + 1,
                        total,
                        len(seg_fps),
                        len(matches),
                    )
                all_matches.extend(matches)
            if progress_callback:
                progress_callback(i + 1, total, f"Matching {i + 1}/{total}")

        logger.info("[Matcher] Total: %d raw matches from %d segments", len(all_matches), total)
        return all_matches

    def _match_fingerprints_with_db(
        self,
        query_fps: list[Fingerprint],
        db_by_hash: dict[int, list[tuple[int, int]]],
    ) -> list[Match]:
        """Match segment fingerprints using pre-fetched DB results.

        Tempo-aware matching: DJ mixes involve BPM changes, so the time offset
        between query and DB fingerprints is NOT constant but follows
        query_time = mix_start + db_time * stretch_ratio.

        For each candidate track, we search over stretch ratios (0.92–1.08)
        and use histogram peak detection to find the best alignment.

        Args:
            query_fps: Query fingerprints for one segment
            db_by_hash: Pre-fetched DB results indexed by hash

        Returns:
            List of matches
        """
        # Build lookup: hash -> first query time
        query_time_by_hash: dict[int, int] = {}
        for fp in query_fps:
            if fp.hash not in query_time_by_hash:
                query_time_by_hash[fp.hash] = fp.time_offset_ms

        # Gather DB matches for this segment's hashes
        filtered_matches: list[tuple[int, int, int]] = []
        for hash_val, query_time in query_time_by_hash.items():
            if hash_val in db_by_hash:
                for track_id, db_time in db_by_hash[hash_val]:
                    filtered_matches.append((track_id, db_time, hash_val))

        if not filtered_matches:
            return []

        # Convert to numpy arrays for vectorized operations
        db_track_ids = np.array([m[0] for m in filtered_matches], dtype=np.int32)
        db_times = np.array([m[1] for m in filtered_matches], dtype=np.float64)
        db_hashes = np.array([m[2] for m in filtered_matches], dtype=np.int64)

        # Vectorized: get query times for each db match
        query_times = np.array(
            [query_time_by_hash[h] for h in db_hashes], dtype=np.float64
        )

        # Get unique tracks and their best matches
        unique_tracks = np.unique(db_track_ids)

        # For efficiency, only analyze top N tracks by raw match count
        track_counts = [(t, np.sum(db_track_ids == t)) for t in unique_tracks]
        track_counts.sort(key=lambda x: -x[1])
        top_tracks = [t for t, c in track_counts[:100] if c >= self.min_matches]

        # Stretch ratios to try (0.92 to 1.08 in 0.5% steps)
        stretch_ratios = np.arange(0.920, 1.081, 0.005)

        matches: list[Match] = []
        total_query_fps = len(query_fps)
        track_info_cache: dict[int, dict | None] = {}
        bin_width = 200  # ms — wider bins for tempo-adjusted matching

        for track_id_np in top_tracks:
            track_id = int(track_id_np)

            # Get data for this track
            mask = db_track_ids == track_id_np
            track_query_times = query_times[mask]
            track_db_times = db_times[mask]

            if len(track_query_times) < self.min_matches:
                continue

            # Search over stretch ratios for best temporal coherence
            best_peak = 0
            best_ratio = 1.0
            best_center = 0

            for ratio in stretch_ratios:
                adjusted = track_query_times - track_db_times * ratio
                adj_min, adj_max = adjusted.min(), adjusted.max()

                if adj_max - adj_min < bin_width:
                    peak = len(adjusted)
                    center = int(np.median(adjusted))
                else:
                    bins = np.arange(adj_min, adj_max + bin_width, bin_width)
                    hist, _ = np.histogram(adjusted, bins=bins)
                    idx = int(np.argmax(hist))
                    peak = int(hist[idx])
                    center = int(bins[idx] + bin_width // 2)

                if peak > best_peak:
                    best_peak = peak
                    best_ratio = float(ratio)
                    best_center = center

            # Quality gate: require min_matches in best bin
            if best_peak < self.min_matches:
                continue

            # Build cluster around peak with best ratio
            adjusted = track_query_times - track_db_times * best_ratio
            half_tol = self.time_tolerance_ms
            cluster_mask = (adjusted >= best_center - half_tol) & (
                adjusted <= best_center + half_tol
            )
            cluster_count = int(cluster_mask.sum())

            # Position in the MIX
            cluster_qt = track_query_times[cluster_mask]
            cluster_dt = track_db_times[cluster_mask]
            query_start_ms = int(cluster_qt.min())
            duration_ms = int(cluster_qt.max() - cluster_qt.min())

            # Position in the ORIGINAL TRACK
            track_start_ms = int(cluster_dt.min())

            # Get track info (cached)
            if track_id not in track_info_cache:
                track_info_cache[track_id] = self.db.get_track_info(track_id)
            track_info = track_info_cache[track_id]

            if not track_info:
                continue

            # Confidence based on peak bin count
            match_ratio = best_peak / total_query_fps
            confidence = min(1.0, match_ratio * 5)

            match = Match(
                track_id=track_id,
                title=track_info.get("title"),
                artist=track_info.get("artist"),
                filename=track_info.get("filename", ""),
                filepath=track_info.get("filepath", ""),
                confidence=confidence,
                query_start_ms=query_start_ms,
                track_start_ms=max(0, track_start_ms),
                duration_ms=duration_ms,
                match_count=cluster_count,
                time_stretch_ratio=best_ratio,
            )
            matches.append(match)

        # Sort by match count (most reliable metric)
        matches.sort(key=lambda m: -m.match_count)

        # Filter by minimum confidence and keep top results per segment
        matches = [m for m in matches if m.confidence >= self.min_confidence][:50]

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

        After merging, filters out weak matches that were only found in a
        single segment (likely false positives from hash collisions).

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
            segment_count = 1

            for m in track_matches[1:]:
                # Check if overlapping (within 30 seconds)
                if m.query_start_ms - (current.query_start_ms + current.duration_ms) < 30000:
                    # Merge: extend duration, sum match count, average confidence
                    new_end = max(
                        current.query_start_ms + current.duration_ms,
                        m.query_start_ms + m.duration_ms,
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
                    segment_count += 1
                else:
                    if segment_count >= 2:
                        merged.append(current)
                    current = m
                    segment_count = 1

            if segment_count >= 2:
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
