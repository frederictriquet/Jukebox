"""Audio fingerprinting using Panako-inspired algorithm.

This implementation uses:
- Constant-Q Transform (CQT) for log-frequency representation
- Peak picking in the spectrogram
- Fingerprints based on frequency ratios and time ratios (tempo-invariant)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True, slots=True)
class Fingerprint:
    """A single fingerprint derived from spectral peaks.

    Based on Panako's approach: use ratios instead of absolute values
    for robustness to tempo and pitch changes.

    Attributes:
        hash: 32-bit hash combining frequency and time ratios
        time_offset_ms: Time offset from start of audio (in milliseconds)
        freq_bin: Anchor frequency bin (for debugging/verification)
    """
    hash: int
    time_offset_ms: int
    freq_bin: int


@dataclass(frozen=True, slots=True)
class Peak:
    """A spectral peak in the CQT spectrogram."""
    time_frame: int
    freq_bin: int
    magnitude: float


class Fingerprinter:
    """Extract fingerprints from audio using Panako-inspired algorithm.

    The algorithm:
    1. Compute Constant-Q Transform (log-frequency spectrogram)
    2. Find local maxima (peaks) in the spectrogram
    3. For each anchor peak, find nearby target peaks
    4. Create fingerprints from triplets using frequency/time ratios

    Using ratios makes fingerprints invariant to:
    - Tempo changes (time stretching)
    - Pitch shifts (frequency scaling)
    """

    def __init__(
        self,
        sample_rate: int = 22050,
        hop_length: int = 512,
        n_bins: int = 84,  # 7 octaves
        bins_per_octave: int = 12,
        peak_neighborhood: tuple[int, int] = (5, 5),  # (time, freq) neighborhood - larger = fewer peaks
        target_zone: tuple[int, int, int, int] = (2, 30, -8, 8),  # (t_min, t_max, f_min, f_max)
        fan_out: int = 3,  # Max targets per anchor - reduced for more selective fingerprints
    ):
        """Initialize fingerprinter.

        Args:
            sample_rate: Audio sample rate (will resample if different)
            hop_length: CQT hop length in samples
            n_bins: Number of CQT frequency bins
            bins_per_octave: Frequency resolution
            peak_neighborhood: Size of neighborhood for peak detection (time, freq)
            target_zone: Zone to search for target peaks relative to anchor
                        (t_min, t_max, f_min, f_max) in frames/bins
            fan_out: Maximum number of target peaks per anchor
        """
        self.sample_rate = sample_rate
        self.hop_length = hop_length
        self.n_bins = n_bins
        self.bins_per_octave = bins_per_octave
        self.peak_neighborhood = peak_neighborhood
        self.target_zone = target_zone
        self.fan_out = fan_out

        # Time resolution in milliseconds
        self.ms_per_frame = (hop_length / sample_rate) * 1000

    def extract_fingerprints(self, audio_path: str) -> list[Fingerprint]:
        """Extract fingerprints from an audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            List of fingerprints
        """
        import librosa

        # Load audio
        y, sr = librosa.load(audio_path, sr=self.sample_rate, mono=True)

        if len(y) == 0:
            return []

        return self.extract_fingerprints_from_array(y)

    def extract_fingerprints_from_array(self, y: np.ndarray) -> list[Fingerprint]:
        """Extract fingerprints from audio array.

        Args:
            y: Audio time series (mono, at self.sample_rate)

        Returns:
            List of fingerprints
        """
        import librosa

        # Compute Constant-Q Transform
        # CQT gives log-frequency representation which is more robust to pitch shifts
        C = np.abs(librosa.cqt(
            y,
            sr=self.sample_rate,
            hop_length=self.hop_length,
            n_bins=self.n_bins,
            bins_per_octave=self.bins_per_octave,
        ))

        # Convert to dB scale
        C_db = librosa.amplitude_to_db(C, ref=np.max)

        # Find peaks
        peaks = self._find_peaks(C_db)

        # Generate fingerprints from peak pairs/triplets
        fingerprints = list(self._generate_fingerprints(peaks))

        return fingerprints

    def _find_peaks(self, spectrogram: np.ndarray) -> list[Peak]:
        """Find local maxima in the spectrogram.

        Args:
            spectrogram: 2D array (frequency x time)

        Returns:
            List of Peak objects sorted by time
        """
        from scipy.ndimage import maximum_filter, minimum_filter

        n_freq, n_time = spectrogram.shape
        freq_hood, time_hood = self.peak_neighborhood

        # Create neighborhood filter
        neighborhood_size = (2 * freq_hood + 1, 2 * time_hood + 1)

        # Find local maxima
        local_max = maximum_filter(spectrogram, size=neighborhood_size)
        is_peak = (spectrogram == local_max)

        # Threshold: only keep peaks well above median (more selective)
        threshold = np.median(spectrogram) + 20  # dB above median
        is_peak &= (spectrogram > threshold)

        # Also filter by percentile - keep only top peaks
        if np.any(is_peak):
            peak_values = spectrogram[is_peak]
            if len(peak_values) > 1000:
                # Keep only top 1000 peaks per spectrogram
                top_threshold = np.percentile(peak_values, 100 * (1 - 1000 / len(peak_values)))
                is_peak &= (spectrogram >= top_threshold)

        # Extract peak coordinates
        freq_bins, time_frames = np.where(is_peak)

        peaks = [
            Peak(
                time_frame=int(t),
                freq_bin=int(f),
                magnitude=float(spectrogram[f, t])
            )
            for f, t in zip(freq_bins, time_frames)
        ]

        # Sort by time
        peaks.sort(key=lambda p: (p.time_frame, -p.magnitude))

        return peaks

    def _generate_fingerprints(self, peaks: list[Peak]) -> Iterator[Fingerprint]:
        """Generate fingerprints from peak constellation.

        Uses Panako-style approach: for each anchor peak, find target peaks
        and create fingerprints using frequency and time ratios.

        Args:
            peaks: List of spectral peaks sorted by time

        Yields:
            Fingerprint objects
        """
        t_min, t_max, f_min, f_max = self.target_zone

        # Index peaks by time frame for efficient lookup
        peaks_by_time: dict[int, list[Peak]] = {}
        for peak in peaks:
            if peak.time_frame not in peaks_by_time:
                peaks_by_time[peak.time_frame] = []
            peaks_by_time[peak.time_frame].append(peak)

        # For each anchor peak
        for anchor in peaks:
            targets_found = 0

            # Search target zone
            for dt in range(t_min, t_max + 1):
                if targets_found >= self.fan_out:
                    break

                target_time = anchor.time_frame + dt
                if target_time not in peaks_by_time:
                    continue

                for target in peaks_by_time[target_time]:
                    if targets_found >= self.fan_out:
                        break

                    df = target.freq_bin - anchor.freq_bin
                    if f_min <= df <= f_max and dt > 0:
                        # Create hash from ratios (tempo/pitch invariant)
                        fp_hash = self._compute_hash(anchor, target, dt, df)

                        time_ms = int(anchor.time_frame * self.ms_per_frame)

                        yield Fingerprint(
                            hash=fp_hash,
                            time_offset_ms=time_ms,
                            freq_bin=anchor.freq_bin,
                        )
                        targets_found += 1

    def _compute_hash(
        self,
        anchor: Peak,
        target: Peak,
        dt: int,
        df: int,
    ) -> int:
        """Compute fingerprint hash from anchor-target pair.

        The hash uses all 32 bits for better discrimination:
        - Anchor frequency (7 bits) - log-frequency bin
        - Target frequency (7 bits) - log-frequency bin
        - Frequency difference (6 bits, signed) - robust to pitch shift
        - Time difference (6 bits) - robust to tempo change
        - Magnitude ratio (6 bits) - relative loudness

        Args:
            anchor: Anchor peak
            target: Target peak
            dt: Time difference in frames
            df: Frequency difference in bins

        Returns:
            32-bit hash value
        """
        # Anchor frequency bin (7 bits = 128 values, covers 84 CQT bins)
        anchor_freq = anchor.freq_bin & 0x7F

        # Target frequency bin (7 bits)
        target_freq = target.freq_bin & 0x7F

        # Frequency difference with offset (6 bits = 64 values, range -32 to +31)
        freq_diff = ((df + 32) & 0x3F)

        # Time difference (6 bits = 64 values, range 0-63 frames)
        time_diff = min(dt, 63) & 0x3F

        # Magnitude ratio: quantize log ratio of magnitudes (6 bits)
        # This adds discrimination based on relative peak strength
        mag_ratio = anchor.magnitude - target.magnitude  # Already in dB
        mag_quantized = int((mag_ratio + 30) / 60 * 63)  # Map [-30, +30] dB to [0, 63]
        mag_quantized = max(0, min(63, mag_quantized)) & 0x3F

        # Combine into 32-bit hash (7+7+6+6+6 = 32 bits)
        fp_hash = (
            (anchor_freq << 25) |      # bits 31-25
            (target_freq << 18) |       # bits 24-18
            (freq_diff << 12) |         # bits 17-12
            (time_diff << 6) |          # bits 11-6
            mag_quantized               # bits 5-0
        )

        return fp_hash & 0xFFFFFFFF


def extract_fingerprints(audio_path: str, **kwargs) -> list[Fingerprint]:
    """Convenience function to extract fingerprints from an audio file.

    Args:
        audio_path: Path to audio file
        **kwargs: Arguments passed to Fingerprinter

    Returns:
        List of fingerprints
    """
    fp = Fingerprinter(**kwargs)
    return fp.extract_fingerprints(audio_path)
