"""Shazamix - Audio fingerprinting for DJ mix track identification.

This module implements an audio fingerprinting algorithm optimized for
identifying tracks in DJ mixes, even when tempo and pitch have been modified.

Based on the Panako algorithm principles:
- Constant-Q transform (log-frequency scale) for pitch-shift robustness
- Frequency ratios instead of absolute values for tempo robustness
- Peak constellation matching

References:
- Panako: https://github.com/JorenSix/Panako
- "A Highly Robust Audio Fingerprinting System" (Wang, 2003)
"""

__version__ = "0.1.0"

from .fingerprint import Fingerprinter
from .database import FingerprintDB
from .matcher import Matcher

__all__ = ["Fingerprinter", "FingerprintDB", "Matcher"]
