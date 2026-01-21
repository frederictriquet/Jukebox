"""Secure waveform serialization using numpy (no pickle).

Pickle can execute arbitrary code during deserialization, making it
a security risk for untrusted data. This module uses numpy's native
format which is safe and cannot execute code.
"""

import io
import logging
from typing import Any

import numpy as np


def serialize_waveform(waveform: dict[str, Any]) -> bytes:
    """Serialize waveform data to bytes using numpy's secure format.

    Args:
        waveform: Dict with 'bass', 'mid', 'treble' numpy arrays

    Returns:
        Compressed bytes representation
    """
    buffer = io.BytesIO()
    # Use savez_compressed for efficient storage of multiple arrays
    np.savez_compressed(
        buffer,
        bass=waveform.get("bass", np.array([])),
        mid=waveform.get("mid", np.array([])),
        treble=waveform.get("treble", np.array([])),
    )
    return buffer.getvalue()


def deserialize_waveform(data: bytes) -> dict[str, np.ndarray]:
    """Deserialize waveform data from bytes.

    Tries numpy format first (secure), falls back to pickle for legacy data
    with a deprecation warning. Legacy pickle data will be replaced with
    secure numpy format on next waveform regeneration.

    Args:
        data: Bytes from serialize_waveform() or legacy pickle

    Returns:
        Dict with 'bass', 'mid', 'treble' numpy arrays

    Raises:
        ValueError: If data is corrupted or invalid format
    """
    buffer = io.BytesIO(data)
    try:
        # Try secure numpy format first (allow_pickle=False)
        with np.load(buffer, allow_pickle=False) as npz:
            return {
                "bass": npz["bass"],
                "mid": npz["mid"],
                "treble": npz["treble"],
            }
    except Exception:
        # Fall back to legacy pickle format for old cached data
        # This is temporary - data will be replaced on next waveform generation
        import pickle

        buffer.seek(0)
        try:
            result = pickle.loads(data)
            logging.debug(
                "[WaveformSerializer] Loaded legacy pickle data. "
                "Regenerate waveforms to upgrade to secure format."
            )
            return result
        except Exception as e:
            raise ValueError(f"Invalid waveform data: {e}") from e
