"""Audio feature extraction using librosa.

Standalone module (no PySide6) so it can be safely imported in subprocesses.
"""

from __future__ import annotations

import numpy as np


def analyze_audio_file(filepath: str, extract_ml_features: bool = False) -> dict[str, float]:
    """Analyze audio file and extract features.

    Args:
        filepath: Path to audio file
        extract_ml_features: If True, extract full stats including tempo, brightness,
                            percussive, RMS, and comprehensive ML features (slower)

    Returns:
        Dict with ML features (only when extract_ml_features=True), empty dict otherwise

    Raises:
        Exception: If analysis fails
    """
    if not extract_ml_features:
        return {}

    import warnings

    import librosa

    # Suppress librosa/audioread warnings for corrupted files
    warnings.filterwarnings("ignore", category=UserWarning, module="librosa")

    # Load audio at native sample rate to preserve full frequency spectrum
    y, sr = librosa.load(filepath, sr=None, mono=True)

    if len(y) == 0:
        raise ValueError("Empty audio file")

    try:
        return _extract_ml_features(y, int(sr))
    finally:
        del y
        import gc

        gc.collect()


def _extract_ml_features(y: np.ndarray, sr: int) -> dict[str, float]:
    """Extract comprehensive ML features for learning.

    Args:
        y: Audio time series
        sr: Sample rate

    Returns:
        Dict with ~50 ML features including tempo, brightness, percussive, RMS
    """
    import librosa

    features: dict[str, float] = {}

    # Core stats: tempo, brightness (spectral_centroid), percussive (zcr), RMS
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    features["tempo"] = float(tempo) if tempo else 0.0

    rms = librosa.feature.rms(y=y)[0]
    features["rms_energy"] = float(np.mean(rms))

    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    features["spectral_centroid"] = float(np.mean(centroid))

    zcr = librosa.feature.zero_crossing_rate(y)[0]
    features["zero_crossing_rate"] = float(np.mean(zcr))

    # 1. Energy & dynamics (8 features)
    features["rms_mean"] = float(np.mean(rms))
    features["rms_std"] = float(np.std(rms))
    features["rms_p10"] = float(np.percentile(rms, 10))
    features["rms_p90"] = float(np.percentile(rms, 90))
    features["peak_amplitude"] = float(np.max(np.abs(y)))
    features["crest_factor"] = float(features["peak_amplitude"] / (features["rms_mean"] + 1e-10))
    features["loudness_variation"] = float(np.std(rms))

    # 2. Frequency band energies (12 features)
    # Compute STFT for band analysis
    stft = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)

    def band_energy(
        stft_mat: np.ndarray, freqs: np.ndarray, f_min: float, f_max: float
    ) -> tuple[float, float]:
        """Compute mean energy and ratio for a frequency band."""
        mask = (freqs >= f_min) & (freqs < f_max)
        band = stft_mat[mask, :]
        band_mean = float(np.mean(band))
        total_energy = float(np.mean(stft_mat))
        ratio = band_mean / (total_energy + 1e-10)
        return band_mean, ratio

    # Sub-bass (20-60 Hz)
    features["sub_bass_mean"], features["sub_bass_ratio"] = band_energy(stft, freqs, 20, 60)
    # Bass (60-150 Hz)
    features["bass_mean"], features["bass_ratio"] = band_energy(stft, freqs, 60, 150)
    # Low-mid (150-500 Hz)
    features["low_mid_mean"], features["low_mid_ratio"] = band_energy(stft, freqs, 150, 500)
    # Mid (500-2000 Hz)
    features["mid_mean"], features["mid_ratio"] = band_energy(stft, freqs, 500, 2000)
    # High-mid (2-6 kHz)
    features["high_mid_mean"], features["high_mid_ratio"] = band_energy(stft, freqs, 2000, 6000)
    # High/treble (6-20 kHz)
    features["high_mean"], features["high_ratio"] = band_energy(stft, freqs, 6000, 20000)

    # 3. Spectral features (6 features) - centroid already computed
    features["spectral_centroid_std"] = float(np.std(centroid))
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
    features["spectral_bandwidth"] = float(np.mean(bandwidth))
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
    features["spectral_rolloff"] = float(np.mean(rolloff))
    flatness = librosa.feature.spectral_flatness(y=y)[0]
    features["spectral_flatness"] = float(np.mean(flatness))
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
    features["spectral_contrast"] = float(np.mean(contrast))
    # Spectral entropy
    spec_norm = stft / (np.sum(stft, axis=0, keepdims=True) + 1e-10)
    spec_entropy = -np.sum(spec_norm * np.log(spec_norm + 1e-10), axis=0)
    features["spectral_entropy"] = float(np.mean(spec_entropy))

    # 4. MFCC (10 coefficients)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=10)
    for i in range(10):
        features[f"mfcc_{i+1}"] = float(np.mean(mfcc[i, :]))

    # 5. Percussive vs harmonic (5 features)
    y_harmonic, y_percussive = librosa.effects.hpss(y)
    features["harmonic_energy"] = float(np.mean(librosa.feature.rms(y=y_harmonic)[0]))
    features["percussive_energy"] = float(np.mean(librosa.feature.rms(y=y_percussive)[0]))
    features["perc_harm_ratio"] = features["percussive_energy"] / (
        features["harmonic_energy"] + 1e-10
    )

    onset_env = librosa.onset.onset_strength(y=y_percussive, sr=sr)
    features["onset_strength_mean"] = float(np.mean(onset_env))
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)
    duration = len(y) / sr
    features["percussive_onset_rate"] = len(onsets) / duration if duration > 0 else 0.0

    # 6. Rhythm & tempo (5 additional features) - tempo already computed
    features["tempo_confidence"] = 1.0  # Placeholder (librosa doesn't return confidence easily)
    if len(beats) > 1:
        beat_times = librosa.frames_to_time(beats, sr=sr)
        beat_intervals = np.diff(beat_times)
        features["beat_interval_mean"] = float(np.mean(beat_intervals))
        features["beat_interval_std"] = float(np.std(beat_intervals))
    else:
        features["beat_interval_mean"] = 0.0
        features["beat_interval_std"] = 0.0

    # Onset rate
    all_onsets = librosa.onset.onset_detect(y=y, sr=sr)
    features["onset_rate"] = len(all_onsets) / duration if duration > 0 else 0.0

    # Tempogram dominant periodicity
    tempogram = librosa.feature.tempogram(onset_envelope=onset_env, sr=sr)
    features["tempogram_periodicity"] = float(np.mean(tempogram))

    # 7. Harmony (4 features)
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    chroma_norm = chroma / (np.sum(chroma, axis=0, keepdims=True) + 1e-10)
    chroma_entropy = -np.sum(chroma_norm * np.log(chroma_norm + 1e-10), axis=0)
    features["chroma_entropy"] = float(np.mean(chroma_entropy))
    features["chroma_centroid"] = float(np.mean(np.argmax(chroma, axis=0)))
    features["chroma_energy_std"] = float(np.std(np.sum(chroma, axis=0)))

    tonnetz = librosa.feature.tonnetz(y=y_harmonic, sr=sr)
    features["tonnetz_mean"] = float(np.mean(tonnetz))

    # Free large intermediates before structure analysis
    del stft, spec_norm, spec_entropy, mfcc, chroma, chroma_norm, chroma_entropy
    del tonnetz, tempogram, onset_env, y_harmonic, y_percussive

    # 8. Structure (4 features)
    # Split track into intro (0-20%), core (20-80%), outro (80-100%)
    n_samples = len(y)
    intro_end = int(n_samples * 0.2)
    core_start = intro_end
    core_end = int(n_samples * 0.8)
    outro_start = core_end

    intro_energy = float(np.mean(np.abs(y[:intro_end])))
    core_energy = float(np.mean(np.abs(y[core_start:core_end])))
    outro_energy = float(np.mean(np.abs(y[outro_start:])))
    total_energy = float(np.mean(np.abs(y)))

    features["intro_energy_ratio"] = intro_energy / (total_energy + 1e-10)
    features["core_energy_ratio"] = core_energy / (total_energy + 1e-10)
    features["outro_energy_ratio"] = outro_energy / (total_energy + 1e-10)

    # Energy slope (linear regression of RMS over time)
    time_indices = np.arange(len(rms))
    slope, _ = np.polyfit(time_indices, rms, 1)
    features["energy_slope"] = float(slope)

    return features
