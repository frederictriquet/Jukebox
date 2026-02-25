"""Shared constants for the Jukebox application."""


class StatusColors:
    """Centralized status message colors (hex)."""

    SUCCESS = "#00FF00"
    ERROR = "#FF0000"
    WARNING = "#FFA500"
    WARNING_ALT = "#FF6600"


# Timer constants
VLC_SEEK_DELAY_MS = 50
"""Delay before seeking in VLC to allow media to initialize."""

WORKER_WAIT_TIMEOUT_MS = 5000
"""Timeout for waiting on worker threads during shutdown."""

# Audio processing constants
AUDIO_SAMPLE_RATE = 22050
"""Standard sample rate for audio analysis (Hz)."""

AUDIO_SAMPLE_RATE_LOW = 11025
"""Low-resolution sample rate for waveform display (Hz)."""

AUDIO_HOP_LENGTH = 2048
"""Hop length for spectral analysis (samples)."""

FREQ_BASS_LOW = 20
"""Bass band lower frequency bound (Hz)."""

FREQ_BASS_HIGH = 250
"""Bass/mid crossover frequency (Hz)."""

FREQ_MID_HIGH = 4000
"""Mid/treble crossover frequency (Hz)."""

FREQ_TREBLE_HIGH = 20000
"""Treble upper frequency bound (Hz)."""
