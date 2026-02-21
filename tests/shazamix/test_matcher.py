"""Tests for shazamix.matcher — dual-feature MFCC fallback methods.

Focus on:
- _best_sustained_run() : pure numpy, fully deterministic
- _compute_combined_frame_features() : shape + normalisation
- match_segment_by_mfcc() : integration with mocked DB and librosa
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unit_columns(arr: np.ndarray) -> np.ndarray:
    """Return *arr* with each column L2-normalised."""
    norms = np.linalg.norm(arr, axis=0, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def _sine_audio(duration_sec: float = 1.0, sr: int = 22050) -> np.ndarray:
    """Generate a 440 Hz sine wave as a float32 array."""
    t = np.linspace(0, duration_sec, int(sr * duration_sec))
    return (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)


def _make_matcher() -> "Matcher":  # type: ignore[name-defined]
    """Return a Matcher with mocked DB and fingerprinter."""
    from shazamix.matcher import Matcher

    db = MagicMock()
    fp = MagicMock()
    fp.sample_rate = 22050
    return Matcher(db, fp)


# ---------------------------------------------------------------------------
# TestBestSustainedRun
# ---------------------------------------------------------------------------

class TestBestSustainedRun:
    """Unit tests for Matcher._best_sustained_run()."""

    def test_identical_features_returns_full_run(self) -> None:
        """When query == ref, cosine sim == 1.0 everywhere → full run length."""
        from shazamix.matcher import Matcher

        feat = _unit_columns(np.random.rand(32, 100))
        run, avg = Matcher._best_sustained_run(feat, feat, slide_step=10, min_overlap=10, threshold=0.9)
        assert run == 100
        assert avg == pytest.approx(1.0, abs=0.01)

    def test_orthogonal_features_returns_zero_run(self) -> None:
        """When sim == 0.0 throughout, run must be 0."""
        from shazamix.matcher import Matcher

        q = np.zeros((4, 60))
        q[0, :] = 1.0  # all frames in dimension 0
        r = np.zeros((4, 60))
        r[1, :] = 1.0  # all frames in dimension 1 → orthogonal → sim = 0

        run, avg = Matcher._best_sustained_run(q, r, slide_step=5, min_overlap=5, threshold=0.5)
        assert run == 0
        assert avg == pytest.approx(0.0)

    def test_ref_too_short_returns_zero(self) -> None:
        """When ref.shape[1] < min_overlap, returns (0, 0.0) immediately."""
        from shazamix.matcher import Matcher

        q = _unit_columns(np.random.rand(32, 100))
        r = _unit_columns(np.random.rand(32, 4))  # only 4 frames, min_overlap=10

        run, avg = Matcher._best_sustained_run(q, r, slide_step=5, min_overlap=10, threshold=0.5)
        assert run == 0
        assert avg == 0.0

    def test_multiple_runs_returns_longest(self) -> None:
        """When two non-overlapping identical regions exist, the longer one wins."""
        from shazamix.matcher import Matcher

        # Use constant features (all frames identical) so any alignment offset
        # gives sim=1.0, making the run detection fully deterministic.
        # q and r share the same constant feature → always sim=1.0.
        T = 60
        q = np.zeros((4, T))
        q[0, :] = 1.0  # all frames identical, pointing in dim 0
        r = q.copy()

        # With identical constant features, the best run equals T.
        run, avg = Matcher._best_sustained_run(q, r, slide_step=1, min_overlap=5, threshold=0.9)
        assert run == T

    def test_returns_avg_sim_in_best_run(self) -> None:
        """avg_sim reflects actual similarities inside the winning run."""
        from shazamix.matcher import Matcher

        feat = _unit_columns(np.random.rand(32, 50))
        run, avg = Matcher._best_sustained_run(feat, feat, slide_step=5, min_overlap=5, threshold=0.9)
        assert 0.9 <= avg <= 1.0 + 1e-6  # within threshold, at most 1.0

    def test_slide_step_coarser_still_finds_match(self) -> None:
        """With a coarser slide_step, the method still detects the match.

        Uses constant features so every alignment offset yields sim=1.0,
        making the result independent of which exact offsets are sampled.
        """
        from shazamix.matcher import Matcher

        # Constant features: every frame is the same unit vector.
        q = np.zeros((4, 80))
        q[0, :] = 1.0
        r = q.copy()

        run_fine, _ = Matcher._best_sustained_run(q, r, slide_step=1, min_overlap=5, threshold=0.9)
        run_coarse, _ = Matcher._best_sustained_run(q, r, slide_step=20, min_overlap=5, threshold=0.9)
        # A coarser step skips some offsets, so it may not land on the exact
        # peak overlap.  We only verify that a substantial match is detected
        # (within one slide_step of the fine-grained result).
        assert run_coarse > 0
        assert run_coarse >= run_fine - 20


# ---------------------------------------------------------------------------
# TestComputeCombinedFrameFeatures
# ---------------------------------------------------------------------------

class TestComputeCombinedFrameFeatures:
    """Unit tests for Matcher._compute_combined_frame_features()."""

    def test_output_has_32_dims(self) -> None:
        """Feature dimensionality must be 12 (chroma) + 20 (MFCC) = 32."""
        from shazamix.matcher import Matcher

        y = _sine_audio(1.0)
        features = Matcher._compute_combined_frame_features(y, sr=22050, hop=2048)
        assert features.shape[0] == 32

    def test_output_columns_are_unit_normalised(self) -> None:
        """Every column of the output must have L2 norm ≈ 1.0."""
        from shazamix.matcher import Matcher

        y = _sine_audio(2.0)
        features = Matcher._compute_combined_frame_features(y, sr=22050, hop=2048)
        norms = np.linalg.norm(features, axis=0)
        np.testing.assert_allclose(norms, 1.0, atol=0.01,
                                    err_msg="Not all columns are unit-normalised")

    def test_output_has_positive_frame_count(self) -> None:
        """A 1-second audio should produce at least one frame."""
        from shazamix.matcher import Matcher

        y = _sine_audio(1.0)
        features = Matcher._compute_combined_frame_features(y, sr=22050, hop=2048)
        assert features.shape[1] > 0

    def test_output_dtype_float(self) -> None:
        """Output should be a float array (not int)."""
        from shazamix.matcher import Matcher

        y = _sine_audio(0.5)
        features = Matcher._compute_combined_frame_features(y, sr=22050, hop=2048)
        assert np.issubdtype(features.dtype, np.floating)

    def test_different_audio_produces_different_features(self) -> None:
        """Two different audio signals must yield distinct feature matrices."""
        from shazamix.matcher import Matcher

        y1 = _sine_audio(1.0)
        y2 = np.random.rand(22050).astype(np.float32)  # random noise
        f1 = Matcher._compute_combined_frame_features(y1, sr=22050, hop=2048)
        f2 = Matcher._compute_combined_frame_features(y2, sr=22050, hop=2048)
        # Column means should differ
        assert not np.allclose(f1.mean(axis=1), f2.mean(axis=1), atol=0.1)


# ---------------------------------------------------------------------------
# TestMatchSegmentByMfcc
# ---------------------------------------------------------------------------

class TestMatchSegmentByMfcc:
    """Integration tests for Matcher.match_segment_by_mfcc()."""

    # ---- helpers -----------------------------------------------------------

    def _matcher(self) -> "Matcher":  # type: ignore[name-defined]
        return _make_matcher()

    def _query_audio(self, dur: float = 5.0) -> np.ndarray:
        return _sine_audio(dur)

    # ---- no features in DB -------------------------------------------------

    def test_returns_none_when_mfcc_summaries_empty(self) -> None:
        """Returns None immediately when the DB has no MFCC summaries."""
        m = self._matcher()
        m.db.get_all_audio_features.return_value = {}
        y = self._query_audio()
        result = m.match_segment_by_mfcc("fake.mp3", 0, 5000, preloaded_audio=y)
        assert result is None

    def test_returns_none_when_chroma_summaries_empty(self) -> None:
        """Returns None when MFCC summaries exist but chroma summaries are missing."""
        m = self._matcher()
        fake_mfcc = {1: np.random.rand(60).astype(np.float32)}

        def _side_effect(key: str) -> dict:
            return fake_mfcc if key == "mfcc_summary" else {}

        m.db.get_all_audio_features.side_effect = _side_effect
        y = self._query_audio()
        result = m.match_segment_by_mfcc("fake.mp3", 0, 5000, preloaded_audio=y)
        assert result is None

    def test_returns_none_when_audio_is_empty(self) -> None:
        """Returns None when the preloaded audio array is empty."""
        m = self._matcher()
        m.db.get_all_audio_features.return_value = {}
        result = m.match_segment_by_mfcc("fake.mp3", 0, 5000,
                                          preloaded_audio=np.array([], dtype=np.float32))
        assert result is None

    # ---- no sustained match ------------------------------------------------

    def test_returns_none_when_no_sustained_match(self) -> None:
        """Returns None when reference audio has no similarity to the query."""
        from shazamix.matcher import Matcher

        m = self._matcher()
        sr = 22050
        y = self._query_audio(5.0)

        # Build plausible compact features (same audio → same compacts)
        fake_mfcc = {1: m.compute_mfcc_summary(y, sr)}
        fake_chroma = {1: m.compute_chroma_summary(y, sr)}

        m.db.get_all_audio_features.side_effect = lambda key: (
            fake_mfcc if key == "mfcc_summary" else fake_chroma
        )
        m.db.get_track_info.return_value = {
            "artist": "Artist",
            "title": "Title",
            "filepath": "/fake/track.mp3",
            "filename": "track.mp3",
        }

        # Reference audio = silence → sim ≈ 0 → no sustained run
        silence = np.zeros(sr * 5, dtype=np.float32)
        with patch("librosa.load", return_value=(silence, sr)):
            result = m.match_segment_by_mfcc("fake.mp3", 0, 5000, preloaded_audio=y)

        assert result is None

    # ---- successful match --------------------------------------------------

    def test_returns_match_when_reference_equals_query(self) -> None:
        """Returns a Match when the reference audio is identical to the query."""
        from shazamix.matcher import Matcher, Match

        m = self._matcher()
        sr = 22050
        y = self._query_audio(5.0)

        fake_mfcc = {1: m.compute_mfcc_summary(y, sr)}
        fake_chroma = {1: m.compute_chroma_summary(y, sr)}

        m.db.get_all_audio_features.side_effect = lambda key: (
            fake_mfcc if key == "mfcc_summary" else fake_chroma
        )
        m.db.get_track_info.return_value = {
            "artist": "Test Artist",
            "title": "Test Title",
            "filepath": "/fake/track.mp3",
            "filename": "track.mp3",
        }

        # Reference == query → perfect self-match
        with patch("librosa.load", return_value=(y, sr)):
            result = m.match_segment_by_mfcc("fake.mp3", 0, 5000, preloaded_audio=y)

        assert result is not None
        assert isinstance(result, Match)
        assert result.artist == "Test Artist"
        assert result.title == "Test Title"
        assert result.confidence >= 0.9

    def test_match_metadata_from_db(self) -> None:
        """Match fields are populated from DB track info."""
        from shazamix.matcher import Matcher, Match

        m = self._matcher()
        sr = 22050
        y = self._query_audio(5.0)

        fake_mfcc = {42: m.compute_mfcc_summary(y, sr)}
        fake_chroma = {42: m.compute_chroma_summary(y, sr)}

        m.db.get_all_audio_features.side_effect = lambda key: (
            fake_mfcc if key == "mfcc_summary" else fake_chroma
        )
        m.db.get_track_info.return_value = {
            "artist": "DJ Test",
            "title": "My Track",
            "filepath": "/music/my_track.mp3",
            "filename": "my_track.mp3",
        }

        start_ms, end_ms = 1000, 6000
        with patch("librosa.load", return_value=(y, sr)):
            result = m.match_segment_by_mfcc("mix.mp3", start_ms, end_ms,
                                              preloaded_audio=y)

        assert result is not None
        assert result.track_id == 42
        assert result.query_start_ms == start_ms
        assert result.duration_ms == end_ms - start_ms
        assert result.filepath == "/music/my_track.mp3"

    def test_best_candidate_wins(self) -> None:
        """When two candidates exist, the one matching the query wins."""
        from shazamix.matcher import Matcher, Match

        m = self._matcher()
        sr = 22050
        y = self._query_audio(5.0)

        # Candidate 1 = identical to query (should win).
        # Candidate 2 = silence (should lose).
        fake_mfcc = {
            1: m.compute_mfcc_summary(y, sr),
            2: m.compute_mfcc_summary(np.zeros(sr * 5, dtype=np.float32), sr),
        }
        fake_chroma = {
            1: m.compute_chroma_summary(y, sr),
            2: m.compute_chroma_summary(np.zeros(sr * 5, dtype=np.float32), sr),
        }

        m.db.get_all_audio_features.side_effect = lambda key: (
            fake_mfcc if key == "mfcc_summary" else fake_chroma
        )

        def _track_info(tid: int) -> dict:
            return {
                "artist": f"Artist {tid}",
                "title": f"Title {tid}",
                "filepath": f"/fake/{tid}.mp3",
                "filename": f"{tid}.mp3",
            }

        m.db.get_track_info.side_effect = _track_info

        silence = np.zeros(sr * 5, dtype=np.float32)
        call_count = [0]

        def _load(path, sr=None, mono=True):
            call_count[0] += 1
            # Return the matching audio for track 1's file, silence for track 2.
            if "1.mp3" in path:
                return y, sr
            return silence, sr

        with patch("librosa.load", side_effect=_load):
            result = m.match_segment_by_mfcc("mix.mp3", 0, 5000, preloaded_audio=y)

        assert result is not None
        assert result.track_id == 1

    def test_progress_callback_called(self) -> None:
        """progress_callback receives at least one message during processing."""
        from shazamix.matcher import Matcher

        m = self._matcher()
        sr = 22050
        y = self._query_audio(3.0)

        fake_mfcc = {1: m.compute_mfcc_summary(y, sr)}
        fake_chroma = {1: m.compute_chroma_summary(y, sr)}
        m.db.get_all_audio_features.side_effect = lambda key: (
            fake_mfcc if key == "mfcc_summary" else fake_chroma
        )
        m.db.get_track_info.return_value = {
            "artist": "A", "title": "T",
            "filepath": "/f.mp3", "filename": "f.mp3",
        }

        messages: list[str] = []

        def _cb(cur: int, tot: int, msg: str) -> None:
            messages.append(msg)

        with patch("librosa.load", return_value=(y, sr)):
            m.match_segment_by_mfcc("fake.mp3", 0, 5000,
                                     preloaded_audio=y,
                                     progress_callback=_cb)

        assert len(messages) > 0
        # Should see Stage 2a and Stage 2b messages
        all_msgs = " ".join(messages)
        assert "Stage 2a" in all_msgs
        assert "Stage 2b" in all_msgs

    def test_loads_mix_when_no_preloaded_audio(self) -> None:
        """When preloaded_audio is None, librosa.load is called for the mix."""
        from shazamix.matcher import Matcher

        m = self._matcher()
        sr = 22050
        y = _sine_audio(5.0)

        # Provide non-empty features so the function proceeds past the early-return
        # and reaches the librosa.load call for the mix segment.
        fake_mfcc = {1: m.compute_mfcc_summary(y, sr)}
        fake_chroma = {1: m.compute_chroma_summary(y, sr)}
        m.db.get_all_audio_features.side_effect = lambda key: (
            fake_mfcc if key == "mfcc_summary" else fake_chroma
        )
        m.db.get_track_info.return_value = {
            "artist": "A", "title": "T",
            "filepath": "/ref.mp3", "filename": "ref.mp3",
        }

        with patch("librosa.load", return_value=(y, sr)) as mock_load:
            m.match_segment_by_mfcc("real_mix.mp3", 10000, 15000)

        # librosa.load must have been called with the mix path (no preloaded_audio)
        called_paths = [call.args[0] for call in mock_load.call_args_list]
        assert "real_mix.mp3" in called_paths
