"""Waveform serialization using numpy (safe format, no pickle).

pickle can execute arbitrary code during deserialization — forbidden
for data coming from the SQLite database. We use only
numpy.savez_compressed / numpy.load(allow_pickle=False).
"""

import io
from typing import Any

import numpy as np


def serialize_waveform(waveform: dict[str, Any]) -> bytes:
    """Serialize waveform data to bytes (compressed numpy format).

    Args:
        waveform: Dict with the 'bass', 'mid', 'treble' arrays

    Returns:
        Bytes in compressed npz format
    """
    buffer = io.BytesIO()
    np.savez_compressed(
        buffer,
        bass=waveform.get("bass", np.array([])),
        mid=waveform.get("mid", np.array([])),
        treble=waveform.get("treble", np.array([])),
    )
    return buffer.getvalue()


def deserialize_waveform(data: bytes) -> dict[str, np.ndarray]:
    """Deserialize waveform data from bytes.

    Args:
        data: Bytes produced by serialize_waveform()

    Returns:
        Dict with the 'bass', 'mid', 'treble' numpy arrays

    Raises:
        ValueError: If the data is corrupted or in an unsupported format
    """
    buffer = io.BytesIO(data)
    try:
        with np.load(buffer, allow_pickle=False) as npz:
            return {
                "bass": npz["bass"],
                "mid": npz["mid"],
                "treble": npz["treble"],
            }
    except Exception as e:
        raise ValueError(f"Données waveform invalides ou format non supporté : {e}") from e
