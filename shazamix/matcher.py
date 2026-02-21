"""Match audio fingerprints against the database to identify tracks.

Public API
----------
``Matcher.analyze_mix(mix_path, ...)``
    Full-mix analysis: extracts fingerprints over overlapping segments and
    returns all identified tracks.  Call this from ``AnalyzeWorker``.

``Matcher.match_segment(mix_path, start_ms, end_ms, ...)``
    Targeted re-analysis of a single time range.  Designed for re-analysis of
    segments missed by ``analyze_mix()``.  Uses a two-stage pipeline:

    1. **Fingerprint + time-stretch**: tries multiple stretch rates (default
       ±35%, step 5%) to handle key-locked mixes.
    2. **MFCC+chroma fallback**: dual-feature timbral similarity when
       fingerprinting fails.  Requires ``precompute_audio_features()`` to have
       been run on the library beforehand.

``Matcher.precompute_audio_features(progress_callback, cancelled)``
    Pre-computes MFCC and chroma summaries for all indexed tracks.  Must be run
    once before ``match_segment()`` can use its MFCC fallback.

Internal pipeline
-----------------
1. Extract fingerprints from the query audio (mix segment)
2. Query the database for matching hashes
3. Use temporal coherence to validate matches
4. Return ranked list of matching tracks with confidence scores
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .database import FingerprintDB
from .fingerprint import Fingerprint, Fingerprinter

logger = logging.getLogger(__name__)


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

    def match_segment(
        self,
        mix_path: str,
        start_ms: int,
        end_ms: int,
        stretch_min: float = 0.85,
        stretch_max: float = 1.35,
        stretch_step: float = 0.05,
        progress_callback: Callable[..., object] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> Match | None:
        """Identify the track in a specific segment of a mix.

        Designed for re-analysis of segments not matched by analyze_mix().
        Handles key-lock (master-tempo) scenarios where the DJ changed the
        tempo but preserved the original pitch.

        Strategy:
        1. **Fingerprint matching** — pre-processes the audio with
           ``librosa.effects.time_stretch()`` at multiple candidate rates
           before extracting fingerprints.  Fast and precise when the tempo
           shift is moderate.
        2. **MFCC fallback** — if fingerprint matching fails (no match or
           very low confidence), falls back to timbral similarity using
           pre-computed MFCC summaries.  More robust to extreme tempo changes
           but requires ``precompute_audio_features()`` to have been run.

        Args:
            mix_path: Path to the mix audio file
            start_ms: Start of the segment to analyse (milliseconds)
            end_ms: End of the segment to analyse (milliseconds)
            stretch_min: Lower bound for time-stretch rate (default 0.85)
            stretch_max: Upper bound for time-stretch rate (default 1.35)
            stretch_step: Step size for time-stretch rate search (default 0.05)
            progress_callback: Optional callback(current, total, message)
            cancelled: Optional callable returning True to abort early

        Returns:
            Best Match found, or None if no match exceeds the confidence threshold
        """
        import librosa

        def log(msg: str) -> None:
            if progress_callback:
                progress_callback(-1, -1, msg)

        start_s = start_ms / 1000.0
        duration_s = (end_ms - start_ms) / 1000.0

        log(f"Loading segment [{start_ms}ms–{end_ms}ms]…")
        y, _ = librosa.load(
            mix_path,
            sr=self.fingerprinter.sample_rate,
            mono=True,
            offset=start_s,
            duration=duration_s,
        )

        if len(y) == 0:
            return None

        # ------------------------------------------------------------------
        # Stage 1: Fingerprint matching with time-stretch pre-processing
        # ------------------------------------------------------------------
        log("Stage 1: Fingerprint matching…")
        rates = np.arange(stretch_min, stretch_max + stretch_step / 2, stretch_step)
        total_rates = len(rates)

        best_match: Match | None = None
        best_match_count = 0

        for i, rate in enumerate(rates):
            if cancelled and cancelled():
                return None
            rate = float(round(rate, 4))
            log(f"Trying time-stretch rate {rate:.2f} ({i + 1}/{total_rates})…")

            # Time-stretch the audio (or skip if rate ~= 1.0)
            if abs(rate - 1.0) < 0.01:
                y_stretched = y
            else:
                y_stretched = librosa.effects.time_stretch(y, rate=rate)

            # Extract fingerprints from the (possibly corrected) audio
            query_fps = self.fingerprinter.extract_fingerprints_from_array(y_stretched)
            if not query_fps:
                continue

            # Query DB with hashes from this rate
            unique_hashes = list({fp.hash for fp in query_fps})
            db_results = self.db.query_fingerprints(unique_hashes)
            if not db_results:
                continue

            db_by_hash: dict[int, list[tuple[int, int]]] = {}
            for track_id, time_offset_ms, hash_val in db_results:
                if hash_val not in db_by_hash:
                    db_by_hash[hash_val] = []
                db_by_hash[hash_val].append((track_id, time_offset_ms))

            # Run temporal coherence matching (ratio=1.0 since audio is
            # already corrected; small ratios around 1.0 for fine-tuning)
            fine_ratios = np.arange(0.96, 1.041, 0.005)
            matches = self._match_fingerprints_with_db(
                query_fps, db_by_hash, stretch_ratios=fine_ratios
            )

            if matches and matches[0].match_count > best_match_count:
                best_match = matches[0]
                best_match_count = matches[0].match_count
                # Record the overall stretch: audio was corrected by `rate`,
                # then fine-tuned by the match's ratio.
                best_match.time_stretch_ratio = rate * best_match.time_stretch_ratio
                log(
                    f"  → candidate: {best_match.artist} – {best_match.title} "
                    f"(count={best_match.match_count}, conf={best_match.confidence:.2f})"
                )

        if best_match:
            log(
                f"Fingerprint match: {best_match.artist} – {best_match.title} "
                f"(stretch={best_match.time_stretch_ratio:.3f}, "
                f"conf={best_match.confidence:.2f})"
            )
            return best_match

        # ------------------------------------------------------------------
        # Stage 2: MFCC timbral similarity fallback
        # ------------------------------------------------------------------
        log("Fingerprint matching failed. Trying MFCC timbral similarity…")
        mfcc_match = self.match_segment_by_mfcc(
            mix_path,
            start_ms,
            end_ms,
            progress_callback=progress_callback,
            preloaded_audio=y,
            cancelled=cancelled,
        )
        return mfcc_match

    @staticmethod
    def compute_mfcc_summary(y: np.ndarray, sr: int = 22050) -> np.ndarray:
        """Compute a compact MFCC summary vector for an audio signal.

        The summary concatenates mean, standard-deviation and delta-mean of
        20 MFCCs, producing a 60-dimensional feature vector that captures the
        timbral signature of the audio.

        Args:
            y: Audio time series (mono)
            sr: Sample rate

        Returns:
            60-element float32 numpy array
        """
        import librosa

        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20, hop_length=2048)
        summary = np.concatenate(
            [
                mfcc.mean(axis=1),
                mfcc.std(axis=1),
                np.diff(mfcc, axis=1).mean(axis=1),
            ]
        )
        return summary.astype(np.float32)

    @staticmethod
    def compute_chroma_summary(y: np.ndarray, sr: int = 22050) -> np.ndarray:
        """Compute a compact chroma summary vector for an audio signal.

        The summary concatenates mean, standard-deviation and delta-mean of
        12 chroma bins, producing a 36-dimensional feature vector that captures
        the harmonic/pitch-class content of the audio.

        Args:
            y: Audio time series (mono)
            sr: Sample rate

        Returns:
            36-element float32 numpy array
        """
        import librosa

        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=2048)
        summary = np.concatenate(
            [
                chroma.mean(axis=1),
                chroma.std(axis=1),
                np.diff(chroma, axis=1).mean(axis=1),
            ]
        )
        return summary.astype(np.float32)

    @staticmethod
    def _compute_combined_frame_features(
        y: np.ndarray,
        sr: int,
        hop: int,
    ) -> np.ndarray:
        """Compute combined chroma+MFCC features per frame.

        Returns a (32, T) array where each column is a unit-normalised vector
        combining 12-dim CQT chroma and 20-dim MFCC.  The two feature sets are
        each L2-normalised before concatenation so that neither dominates.

        This combined representation captures both harmonic structure (chroma)
        and timbral character (MFCC), providing much stronger discrimination
        between tracks with similar harmonic content but different timbre.
        """
        import librosa

        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
        mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=hop, n_mfcc=20)

        cn = np.linalg.norm(chroma, axis=0, keepdims=True)
        cn[cn == 0] = 1.0
        mn = np.linalg.norm(mfcc, axis=0, keepdims=True)
        mn[mn == 0] = 1.0

        combined = np.concatenate([chroma / cn, mfcc / mn], axis=0)

        fn = np.linalg.norm(combined, axis=0, keepdims=True)
        fn[fn == 0] = 1.0
        return combined / fn

    @staticmethod
    def _best_sustained_run(
        query_feat: np.ndarray,
        ref_feat: np.ndarray,
        slide_step: int,
        min_overlap: int,
        threshold: float,
    ) -> tuple[int, float]:
        """Find the longest sustained run of frame similarity above threshold.

        Slides *ref_feat* along *query_feat* and returns the length of the
        longest contiguous run of frames where cosine similarity >= *threshold*,
        together with the average similarity within that run.

        Returns:
            ``(best_run_length, avg_similarity)``.  ``(0, 0.0)`` if no run.
        """
        nq = query_feat.shape[1]
        nr = ref_feat.shape[1]
        if nr < min_overlap:
            return 0, 0.0

        max_run = 0
        avg_at_best = 0.0

        for offset in range(-nq + min_overlap, nr, slide_step):
            mix_s = max(0, -offset)
            ref_s = max(0, offset)
            overlap = min(nq - mix_s, nr - ref_s)
            if overlap < min_overlap:
                continue

            sims = np.sum(
                query_feat[:, mix_s : mix_s + overlap] * ref_feat[:, ref_s : ref_s + overlap],
                axis=0,
            )
            above = sims >= threshold
            boundaries = np.where(np.diff(np.concatenate(([False], above, [False])).astype(int)))[0]
            if len(boundaries) >= 2:
                runs = boundaries[1::2] - boundaries[::2]
                run_len = int(runs.max())
                if run_len > max_run:
                    ri = int(runs.argmax())
                    rs = boundaries[ri * 2]
                    re_ = boundaries[ri * 2 + 1]
                    max_run = run_len
                    avg_at_best = float(sims[rs:re_].mean())

        return max_run, avg_at_best

    def _alignment_rerank(
        self,
        candidates: list[tuple[int, float]],
        query_features: np.ndarray,
        sr: int,
        hop: int,
        sim_threshold: float,
        slide_step: int,
        min_overlap: int,
        feature_type: str,
        log: callable | None = None,
        log_every: int = 10,
    ) -> list[tuple[int, int, float]]:
        """Re-rank candidates by full-alignment sustained similarity.

        For each candidate, loads the reference audio, computes per-frame
        features (combined or chroma-only), and slides the reference against
        the query to find the longest run of consecutive frames above
        *sim_threshold*.

        Args:
            candidates: List of (track_id, compact_score) from Stage 2a
            query_features: Pre-computed query features (D, T) array
            sr: Sample rate
            hop: Hop length for feature computation
            sim_threshold: Minimum cosine similarity threshold
            slide_step: Frames between alignment offsets
            min_overlap: Minimum overlap in frames
            feature_type: ``"combined"`` for chroma+MFCC, ``"chroma"``
                for chroma-only
            log: Optional logging callback
            log_every: Log progress every N candidates

        Returns:
            Sorted list of (track_id, best_run, avg_sim) tuples,
            descending by best_run then avg_sim.
        """
        import librosa

        nq = query_features.shape[1]
        results: list[tuple[int, int, float]] = []

        for idx, (track_id, _compact_score) in enumerate(candidates):
            track_info = self.db.get_track_info(track_id)
            if not track_info:
                continue
            filepath = track_info.get("filepath", "")
            if not filepath:
                continue

            try:
                y_ref, _ = librosa.load(filepath, sr=sr, mono=True)
                if len(y_ref) == 0:
                    continue

                if feature_type == "combined":
                    ref_features = self._compute_combined_frame_features(
                        y_ref,
                        sr,
                        hop,
                    )
                else:
                    ref_chroma = librosa.feature.chroma_cqt(
                        y=y_ref,
                        sr=sr,
                        hop_length=hop,
                    )
                    rn = np.linalg.norm(ref_chroma, axis=0, keepdims=True)
                    rn[rn == 0] = 1.0
                    ref_features = ref_chroma / rn

                nr = ref_features.shape[1]
                if nr < min_overlap:
                    continue

                max_run_this = 0
                avg_at_best = 0.0

                for offset in range(-nq + min_overlap, nr, slide_step):
                    mix_s = max(0, -offset)
                    ref_s = max(0, offset)
                    overlap = min(nq - mix_s, nr - ref_s)
                    if overlap < min_overlap:
                        continue

                    sims = np.sum(
                        query_features[:, mix_s : mix_s + overlap]
                        * ref_features[:, ref_s : ref_s + overlap],
                        axis=0,
                    )
                    above = sims >= sim_threshold
                    boundaries = np.where(
                        np.diff(np.concatenate(([False], above, [False])).astype(int))
                    )[0]
                    if len(boundaries) >= 2:
                        runs = boundaries[1::2] - boundaries[::2]
                        run_len = int(runs.max())
                        if run_len > max_run_this:
                            ri = int(runs.argmax())
                            rs = boundaries[ri * 2]
                            re = boundaries[ri * 2 + 1]
                            max_run_this = run_len
                            avg_at_best = float(sims[rs:re].mean())

                if max_run_this > 0:
                    results.append((track_id, max_run_this, avg_at_best))

            except Exception:
                continue

            if log and (idx + 1) % log_every == 0:
                log(f"  Re-ranked {idx + 1}/{len(candidates)} candidates…")

        results.sort(key=lambda r: (-r[1], -r[2]))
        return results

    def match_segment_by_mfcc(
        self,
        mix_path: str,
        start_ms: int,
        end_ms: int,
        progress_callback: Callable[..., object] | None = None,
        preloaded_audio: np.ndarray | None = None,
        top_n: int = 200,
        cancelled: Callable[[], bool] | None = None,
    ) -> Match | None:
        """Identify a track by audio feature similarity (two-stage).

        **Stage 2a** — combined MFCC+chroma screening using compact summaries
        (60-dim MFCC + 36-dim chroma, normalised and concatenated).
        Selects *top_n* candidates.

        **Stage 2b** — dual-feature full-alignment re-ranking.  For each
        candidate, loads the reference audio once and computes both:

        - *Combined chroma+MFCC* per-frame features (threshold 0.80) —
          catches timbral matches.
        - *Chroma-only* per-frame features (threshold 0.92) — catches
          harmonic matches among same-genre tracks.

        The final score is ``min(combined_run, chroma_run)``.  This
        eliminates false positives that score well in only one metric
        (e.g. similar timbre but wrong harmony, or vice versa).

        Requires that ``precompute_audio_features()`` has been run beforehand.

        Args:
            mix_path: Path to the mix audio file
            start_ms: Start of the segment (milliseconds)
            end_ms: End of the segment (milliseconds)
            progress_callback: Optional callback(current, total, message)
            preloaded_audio: Optional pre-loaded audio array (mono, at
                ``self.fingerprinter.sample_rate``). Avoids double loading.
            top_n: Number of candidates from compact screening (default 200)
            cancelled: Optional callable returning True to abort early

        Returns:
            Best Match found, or None
        """
        import librosa

        sr = self.fingerprinter.sample_rate

        def log(msg: str) -> None:
            if progress_callback:
                progress_callback(-1, -1, msg)

        # Load both MFCC and chroma summaries
        log("Loading pre-computed audio feature summaries…")
        mfcc_summaries = self.db.get_all_audio_features("mfcc_summary")
        chroma_summaries = self.db.get_all_audio_features("chroma_summary")
        both_ids = set(mfcc_summaries.keys()) & set(chroma_summaries.keys())
        if not both_ids:
            log("No audio feature summaries in database. " "Run feature pre-computation first.")
            return None

        log(f"Loaded features for {len(both_ids)} tracks")

        if preloaded_audio is not None:
            y = preloaded_audio
        else:
            start_s = start_ms / 1000.0
            duration_s = (end_ms - start_ms) / 1000.0
            log(f"Loading mix segment [{start_ms}ms–{end_ms}ms]…")
            y, _ = librosa.load(
                mix_path,
                sr=sr,
                mono=True,
                offset=start_s,
                duration=duration_s,
            )

        if len(y) == 0:
            return None

        # ------------------------------------------------------------------
        # Stage 2a: Combined MFCC+Chroma screening
        # ------------------------------------------------------------------
        log("Stage 2a: Combined MFCC+Chroma screening…")
        q_mfcc = self.compute_mfcc_summary(y, sr)
        q_chroma = self.compute_chroma_summary(y, sr)
        q_mfcc_norm = np.linalg.norm(q_mfcc)
        q_chroma_norm = np.linalg.norm(q_chroma)
        if q_mfcc_norm == 0 or q_chroma_norm == 0:
            return None

        # Normalise each feature set to unit length before concatenating
        q_combined = np.concatenate([q_mfcc / q_mfcc_norm, q_chroma / q_chroma_norm])
        q_combined_norm = np.linalg.norm(q_combined)

        scores: list[tuple[int, float]] = []
        for track_id in both_ids:
            m = mfcc_summaries[track_id]
            c = chroma_summaries[track_id]
            mn = np.linalg.norm(m)
            cn = np.linalg.norm(c)
            if mn == 0 or cn == 0:
                continue
            ref_combined = np.concatenate([m / mn, c / cn])
            rn = np.linalg.norm(ref_combined)
            cos_sim = float(np.dot(q_combined, ref_combined) / (q_combined_norm * rn))
            scores.append((track_id, cos_sim))

        if not scores:
            return None

        scores.sort(key=lambda x: -x[1])
        candidates = scores[:top_n]
        log(
            f"Top {len(candidates)} candidates selected "
            f"(best={candidates[0][1]:.4f}, worst={candidates[-1][1]:.4f})"
        )

        hop = 2048  # ~0.093s per frame
        slide_step = 15
        min_overlap = 30

        # ------------------------------------------------------------------
        # Stage 2b: Dual-feature sustained re-ranking
        # ------------------------------------------------------------------
        # For each candidate, load audio once and compute BOTH:
        #   combined chroma+MFCC (threshold 0.80) → timbral match
        #   chroma-only          (threshold 0.92) → harmonic match
        # Score = min(combined_run, chroma_run) — eliminates false
        # positives that score well in only one metric.
        # ------------------------------------------------------------------
        log(f"Stage 2b: Sustained chroma+MFCC re-ranking " f"({len(candidates)} tracks)…")

        query_combined = self._compute_combined_frame_features(y, sr, hop)
        query_chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
        qn = np.linalg.norm(query_chroma, axis=0, keepdims=True)
        qn[qn == 0] = 1.0
        query_chroma_normed = query_chroma / qn

        results: list[tuple[int, int, float]] = []

        for idx, (track_id, _compact_score) in enumerate(candidates):
            if cancelled and cancelled():
                log("Re-ranking cancelled.")
                return None

            track_info = self.db.get_track_info(track_id)
            if not track_info:
                continue
            filepath = track_info.get("filepath", "")
            if not filepath:
                continue

            try:
                y_ref, _ = librosa.load(filepath, sr=sr, mono=True)
                if len(y_ref) == 0:
                    continue

                # Compute both feature types from the same audio load
                ref_combined = self._compute_combined_frame_features(
                    y_ref,
                    sr,
                    hop,
                )
                ref_chroma = librosa.feature.chroma_cqt(
                    y=y_ref,
                    sr=sr,
                    hop_length=hop,
                )
                rn = np.linalg.norm(ref_chroma, axis=0, keepdims=True)
                rn[rn == 0] = 1.0
                ref_chroma_normed = ref_chroma / rn

                if ref_combined.shape[1] < min_overlap:
                    continue

                comb_run, comb_sim = self._best_sustained_run(
                    query_combined,
                    ref_combined,
                    slide_step,
                    min_overlap,
                    0.80,
                )
                chro_run, chro_sim = self._best_sustained_run(
                    query_chroma_normed,
                    ref_chroma_normed,
                    slide_step,
                    min_overlap,
                    0.92,
                )

                score = min(comb_run, chro_run)
                avg_sim = min(comb_sim, chro_sim) if score > 0 else 0.0

                if score > 0:
                    results.append((track_id, score, avg_sim))

            except Exception:
                logger.debug(
                    "Failed to load/process track %d (%s), skipping",
                    track_id,
                    filepath,
                    exc_info=True,
                )
                continue

            if (idx + 1) % 20 == 0:
                log(f"  Re-ranked {idx + 1}/{len(candidates)} candidates…")

        results.sort(key=lambda r: (-r[1], -r[2]))

        if not results or results[0][1] == 0:
            log("Re-ranking: no sustained match found.")
            return None

        best = results[0]
        track_info = self.db.get_track_info(best[0])
        if not track_info:
            return None

        run_seconds = best[1] * hop / sr
        log(
            f"Match: {track_info.get('artist', '?')} – "
            f"{track_info.get('title', '?')} "
            f"(run={best[1]} frames/{run_seconds:.0f}s, "
            f"avg_sim={best[2]:.3f})"
        )

        return Match(
            track_id=best[0],
            title=track_info.get("title"),
            artist=track_info.get("artist"),
            filename=track_info.get("filename", ""),
            filepath=track_info.get("filepath", ""),
            confidence=best[2],
            query_start_ms=start_ms,
            track_start_ms=0,
            duration_ms=end_ms - start_ms,
            match_count=0,
            time_stretch_ratio=1.0,
        )

    def precompute_audio_features(
        self,
        progress_callback: callable | None = None,
        max_workers: int = 1,
        cancelled: callable | None = None,
    ) -> int:
        """Compute and store MFCC and chroma summaries for all indexed tracks.

        Reads 30 seconds from the middle of each track, computes MFCC and
        chroma summaries, and stores them in the ``audio_features`` table.
        Tracks that already have both summaries are skipped.

        Args:
            progress_callback: Optional callback(current, total, message)
            max_workers: Not used yet (reserved for future parallelism)
            cancelled: Optional callable returning True to abort

        Returns:
            Number of new summaries computed
        """
        import librosa

        def log(current: int, total: int, msg: str) -> None:
            if progress_callback:
                progress_callback(current, total, msg)

        tracks = self.db.get_all_indexed_tracks()
        # Filter out tracks that already have both summaries
        existing_mfcc = self.db.get_all_audio_features("mfcc_summary")
        existing_chroma = self.db.get_all_audio_features("chroma_summary")
        to_process = [
            t for t in tracks if t["id"] not in existing_mfcc or t["id"] not in existing_chroma
        ]

        total = len(to_process)
        log(0, total, f"Computing audio features for {total} tracks…")

        computed = 0
        for i, track in enumerate(to_process):
            if cancelled and cancelled():
                break

            filepath = track.get("filepath", "")
            if not filepath:
                continue

            try:
                y, sr_loaded = librosa.load(
                    filepath,
                    sr=self.fingerprinter.sample_rate,
                    mono=True,
                    duration=30.0,
                    offset=15.0,  # start 15s in to skip intros
                )
                if len(y) < self.fingerprinter.sample_rate * 5:
                    # Track too short, load from beginning
                    y, sr_loaded = librosa.load(
                        filepath,
                        sr=self.fingerprinter.sample_rate,
                        mono=True,
                        duration=30.0,
                    )

                if len(y) == 0:
                    continue

                sr = self.fingerprinter.sample_rate
                tid = track["id"]

                if tid not in existing_mfcc:
                    mfcc_summary = self.compute_mfcc_summary(y, sr)
                    self.db.store_audio_features(tid, "mfcc_summary", mfcc_summary)

                if tid not in existing_chroma:
                    chroma_summary = self.compute_chroma_summary(y, sr)
                    self.db.store_audio_features(tid, "chroma_summary", chroma_summary)

                computed += 1
            except Exception:
                pass  # Skip tracks that can't be loaded

            if (i + 1) % 50 == 0 or i + 1 == total:
                log(i + 1, total, f"Computed {computed}/{i + 1} feature sets…")

        log(total, total, f"Done: {computed} new feature sets computed")
        return computed

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
        from concurrent.futures import ProcessPoolExecutor, as_completed

        def is_cancelled() -> bool:
            return cancelled is not None and cancelled()

        def log(msg: str) -> None:
            if progress_callback:
                progress_callback(-1, -1, msg)

        # Fast path: reuse precomputed fingerprints (skip audio + extraction)
        if precomputed_fingerprints is not None:
            log(
                f"Using cached fingerprints ({len(precomputed_fingerprints)} segments), matching..."
            )
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
        matches = self._match_global(segment_fps_list, progress_callback=progress_callback)

        log(f"Found {len(matches)} unique tracks")

        return matches, segment_fps_list

    def _match_global(
        self,
        segment_fps_list: list[list[Fingerprint]],
        progress_callback: callable | None = None,
        stretch_ratios: np.ndarray | None = None,
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
            (tid, len(pairs)) for tid, pairs in track_data.items() if len(pairs) >= self.min_matches
        ]
        candidate_tracks.sort(key=lambda x: -x[1])

        total_candidates = len(candidate_tracks)
        log(f"Analyzing {total_candidates:,} candidate tracks...")

        # Stretch ratios to try
        if stretch_ratios is None:
            stretch_ratios = np.arange(0.920, 1.081, 0.005)
        num_ratios = len(stretch_ratios)
        bin_width = 200  # ms

        matches: list[Match] = []
        track_info_cache: dict[int, dict | None] = {}

        for idx, (track_id, _raw_count) in enumerate(candidate_tracks):
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
            offset_range_ms = float(t_qt.max() - t_qt.min() + t_dt.max() - t_dt.min())
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
                total_candidates,
                total_candidates,
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
        stretch_ratios: np.ndarray | None = None,
        min_confidence: float | None = None,
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
        for hash_val, _query_time in query_time_by_hash.items():
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
        query_times = np.array([query_time_by_hash[h] for h in db_hashes], dtype=np.float64)

        # Get unique tracks and their best matches
        unique_tracks = np.unique(db_track_ids)

        # For efficiency, only analyze top N tracks by raw match count
        track_counts = [(t, np.sum(db_track_ids == t)) for t in unique_tracks]
        track_counts.sort(key=lambda x: -x[1])
        top_tracks = [t for t, c in track_counts[:100] if c >= self.min_matches]

        # Stretch ratios to try (0.92 to 1.08 in 0.5% steps by default)
        if stretch_ratios is None:
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
        threshold = min_confidence if min_confidence is not None else self.min_confidence
        matches = [m for m in matches if m.confidence >= threshold][:50]

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

        for _track_id, track_matches in by_track.items():
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
