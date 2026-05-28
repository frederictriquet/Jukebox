"""Waveform serialization using numpy (format sûr, sans pickle).

pickle peut exécuter du code arbitraire à la désérialisation — interdit
pour des données provenant de la base SQLite. On utilise uniquement
numpy.savez_compressed / numpy.load(allow_pickle=False).
"""

import io
from typing import Any

import numpy as np


def serialize_waveform(waveform: dict[str, Any]) -> bytes:
    """Sérialise les données waveform en bytes (format numpy compressé).

    Args:
        waveform: Dict avec les arrays 'bass', 'mid', 'treble'

    Returns:
        Bytes au format npz compressé
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
    """Désérialise les données waveform depuis bytes.

    Args:
        data: Bytes produits par serialize_waveform()

    Returns:
        Dict avec les arrays numpy 'bass', 'mid', 'treble'

    Raises:
        ValueError: Si les données sont corrompues ou dans un format non supporté
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
