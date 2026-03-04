"""Tests for waveform serialization utilities."""

import io
import pickle
import warnings
from pathlib import Path

import numpy as np
import pytest

from jukebox.utils.waveform_serializer import deserialize_waveform, serialize_waveform


class TestSerializeWaveform:
    """Tests for serialize_waveform."""

    def test_round_trip_returns_same_arrays(self) -> None:
        """Serializing then deserializing returns equivalent arrays."""
        waveform = {
            "bass": np.array([0.1, 0.2, 0.3], dtype=np.float32),
            "mid": np.array([0.4, 0.5, 0.6], dtype=np.float32),
            "treble": np.array([0.7, 0.8, 0.9], dtype=np.float32),
        }

        data = serialize_waveform(waveform)
        result = deserialize_waveform(data)

        np.testing.assert_array_almost_equal(result["bass"], waveform["bass"])
        np.testing.assert_array_almost_equal(result["mid"], waveform["mid"])
        np.testing.assert_array_almost_equal(result["treble"], waveform["treble"])

    def test_round_trip_preserves_float64(self) -> None:
        """Round-trip preserves float64 array values."""
        waveform = {
            "bass": np.linspace(0.0, 1.0, 100, dtype=np.float64),
            "mid": np.zeros(100, dtype=np.float64),
            "treble": np.ones(100, dtype=np.float64),
        }

        data = serialize_waveform(waveform)
        result = deserialize_waveform(data)

        np.testing.assert_array_almost_equal(result["bass"], waveform["bass"])
        np.testing.assert_array_almost_equal(result["mid"], waveform["mid"])
        np.testing.assert_array_almost_equal(result["treble"], waveform["treble"])

    def test_serialize_returns_bytes(self) -> None:
        """serialize_waveform returns bytes."""
        waveform = {
            "bass": np.array([1.0]),
            "mid": np.array([2.0]),
            "treble": np.array([3.0]),
        }
        data = serialize_waveform(waveform)
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_empty_arrays_round_trip(self) -> None:
        """Serialize and deserialize empty arrays."""
        waveform = {
            "bass": np.array([]),
            "mid": np.array([]),
            "treble": np.array([]),
        }

        data = serialize_waveform(waveform)
        result = deserialize_waveform(data)

        assert result["bass"].size == 0
        assert result["mid"].size == 0
        assert result["treble"].size == 0

    def test_missing_keys_produce_empty_arrays(self) -> None:
        """Missing keys in input dict produce empty arrays on deserialize."""
        # Provide a dict with no bass/mid/treble keys at all
        waveform: dict = {}

        data = serialize_waveform(waveform)
        result = deserialize_waveform(data)

        assert result["bass"].size == 0
        assert result["mid"].size == 0
        assert result["treble"].size == 0

    def test_partial_missing_keys(self) -> None:
        """Providing only some keys produces empty arrays for the rest."""
        waveform = {
            "bass": np.array([1.0, 2.0]),
        }

        data = serialize_waveform(waveform)
        result = deserialize_waveform(data)

        np.testing.assert_array_almost_equal(result["bass"], np.array([1.0, 2.0]))
        assert result["mid"].size == 0
        assert result["treble"].size == 0


class TestDeserializeWaveform:
    """Tests for deserialize_waveform."""

    def test_legacy_pickle_fallback_loads_data(self) -> None:
        """Legacy pickle data is loaded with a deprecation log message."""
        waveform = {
            "bass": np.array([0.1, 0.2]),
            "mid": np.array([0.3, 0.4]),
            "treble": np.array([0.5, 0.6]),
        }
        pickle_data = pickle.dumps(waveform)

        # deserialize_waveform should fall back to pickle and succeed
        result = deserialize_waveform(pickle_data)

        np.testing.assert_array_almost_equal(result["bass"], waveform["bass"])
        np.testing.assert_array_almost_equal(result["mid"], waveform["mid"])
        np.testing.assert_array_almost_equal(result["treble"], waveform["treble"])

    def test_legacy_pickle_fallback_logs_deprecation(self, caplog: pytest.LogCaptureFixture) -> None:
        """Legacy pickle fallback emits a debug log about upgrading."""
        import logging

        waveform = {
            "bass": np.array([1.0]),
            "mid": np.array([2.0]),
            "treble": np.array([3.0]),
        }
        pickle_data = pickle.dumps(waveform)

        with caplog.at_level(logging.DEBUG):
            deserialize_waveform(pickle_data)

        assert any("legacy pickle" in record.message.lower() for record in caplog.records)

    def test_corrupt_data_raises_value_error(self) -> None:
        """Corrupt bytes that are neither numpy nor pickle raise ValueError."""
        corrupt_data = b"this is not valid waveform data at all!!!"

        with pytest.raises(ValueError, match="Invalid waveform data"):
            deserialize_waveform(corrupt_data)

    def test_empty_bytes_raises_value_error(self) -> None:
        """Empty bytes raise ValueError."""
        with pytest.raises(ValueError, match="Invalid waveform data"):
            deserialize_waveform(b"")

    def test_truncated_numpy_data_raises_value_error(self) -> None:
        """Truncated numpy data raises ValueError."""
        waveform = {
            "bass": np.array([1.0, 2.0]),
            "mid": np.array([3.0, 4.0]),
            "treble": np.array([5.0, 6.0]),
        }
        good_data = serialize_waveform(waveform)
        truncated = good_data[: len(good_data) // 2]

        with pytest.raises(ValueError, match="Invalid waveform data"):
            deserialize_waveform(truncated)
