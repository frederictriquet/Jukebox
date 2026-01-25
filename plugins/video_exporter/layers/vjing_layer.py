"""VJing effects layer based on music genre."""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image, ImageDraw

from plugins.video_exporter.layers.base import BaseVisualLayer

# Try to import noise library, fallback to pseudo-noise if not available
try:
    from noise import pnoise2, snoise2

    NOISE_AVAILABLE = True
except ImportError:
    NOISE_AVAILABLE = False
    logging.warning("[VJingLayer] noise library not installed, using pseudo-noise fallback")

# Try to import GPU shaders
try:
    from plugins.video_exporter.layers.gpu_shaders import GPUShaderRenderer, get_gpu_renderer

    GPU_SHADERS_AVAILABLE = True
except ImportError:
    GPU_SHADERS_AVAILABLE = False
    GPUShaderRenderer = None  # type: ignore
    get_gpu_renderer = None  # type: ignore
    logging.warning("[VJingLayer] GPU shaders not available")

if TYPE_CHECKING:
    from numpy.typing import NDArray


# =============================================================================
# LFO (Low Frequency Oscillator) System
# =============================================================================


class LFOWaveform(Enum):
    """Available LFO waveforms."""

    SINE = "sine"
    TRIANGLE = "triangle"
    SAWTOOTH = "sawtooth"
    SQUARE = "square"
    RANDOM = "random"


@dataclass
class LFO:
    """Low Frequency Oscillator for modulating effect parameters.

    Attributes:
        frequency: Oscillation frequency in Hz.
        amplitude: Output amplitude (0.0 to 1.0).
        phase: Initial phase offset (0.0 to 1.0).
        waveform: Type of waveform.
        offset: DC offset added to output.
    """

    frequency: float = 0.5
    amplitude: float = 1.0
    phase: float = 0.0
    waveform: LFOWaveform = LFOWaveform.SINE
    offset: float = 0.0
    _random_value: float = 0.0
    _last_random_time: float = -1.0

    def value(self, time_pos: float) -> float:
        """Get LFO value at given time.

        Args:
            time_pos: Time position in seconds.

        Returns:
            LFO value in range [offset - amplitude, offset + amplitude].
        """
        # Calculate phase position (0 to 1)
        t = (time_pos * self.frequency + self.phase) % 1.0

        if self.waveform == LFOWaveform.SINE:
            v = math.sin(t * 2 * math.pi)
        elif self.waveform == LFOWaveform.TRIANGLE:
            v = 4 * abs(t - 0.5) - 1
        elif self.waveform == LFOWaveform.SAWTOOTH:
            v = 2 * t - 1
        elif self.waveform == LFOWaveform.SQUARE:
            v = 1.0 if t < 0.5 else -1.0
        elif self.waveform == LFOWaveform.RANDOM:
            # Sample-and-hold random
            period = 1.0 / self.frequency if self.frequency > 0 else 1.0
            current_period = int(time_pos / period)
            if current_period != int(self._last_random_time / period):
                self._random_value = random.uniform(-1, 1)
                self._last_random_time = time_pos
            v = self._random_value
        else:
            v = 0.0

        return self.offset + v * self.amplitude

    def value_normalized(self, time_pos: float) -> float:
        """Get LFO value normalized to 0-1 range.

        Args:
            time_pos: Time position in seconds.

        Returns:
            LFO value in range [0, 1].
        """
        if self.amplitude > 0:
            return (self.value(time_pos) + self.amplitude) / (2 * self.amplitude)
        return 0.5


# =============================================================================
# Perlin Noise Utilities
# =============================================================================


def perlin2d(x: float, y: float, octaves: int = 1, persistence: float = 0.5) -> float:
    """Get 2D Perlin noise value.

    Args:
        x: X coordinate.
        y: Y coordinate.
        octaves: Number of noise octaves (detail levels).
        persistence: Amplitude decay per octave.

    Returns:
        Noise value in range [-1, 1].
    """
    if NOISE_AVAILABLE:
        return pnoise2(x, y, octaves=octaves, persistence=persistence)
    else:
        # Fallback pseudo-noise
        return _pseudo_perlin2d(x, y, octaves, persistence)


def simplex2d(x: float, y: float, octaves: int = 1, persistence: float = 0.5) -> float:
    """Get 2D Simplex noise value (faster than Perlin).

    Args:
        x: X coordinate.
        y: Y coordinate.
        octaves: Number of noise octaves.
        persistence: Amplitude decay per octave.

    Returns:
        Noise value in range [-1, 1].
    """
    if NOISE_AVAILABLE:
        return snoise2(x, y, octaves=octaves, persistence=persistence)
    else:
        return _pseudo_perlin2d(x, y, octaves, persistence)


def _pseudo_perlin2d(x: float, y: float, octaves: int = 1, persistence: float = 0.5) -> float:
    """Fallback pseudo-Perlin noise using sine functions.

    Args:
        x: X coordinate.
        y: Y coordinate.
        octaves: Number of noise octaves.
        persistence: Amplitude decay per octave.

    Returns:
        Noise value in range approximately [-1, 1].
    """
    total = 0.0
    amplitude = 1.0
    max_value = 0.0

    for i in range(octaves):
        freq = 2**i
        # Multi-frequency sine combination
        total += amplitude * (
            math.sin(x * freq * 1.7 + y * freq * 2.3)
            * math.cos(y * freq * 1.3 - x * freq * 0.7)
            * 0.5
            + math.sin((x + y) * freq * 0.9) * 0.5
        )
        max_value += amplitude
        amplitude *= persistence

    return total / max_value if max_value > 0 else 0.0


def fbm2d(
    x: float, y: float, octaves: int = 4, lacunarity: float = 2.0, gain: float = 0.5
) -> float:
    """Fractal Brownian Motion noise (layered Perlin).

    Args:
        x: X coordinate.
        y: Y coordinate.
        octaves: Number of noise layers.
        lacunarity: Frequency multiplier per octave.
        gain: Amplitude multiplier per octave.

    Returns:
        FBM noise value.
    """
    total = 0.0
    amplitude = 1.0
    frequency = 1.0
    max_value = 0.0

    for _ in range(octaves):
        total += perlin2d(x * frequency, y * frequency) * amplitude
        max_value += amplitude
        amplitude *= gain
        frequency *= lacunarity

    return total / max_value if max_value > 0 else 0.0


def turbulence2d(x: float, y: float, octaves: int = 4) -> float:
    """Turbulence noise (absolute value of FBM).

    Args:
        x: X coordinate.
        y: Y coordinate.
        octaves: Number of noise layers.

    Returns:
        Turbulence value in range [0, 1].
    """
    total = 0.0
    amplitude = 1.0
    frequency = 1.0
    max_value = 0.0

    for _ in range(octaves):
        total += abs(perlin2d(x * frequency, y * frequency)) * amplitude
        max_value += amplitude
        amplitude *= 0.5
        frequency *= 2.0

    return total / max_value if max_value > 0 else 0.0


class VJingLayer(BaseVisualLayer):
    """VJing visual effects based on genre letters.

    Supports multiple effects when genre contains multiple letters.

    Available effects:
    - Rhythm: pulse, strobe
    - Spectrum: fft_bars, fft_rings, bass_warp
    - Particles: particles, flow_field, explosion, smoke
    - Geometric: kaleidoscope, lissajous, tunnel, spiral, fractal, wormhole, metaballs
    - Post-processing: chromatic, pixelate, feedback
    - Nature: fire, water, aurora, plasma
    - Classic: wave, neon, vinyl
    - Cyber: radar, voronoi
    - Space: starfield, lightning
    """

    z_index = 4

    # Default effect mappings (based on genre_editor codes)
    # Valid genres: D, C, P, T, H, G, I, A, W, B, F, R, L, U, O, N
    # Each genre maps to a list of effects (all rendered together)
    DEFAULT_MAPPINGS: dict[str, list[str]] = {
        "D": ["aurora"],  # Deep - chill, ambient
        "C": ["kaleidoscope"],  # Classic - elegant
        "P": ["strobe"],  # Power - energetic
        "T": ["fractal"],  # Trance - hypnotic, psychedelic
        "H": ["fire"],  # House - groovy, warm
        "G": ["flow_field"],  # Garden - natural
        "I": ["neon"],  # Ibiza - club, colorful
        "A": ["wave"],  # A Cappella - soft
        "W": ["plasma"],  # Weed - chill, psychedelic
        "B": ["explosion"],  # Banger - intense
        "F": ["particles"],  # Fun - playful, festive
        "R": ["vinyl"],  # Retro - vintage
        "L": ["lissajous"],  # Loop - repetitive, hypnotic
        "U": ["wormhole"],  # Unclassable - weird, experimental
        "O": ["flow_field"],  # Organic - natural
        "N": ["wave"],  # Namaste - zen, calm
    }

    # All available effects
    AVAILABLE_EFFECTS = [
        "pulse",
        "strobe",
        "fft_bars",
        "fft_rings",
        "bass_warp",
        "particles",
        "flow_field",
        "explosion",
        "kaleidoscope",
        "lissajous",
        "tunnel",
        "spiral",
        "chromatic",
        "pixelate",
        "feedback",
        "fire",
        "water",
        "aurora",
        "wave",
        "neon",
        "vinyl",
        "fractal",
        "radar",
        "plasma",
        "wormhole",
        "starfield",
        "lightning",
        "voronoi",
        "metaballs",
        "smoke",
    ]

    def __init__(
        self,
        width: int,
        height: int,
        fps: int,
        audio: NDArray[np.floating],
        sr: int,
        duration: float,
        genre: str = "",
        effect_mappings: dict[str, list[str]] | None = None,
        preset: str = "",
        presets: dict[str, list[str]] | None = None,
        intensity: float = 0.7,
        transitions_enabled: bool = True,
        transition_duration: float = 2.0,
        effect_cycle_duration: float = 8.0,
        use_gpu: bool = True,
        **kwargs: Any,
    ) -> None:
        """Initialize VJing layer.

        Args:
            width: Frame width.
            height: Frame height.
            fps: Frames per second.
            audio: Audio samples.
            sr: Sample rate.
            duration: Duration in seconds.
            genre: Genre string (each letter can trigger effects).
            effect_mappings: Custom letter to effects list mappings.
            preset: Name of preset to use (overrides genre mapping).
            presets: Available presets {name: [effects]}.
            intensity: Effect intensity (0.0 to 1.0).
            transitions_enabled: Enable smooth transitions between effects.
            transition_duration: Duration of fade transition in seconds.
            effect_cycle_duration: How long each effect is prominently visible.
            use_gpu: Enable GPU-accelerated shaders when available.
            **kwargs: Additional parameters.
        """
        self.genre = genre
        self.intensity = intensity
        self.preset = preset
        self.presets = presets or {}
        self.transitions_enabled = transitions_enabled
        self.transition_duration = transition_duration
        self.effect_cycle_duration = effect_cycle_duration
        self.use_gpu = use_gpu
        self._gpu_renderer: GPUShaderRenderer | None = None

        # Merge custom mappings with defaults (custom takes precedence)
        self.effect_mappings: dict[str, list[str]] = {
            **self.DEFAULT_MAPPINGS,
            **(effect_mappings or {}),
        }

        logging.info(f"[VJingLayer] Initializing with genre='{genre}', preset='{preset}'")
        logging.debug(f"[VJingLayer] Effect mappings: {self.effect_mappings}")

        # Determine which effects to use based on preset or genre
        self.active_effects = self._determine_effects()

        logging.info(f"[VJingLayer] Active effects: {self.active_effects}")

        # Initialize LFOs for parameter modulation
        self._init_lfos()

        # Store dimensions for GPU initialization (done in _precompute)
        self._pending_gpu_init = use_gpu and GPU_SHADERS_AVAILABLE

        super().__init__(width, height, fps, audio, sr, duration, **kwargs)


    def _init_lfos(self) -> None:
        """Initialize LFO oscillators for parameter modulation.

        Creates a set of LFOs with different frequencies and waveforms
        that can be used to modulate effect parameters over time.
        """
        # Primary LFOs - slow modulation
        self.lfo_slow = LFO(frequency=0.1, amplitude=1.0, waveform=LFOWaveform.SINE)
        self.lfo_medium = LFO(frequency=0.3, amplitude=1.0, waveform=LFOWaveform.SINE)
        self.lfo_fast = LFO(frequency=0.8, amplitude=1.0, waveform=LFOWaveform.SINE)

        # Triangle LFOs - for linear sweeps
        self.lfo_triangle = LFO(frequency=0.2, amplitude=1.0, waveform=LFOWaveform.TRIANGLE)

        # Sawtooth - for ramp effects
        self.lfo_saw = LFO(frequency=0.15, amplitude=1.0, waveform=LFOWaveform.SAWTOOTH)

        # Random - for variation
        self.lfo_random = LFO(frequency=0.5, amplitude=0.5, waveform=LFOWaveform.RANDOM)

        # Collect all LFOs for easy iteration
        self.lfos: dict[str, LFO] = {
            "slow": self.lfo_slow,
            "medium": self.lfo_medium,
            "fast": self.lfo_fast,
            "triangle": self.lfo_triangle,
            "saw": self.lfo_saw,
            "random": self.lfo_random,
        }

        logging.debug(f"[VJingLayer] Initialized {len(self.lfos)} LFOs")

    def _init_gpu_renderer(self) -> None:
        """Initialize GPU shader renderer if available.

        This is called during _precompute after dimensions are set.
        """
        if not GPU_SHADERS_AVAILABLE or get_gpu_renderer is None:
            self._gpu_renderer = None
            return

        try:
            self._gpu_renderer = get_gpu_renderer(self.width, self.height)
            if self._gpu_renderer and self._gpu_renderer.available:
                # Check which GPU-accelerated effects we'll use
                gpu_effects = [e for e in self.active_effects if self._gpu_renderer.has_shader(e)]
                if gpu_effects:
                    logging.info(f"[VJingLayer] GPU acceleration enabled for: {gpu_effects}")
                else:
                    logging.debug("[VJingLayer] No active effects support GPU acceleration")
            else:
                logging.debug("[VJingLayer] GPU renderer not available")
                self._gpu_renderer = None
        except Exception as e:
            logging.warning(f"[VJingLayer] Failed to initialize GPU renderer: {e}")
            self._gpu_renderer = None

    def _render_gpu_effect(
        self, shader_name: str, time_pos: float, ctx: dict
    ) -> Image.Image | None:
        """Try to render an effect using GPU shader.

        Args:
            shader_name: Name of the shader (must match effect name).
            time_pos: Time position in seconds.
            ctx: Audio context dictionary.

        Returns:
            RGBA PIL Image if GPU rendering succeeded, None otherwise.
        """
        if not self._gpu_renderer or not self._gpu_renderer.has_shader(shader_name):
            return None

        return self._gpu_renderer.render(
            shader_name,
            time_pos,
            energy=ctx.get("energy", 0.5),
            bass=ctx.get("bass", 0.5),
            mid=ctx.get("mid", 0.5),
            treble=ctx.get("treble", 0.5),
            intensity=self.intensity,
        )

    def _determine_effects(self) -> list[str]:
        """Determine which effects to use based on preset or genre.

        If a preset is selected, use its effects directly.
        Otherwise, determine effects from genre letters using mappings.

        Returns:
            List of effect names (unique).
        """
        # If a preset is selected, use its effects
        if self.preset and self.preset in self.presets:
            effects = self.presets[self.preset]
            logging.info(f"[VJingLayer] Using preset '{self.preset}': {effects}")
            return effects

        # Otherwise, use genre-based mapping
        if not self.genre:
            return ["wave"]  # Default effect

        effects = []
        seen = set()

        # Check each letter in the genre against mappings
        for letter in self.genre.upper():
            if letter in self.effect_mappings:
                effect_list = self.effect_mappings[letter]
                for effect in effect_list:
                    if effect not in seen:
                        effects.append(effect)
                        seen.add(effect)

        return effects if effects else ["wave"]

    def _precompute(self) -> None:
        """Pre-compute effect-specific data."""
        samples_per_frame = len(self.audio) / self.total_frames

        # Compute energy envelope for reactive effects
        self.energy = []
        self.bass_energy = []
        self.mid_energy = []
        self.treble_energy = []

        # Try to use scipy for frequency band separation
        try:
            from scipy import signal

            nyquist = self.sr / 2

            # Design filters
            bass_b, bass_a = signal.butter(4, [20 / nyquist, 250 / nyquist], btype="band")
            mid_b, mid_a = signal.butter(
                4, [250 / nyquist, min(4000 / nyquist, 0.99)], btype="band"
            )
            treble_b, treble_a = signal.butter(4, min(4000 / nyquist, 0.99), btype="high")

            # Filter audio
            bass_audio = signal.filtfilt(bass_b, bass_a, self.audio)
            mid_audio = signal.filtfilt(mid_b, mid_a, self.audio)
            treble_audio = signal.filtfilt(treble_b, treble_a, self.audio)

            self._has_frequency_bands = True
        except ImportError:
            bass_audio = mid_audio = treble_audio = self.audio
            self._has_frequency_bands = False

        # Compute per-frame energy
        for frame_idx in range(self.total_frames):
            start = int(frame_idx * samples_per_frame)
            end = int((frame_idx + 1) * samples_per_frame)

            chunk = self.audio[start:end]
            bass_chunk = bass_audio[start:end]
            mid_chunk = mid_audio[start:end]
            treble_chunk = treble_audio[start:end]

            self.energy.append(np.sqrt(np.mean(chunk**2)) if len(chunk) > 0 else 0.0)
            self.bass_energy.append(
                np.sqrt(np.mean(bass_chunk**2)) if len(bass_chunk) > 0 else 0.0
            )
            self.mid_energy.append(
                np.sqrt(np.mean(mid_chunk**2)) if len(mid_chunk) > 0 else 0.0
            )
            self.treble_energy.append(
                np.sqrt(np.mean(treble_chunk**2)) if len(treble_chunk) > 0 else 0.0
            )

        # Normalize
        def normalize(arr: list) -> NDArray:
            arr = np.array(arr)
            max_val = np.max(arr) if np.max(arr) > 0 else 1.0
            return arr / max_val

        self.energy = normalize(self.energy)
        self.bass_energy = normalize(self.bass_energy)
        self.mid_energy = normalize(self.mid_energy)
        self.treble_energy = normalize(self.treble_energy)

        # Beat detection (simple onset detection)
        self._detect_beats()

        # Compute FFT data for spectrum effects
        self._compute_fft_data()

        # Effect-specific initialization
        if "particles" in self.active_effects:
            self._init_particles()
        if "flow_field" in self.active_effects:
            self._init_flow_field()
        if "explosion" in self.active_effects:
            self._init_explosion()
        if "feedback" in self.active_effects:
            self._init_feedback()
        if "water" in self.active_effects:
            self._init_water()
        if "fractal" in self.active_effects:
            self._init_fractal()
        if "plasma" in self.active_effects:
            self._init_plasma()
        if "wormhole" in self.active_effects:
            self._init_wormhole()
        if "starfield" in self.active_effects:
            self._init_starfield()
        if "voronoi" in self.active_effects:
            self._init_voronoi()
        if "metaballs" in self.active_effects:
            self._init_metaballs()
        if "smoke" in self.active_effects:
            self._init_smoke()

        # Initialize GPU renderer if enabled
        if self._pending_gpu_init:
            self._init_gpu_renderer()

    def _detect_beats(self) -> None:
        """Simple beat detection based on energy peaks."""
        self.beats = []
        threshold = 0.5
        min_interval = self.fps // 4  # Minimum frames between beats

        last_beat = -min_interval
        for i, e in enumerate(self.bass_energy):
            if e > threshold and i - last_beat >= min_interval:
                # Check if it's a local maximum
                window = 3
                start = max(0, i - window)
                end = min(len(self.bass_energy), i + window + 1)
                if e == max(self.bass_energy[start:end]):
                    self.beats.append(i)
                    last_beat = i

    def _compute_fft_data(self) -> None:
        """Pre-compute FFT data for each frame."""
        self.fft_data = []
        samples_per_frame = len(self.audio) / self.total_frames
        n_bands = 32  # Number of frequency bands

        for frame_idx in range(self.total_frames):
            start = int(frame_idx * samples_per_frame)
            end = int((frame_idx + 1) * samples_per_frame)
            chunk = self.audio[start:end]

            if len(chunk) > 0:
                # Compute FFT
                fft = np.abs(np.fft.rfft(chunk))
                # Resample to n_bands
                band_size = len(fft) // n_bands
                bands = []
                for i in range(n_bands):
                    band_start = i * band_size
                    band_end = (i + 1) * band_size
                    bands.append(np.mean(fft[band_start:band_end]))
                self.fft_data.append(np.array(bands))
            else:
                self.fft_data.append(np.zeros(n_bands))

        # Normalize FFT data
        max_fft = max(np.max(f) for f in self.fft_data) if self.fft_data else 1.0
        if max_fft > 0:
            self.fft_data = [f / max_fft for f in self.fft_data]

    def _init_particles(self) -> None:
        """Initialize particle system."""
        self.particles: list[dict[str, Any]] = []
        self.max_particles = 80

        for _ in range(self.max_particles):
            self._spawn_particle()

    def _spawn_particle(self) -> None:
        """Spawn a new particle."""
        self.particles.append(
            {
                "x": random.random() * self.width,
                "y": random.random() * self.height,
                "vx": (random.random() - 0.5) * 2,
                "vy": (random.random() - 0.5) * 2,
                "size": random.random() * 10 + 5,
                "color": random.choice(
                    [(255, 100, 100), (100, 255, 100), (100, 100, 255), (255, 255, 100)]
                ),
                "life": random.random() * 100,
            }
        )

    def _init_flow_field(self) -> None:
        """Initialize flow field (Perlin-like noise field)."""
        self.flow_resolution = 20
        self.flow_particles: list[dict[str, float]] = []
        self.max_flow_particles = 200

        # Initialize particles
        for _ in range(self.max_flow_particles):
            self.flow_particles.append(
                {
                    "x": random.random() * self.width,
                    "y": random.random() * self.height,
                    "life": random.random() * 50 + 50,
                }
            )

    def _init_explosion(self) -> None:
        """Initialize explosion particles."""
        self.explosion_particles: list[dict[str, float]] = []
        self.explosion_active = False
        self.explosion_frame = 0

    def _init_feedback(self) -> None:
        """Initialize feedback buffer."""
        self.feedback_buffer: Image.Image | None = None

    def _init_water(self) -> None:
        """Initialize water ripple state."""
        self.ripples: list[dict[str, float]] = []

    def render(self, frame_idx: int, time_pos: float) -> Image.Image:
        """Render VJing effects for the current frame.

        Args:
            frame_idx: Frame index.
            time_pos: Time position in seconds.

        Returns:
            RGBA image with VJing effects.
        """
        img = self.create_transparent_image()

        # Get current energy values
        safe_idx = min(frame_idx, len(self.energy) - 1)
        energy = self.energy[safe_idx]
        bass = self.bass_energy[safe_idx]
        mid = self.mid_energy[safe_idx]
        treble = self.treble_energy[safe_idx]
        fft = self.fft_data[safe_idx] if safe_idx < len(self.fft_data) else np.zeros(32)
        is_beat = frame_idx in self.beats

        # Context dict for effects
        ctx = {
            "energy": energy,
            "bass": bass,
            "mid": mid,
            "treble": treble,
            "fft": fft,
            "is_beat": is_beat,
        }

        # Render effects with transitions
        if self.transitions_enabled and len(self.active_effects) > 1:
            self._render_with_transitions(img, frame_idx, time_pos, ctx)
        else:
            # Render all active effects (composited together)
            for effect_name in self.active_effects:
                effect_method = getattr(self, f"_render_{effect_name}", self._render_wave)
                effect_method(img, frame_idx, time_pos, ctx)

        return img

    def _calculate_effect_alpha(self, effect_idx: int, time_pos: float) -> float:
        """Calculate alpha multiplier for crossfade between effects.

        At any time, one effect is "dominant" (the one whose window contains time_pos).
        During the transition period at the end of each window, the dominant effect
        fades out while the next effect fades in.

        Args:
            effect_idx: Index of the effect in active_effects.
            time_pos: Current time position in seconds.

        Returns:
            Alpha multiplier (0.0 to 1.0).
        """
        num_effects = len(self.active_effects)
        if num_effects <= 1:
            return 1.0

        cycle = self.effect_cycle_duration
        total_cycle = cycle * num_effects
        fade = self.transition_duration

        t = time_pos % total_cycle

        # Which effect is dominant (whose window contains t)?
        dominant_idx = int(t / cycle) % num_effects
        # Position within the dominant effect's window
        pos_in_window = t % cycle

        # Are we in the transition period (end of window)?
        if pos_in_window >= cycle - fade:
            # Transition period - crossfade between dominant and next
            transition_progress = (pos_in_window - (cycle - fade)) / fade  # 0 to 1
            next_idx = (dominant_idx + 1) % num_effects

            if effect_idx == dominant_idx:
                # Outgoing effect
                return 1.0 - transition_progress
            elif effect_idx == next_idx:
                # Incoming effect
                return transition_progress
            else:
                return 0.0
        else:
            # No transition - only dominant effect is visible
            if effect_idx == dominant_idx:
                return 1.0
            else:
                return 0.0

    def _render_with_transitions(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render effects with smooth transitions between them.

        Args:
            img: Target image to render onto.
            frame_idx: Frame index.
            time_pos: Time position in seconds.
            ctx: Audio context dictionary.
        """
        for idx, effect_name in enumerate(self.active_effects):
            alpha = self._calculate_effect_alpha(idx, time_pos)

            if alpha < 0.01:
                continue  # Skip nearly invisible effects

            # Create temporary image for this effect
            effect_img = self.create_transparent_image()

            # Render effect
            effect_method = getattr(self, f"_render_{effect_name}", self._render_wave)
            effect_method(effect_img, frame_idx, time_pos, ctx)

            # Apply alpha to effect image
            if alpha < 0.99:
                # Reduce alpha of entire effect image
                effect_data = np.array(effect_img)
                effect_data[:, :, 3] = (effect_data[:, :, 3] * alpha).astype(np.uint8)
                effect_img = Image.fromarray(effect_data, "RGBA")

            # Composite onto main image using alpha_composite (not paste)
            # paste with mask doesn't handle transparent backgrounds correctly
            img_data = np.array(img)
            effect_data = np.array(effect_img)
            
            # Manual alpha compositing: result = effect + img * (1 - effect_alpha)
            effect_alpha = effect_data[:, :, 3:4].astype(np.float32) / 255.0
            result = (
                effect_data[:, :, :3].astype(np.float32) * effect_alpha
                + img_data[:, :, :3].astype(np.float32) * (1 - effect_alpha)
            ).astype(np.uint8)
            result_alpha = np.clip(
                effect_data[:, :, 3].astype(np.float32)
                + img_data[:, :, 3].astype(np.float32) * (1 - effect_alpha[:, :, 0]),
                0,
                255,
            ).astype(np.uint8)
            
            # Update img in place
            combined = np.dstack([result, result_alpha])
            img.paste(Image.fromarray(combined, "RGBA"))

    # ========================================================================
    # RHYTHM-SYNCHRONIZED EFFECTS
    # ========================================================================

    def _render_pulse(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render beat pulse effect - luminosity/size variation on beats."""
        if not ctx["is_beat"]:
            return

        draw = ImageDraw.Draw(img)
        center = (self.width // 2, self.height // 2)

        # Pulse circle that expands from center
        frames_since_beat = 0
        for b in reversed(self.beats):
            if b <= frame_idx:
                frames_since_beat = frame_idx - b
                break

        max_radius = min(self.width, self.height) // 2
        decay = math.exp(-frames_since_beat / 10)
        radius = int(max_radius * decay * self.intensity)
        alpha = int(150 * decay * self.intensity)

        if radius > 5:
            # Draw expanding ring
            for thickness in range(3):
                r = radius + thickness * 5
                a = max(0, alpha - thickness * 40)
                draw.ellipse(
                    [center[0] - r, center[1] - r, center[0] + r, center[1] + r],
                    outline=(255, 255, 255, a),
                    width=3,
                )

    def _render_strobe(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render intelligent strobe effect."""
        energy = ctx["energy"]
        treble = ctx["treble"]

        # Strobe activates on high energy or treble
        if energy > 0.3 or treble > 0.5:
            # Strobe frequency increases with energy
            strobe_rate = 2 if energy > 0.7 else 3 if energy > 0.5 else 4
            if frame_idx % strobe_rate < strobe_rate // 2 + 1:
                alpha = min(255, int(300 * energy * self.intensity))
                flash = Image.new("RGBA", (self.width, self.height), (255, 255, 255, alpha))
                img.paste(flash, (0, 0), flash)

    # ========================================================================
    # SPECTRUM-BASED EFFECTS
    # ========================================================================

    def _render_fft_bars(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render FFT frequency bars."""
        draw = ImageDraw.Draw(img)
        fft = ctx["fft"]
        n_bars = len(fft)

        bar_width = self.width // n_bars
        max_height = self.height * 0.6

        for i, amplitude in enumerate(fft):
            x = i * bar_width
            height = int(amplitude * max_height * self.intensity)

            # Color gradient based on frequency
            hue = i / n_bars
            r = int(255 * (1 - hue))
            g = int(255 * abs(0.5 - hue) * 2)
            b = int(255 * hue)
            alpha = int(180 * self.intensity)

            # Draw bar from bottom
            y = self.height - height
            draw.rectangle([x, y, x + bar_width - 2, self.height], fill=(r, g, b, alpha))

    def _render_fft_rings(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render FFT as concentric rings."""
        draw = ImageDraw.Draw(img)
        fft = ctx["fft"]
        center = (self.width // 2, self.height // 2)
        max_radius = min(self.width, self.height) // 2

        n_rings = min(16, len(fft))
        for i in range(n_rings):
            amplitude = fft[i * len(fft) // n_rings]
            base_radius = max_radius * (i + 1) / n_rings

            # Modulate radius by amplitude
            radius = int(base_radius * (0.8 + 0.4 * amplitude))

            # Rotate over time
            rotation = time_pos * (1 + i * 0.1)

            # Color based on frequency
            hue = i / n_rings
            r = int(255 * (1 - hue) * amplitude)
            g = int(100 + 155 * amplitude)
            b = int(255 * hue * amplitude)
            alpha = int(120 * self.intensity * (0.5 + amplitude * 0.5))

            # Draw arc
            n_points = 60
            points = []
            arc_length = math.pi * (0.5 + amplitude * 0.5)
            for j in range(n_points):
                angle = rotation + (j / n_points) * arc_length
                x = center[0] + radius * math.cos(angle)
                y = center[1] + radius * math.sin(angle)
                points.append((x, y))

            if len(points) >= 2:
                draw.line(points, fill=(r, g, b, alpha), width=2)

    def _render_bass_warp(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render bass-driven distortion/warp effect."""
        draw = ImageDraw.Draw(img)
        bass = ctx["bass"]

        if bass < 0.2:
            return

        center = (self.width // 2, self.height // 2)

        # Draw warped concentric shapes
        n_shapes = int(10 * bass * self.intensity)
        for i in range(n_shapes):
            progress = i / max(n_shapes, 1)
            base_radius = 50 + progress * min(self.width, self.height) * 0.4

            # Warp amount based on bass
            warp = bass * 30 * self.intensity

            # Draw warped polygon
            n_points = 6 + i % 3
            points = []
            for j in range(n_points):
                angle = (j / n_points) * 2 * math.pi + time_pos
                noise = math.sin(angle * 3 + time_pos * 5) * warp
                r = base_radius + noise
                x = center[0] + r * math.cos(angle)
                y = center[1] + r * math.sin(angle)
                points.append((x, y))
            points.append(points[0])  # Close shape

            alpha = int(100 * (1 - progress) * self.intensity)
            color = (int(255 * bass), 50, int(255 * (1 - bass)), alpha)
            draw.line(points, fill=color, width=2)

    # ========================================================================
    # PARTICLE SYSTEMS
    # ========================================================================

    def _render_particles(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render rhythmic particle effect."""
        draw = ImageDraw.Draw(img)
        energy = ctx["energy"]
        is_beat = ctx["is_beat"]

        # Spawn extra particles on beats
        if is_beat and len(self.particles) < self.max_particles + 20:
            for _ in range(5):
                self._spawn_particle()

        # Update and draw particles
        for particle in self.particles:
            # Update position with energy-based speed
            speed_mult = 1 + energy * 3
            particle["x"] += particle["vx"] * speed_mult
            particle["y"] += particle["vy"] * speed_mult
            particle["life"] -= 1

            # Wrap around
            if particle["x"] < 0:
                particle["x"] = self.width
            elif particle["x"] > self.width:
                particle["x"] = 0
            if particle["y"] < 0:
                particle["y"] = self.height
            elif particle["y"] > self.height:
                particle["y"] = 0

            # Respawn if dead
            if particle["life"] <= 0:
                particle["life"] = random.random() * 100
                particle["x"] = random.random() * self.width
                particle["y"] = random.random() * self.height

            # Draw particle
            size = int(particle["size"] * (1 + energy * 0.5) * self.intensity)
            alpha = int(150 * self.intensity * (particle["life"] / 100))
            color = (*particle["color"], alpha)

            x, y = int(particle["x"]), int(particle["y"])
            draw.ellipse([x - size, y - size, x + size, y + size], fill=color)

    def _render_flow_field(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render flow field effect using Perlin noise field."""
        draw = ImageDraw.Draw(img)
        energy = ctx["energy"]
        bass = ctx["bass"]

        # Flow field parameters
        scale = 0.008  # Noise scale (smaller = smoother)
        time_scale = 0.3  # Time evolution speed
        speed = 2 + energy * 5

        for particle in self.flow_particles:
            # Get flow direction from Perlin noise
            nx = particle["x"] * scale
            ny = particle["y"] * scale
            # Use FBM for more natural flow patterns
            noise_val = fbm2d(
                nx + time_pos * time_scale, ny + time_pos * time_scale * 0.7, octaves=3
            )
            angle = noise_val * math.pi * 2

            # Apply velocity
            particle["x"] += math.cos(angle) * speed
            particle["y"] += math.sin(angle) * speed
            particle["life"] -= 1

            # Respawn if out of bounds or dead
            if (
                particle["x"] < 0
                or particle["x"] > self.width
                or particle["y"] < 0
                or particle["y"] > self.height
                or particle["life"] <= 0
            ):
                particle["x"] = random.random() * self.width
                particle["y"] = random.random() * self.height
                particle["life"] = random.random() * 50 + 50

            # Draw particle as small line in flow direction
            x, y = int(particle["x"]), int(particle["y"])
            length = 5 + bass * 10
            x2 = x + int(math.cos(angle) * length)
            y2 = y + int(math.sin(angle) * length)

            # Color based on position and noise
            hue = (particle["x"] / self.width + particle["y"] / self.height) / 2
            r = int(100 + 155 * (1 - hue))
            g = int(150 + 105 * energy)
            b = int(100 + 155 * hue)
            alpha = int(100 * self.intensity * (particle["life"] / 100))

            draw.line([(x, y), (x2, y2)], fill=(r, g, b, alpha), width=1)

    def _render_explosion(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render explosion/implosion effect on beats."""
        draw = ImageDraw.Draw(img)
        is_beat = ctx["is_beat"]
        energy = ctx["energy"]
        center = (self.width // 2, self.height // 2)

        # Trigger explosion on strong beats
        if is_beat and energy > 0.6 and not self.explosion_active:
            self.explosion_active = True
            self.explosion_frame = frame_idx
            self.explosion_particles = []
            # Spawn explosion particles
            n_particles = 100
            for _ in range(n_particles):
                angle = random.random() * 2 * math.pi
                speed = random.random() * 15 + 5
                self.explosion_particles.append(
                    {
                        "x": float(center[0]),
                        "y": float(center[1]),
                        "vx": math.cos(angle) * speed,
                        "vy": math.sin(angle) * speed,
                        "size": random.random() * 5 + 2,
                        "color": random.choice(
                            [(255, 200, 50), (255, 100, 0), (255, 255, 100), (255, 150, 0)]
                        ),
                        "life": 40 + random.random() * 20,
                    }
                )

        # Update and draw explosion particles
        if self.explosion_active:
            frames_since = frame_idx - self.explosion_frame
            if frames_since > 60:
                self.explosion_active = False
                return

            for p in self.explosion_particles:
                # Update position with gravity
                p["x"] += p["vx"]
                p["y"] += p["vy"]
                p["vy"] += 0.3  # Gravity
                p["life"] -= 1

                if p["life"] > 0:
                    x, y = int(p["x"]), int(p["y"])
                    size = int(p["size"] * (p["life"] / 60) * self.intensity)
                    alpha = int(200 * (p["life"] / 60) * self.intensity)

                    if 0 <= x < self.width and 0 <= y < self.height:
                        draw.ellipse(
                            [x - size, y - size, x + size, y + size],
                            fill=(*p["color"], alpha),
                        )

    # ========================================================================
    # GEOMETRIC EFFECTS
    # ========================================================================

    def _render_kaleidoscope(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render geometric kaleidoscope effect."""
        draw = ImageDraw.Draw(img)
        energy = ctx["energy"]
        center = (self.width // 2, self.height // 2)

        n_segments = 8
        rotation = time_pos * 0.5

        # Draw kaleidoscope pattern
        for segment in range(n_segments):
            base_angle = (segment / n_segments) * 2 * math.pi + rotation

            # Draw shapes in each segment
            n_shapes = 5
            for i in range(n_shapes):
                distance = 50 + i * 60 * self.intensity
                size = 20 + energy * 30

                # Position in segment
                angle = base_angle + math.sin(time_pos + i) * 0.2
                x = center[0] + distance * math.cos(angle)
                y = center[1] + distance * math.sin(angle)

                # Color varies by segment and shape
                hue = (segment / n_segments + i * 0.1) % 1.0
                r = int(255 * (1 - hue))
                g = int(255 * abs(0.5 - hue) * 2)
                b = int(255 * hue)
                alpha = int(150 * self.intensity * (1 - i / n_shapes))

                # Draw polygon
                n_sides = 3 + i % 3
                points = []
                for j in range(n_sides):
                    pa = angle + (j / n_sides) * 2 * math.pi
                    px = x + size * math.cos(pa)
                    py = y + size * math.sin(pa)
                    points.append((px, py))
                points.append(points[0])

                draw.polygon(points, outline=(r, g, b, alpha))

    def _render_lissajous(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render Lissajous curves."""
        draw = ImageDraw.Draw(img)
        energy = ctx["energy"]
        bass = ctx["bass"]
        center = (self.width // 2, self.height // 2)

        # Lissajous parameters (modulated by audio)
        a = 3 + int(bass * 4)
        b = 4 + int(energy * 3)
        delta = time_pos

        # Draw multiple curves with different phases
        n_curves = 3
        for curve in range(n_curves):
            points = []
            phase_offset = curve * math.pi / n_curves

            amplitude_x = (self.width * 0.35) * self.intensity
            amplitude_y = (self.height * 0.35) * self.intensity

            for t in np.linspace(0, 2 * math.pi, 200):
                x = center[0] + amplitude_x * math.sin(a * t + delta + phase_offset)
                y = center[1] + amplitude_y * math.sin(b * t)
                points.append((x, y))

            # Color per curve
            colors = [
                (255, 100, 100, 150),
                (100, 255, 100, 150),
                (100, 100, 255, 150),
            ]
            color = colors[curve % len(colors)]

            if len(points) >= 2:
                draw.line(points, fill=color, width=2)

    def _render_tunnel(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render infinite tunnel effect with LFO modulation."""
        draw = ImageDraw.Draw(img)
        energy = ctx["energy"]
        center = (self.width // 2, self.height // 2)

        # LFO modulation
        rotation_mod = self.lfo_slow.value(time_pos) * 0.5  # Rotation wobble
        scale_mod = 1.0 + self.lfo_medium.value(time_pos) * 0.2  # Size pulsing
        hue_offset = self.lfo_triangle.value_normalized(time_pos)  # Color cycling

        # Tunnel parameters
        n_rings = 20
        speed = time_pos * 2

        for i in range(n_rings):
            # Ring distance (creates depth illusion)
            z = (i / n_rings + speed) % 1.0
            if z < 0.1:
                continue

            # Size based on "depth" with LFO modulation
            scale = 1 / z * scale_mod
            radius = min(self.width, self.height) * 0.1 * scale

            if radius > max(self.width, self.height):
                continue

            # Rotation with LFO modulation
            rotation = time_pos * 0.5 + i * 0.1 + rotation_mod

            # Draw polygon ring
            n_sides = 6
            points = []
            for j in range(n_sides):
                angle = rotation + (j / n_sides) * 2 * math.pi
                x = center[0] + radius * math.cos(angle)
                y = center[1] + radius * math.sin(angle)
                points.append((x, y))
            points.append(points[0])

            # Color fades with depth, modulated by LFO
            alpha = int(200 * (1 - z) * self.intensity)
            hue = (i / n_rings + hue_offset) % 1.0
            r = int(100 + 155 * (1 - hue))
            g = int(50 + 100 * energy)
            b = int(100 + 155 * hue)

            draw.line(points, fill=(r, g, b, alpha), width=2)

    def _render_spiral(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render animated spiral effect with LFO modulation."""
        draw = ImageDraw.Draw(img)
        energy = ctx["energy"]
        center = (self.width // 2, self.height // 2)
        max_radius = min(self.width, self.height) * 0.45

        # LFO modulation
        rotation_speed = 2 + self.lfo_medium.value(time_pos) * 0.5  # Speed variation
        scale_mod = 1.0 + self.lfo_slow.value(time_pos) * 0.15  # Breathing effect
        color_shift = self.lfo_triangle.value_normalized(time_pos)  # Color shift

        # Draw spiral
        points = []
        n_points = 200
        rotations = 4 + energy * 2 + self.lfo_fast.value(time_pos) * 0.5

        for i in range(n_points):
            progress = i / n_points
            angle = progress * rotations * 2 * math.pi + time_pos * rotation_speed
            radius = progress * max_radius * scale_mod

            x = center[0] + radius * math.cos(angle)
            y = center[1] + radius * math.sin(angle)
            points.append((x, y))

        # Draw with gradient color, shifted by LFO
        if len(points) >= 2:
            for i in range(len(points) - 1):
                progress = (i / len(points) + color_shift) % 1.0
                r = int(255 * (1 - progress))
                g = int(100 + 155 * energy)
                b = int(255 * progress)
                alpha = int(180 * self.intensity)
                draw.line([points[i], points[i + 1]], fill=(r, g, b, alpha), width=2)

    # ========================================================================
    # POST-PROCESSING EFFECTS
    # ========================================================================

    def _render_chromatic(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render chromatic aberration effect."""
        bass = ctx["bass"]

        # Offset amount based on bass
        offset = int(5 + bass * 15 * self.intensity)

        if offset < 2:
            return

        # Get image data
        data = np.array(img)

        # Separate and offset color channels
        r_channel = np.roll(data[:, :, 0], offset, axis=1)
        b_channel = np.roll(data[:, :, 2], -offset, axis=1)

        # Recombine
        data[:, :, 0] = r_channel
        data[:, :, 2] = b_channel

        # Update image
        result = Image.fromarray(data, "RGBA")
        img.paste(result, (0, 0))

    def _render_pixelate(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render pixelation/mosaic effect."""
        bass = ctx["bass"]

        # Pixel size based on bass
        pixel_size = int(5 + bass * 20 * self.intensity)

        if pixel_size < 3:
            return

        # Create pixelated overlay
        small = img.resize(
            (self.width // pixel_size, self.height // pixel_size), Image.Resampling.NEAREST
        )
        pixelated = small.resize((self.width, self.height), Image.Resampling.NEAREST)

        # Blend with original based on energy
        alpha = int(255 * bass * self.intensity)
        mask = Image.new("L", (self.width, self.height), alpha)
        img.paste(Image.composite(pixelated, img, mask), (0, 0))

    def _render_feedback(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render feedback/trail effect."""
        energy = ctx["energy"]

        if self.feedback_buffer is None:
            self.feedback_buffer = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

        # Decay factor (higher = longer trails)
        decay = 0.85 + energy * 0.1

        # Rotate feedback slightly
        angle = math.sin(time_pos) * 2

        # Transform feedback buffer
        rotated = self.feedback_buffer.rotate(
            angle, center=(self.width // 2, self.height // 2), expand=False
        )

        # Apply decay
        r, g, b, a = rotated.split()
        a = a.point(lambda x: int(x * decay))
        decayed = Image.merge("RGBA", (r, g, b, a))

        # Composite: feedback behind current frame
        result = Image.alpha_composite(decayed, img)

        # Store for next frame
        self.feedback_buffer = result.copy()

        # Update img
        img.paste(result, (0, 0))

    # ========================================================================
    # NATURE-INSPIRED EFFECTS
    # ========================================================================

    def _render_fire(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render fire/flame effect with Perlin noise turbulence."""
        draw = ImageDraw.Draw(img)
        bass = ctx["bass"]

        # Fire height based on bass
        fire_height = int(self.height * 0.4 * (0.5 + bass * 0.5) * self.intensity)

        for y in range(fire_height):
            progress = y / max(fire_height, 1)

            # Color gradient: yellow -> orange -> red -> transparent
            if progress < 0.3:
                r, g, b = 255, int(255 - progress * 200), int(100 * (1 - progress * 3))
            elif progress < 0.6:
                r, g, b = 255, int(180 - (progress - 0.3) * 400), 0
            else:
                r, g, b = int(255 - (progress - 0.6) * 400), 0, 0

            alpha = int(150 * (1 - progress) * self.intensity)

            # Animated flame shape using turbulence noise
            for x in range(0, self.width, 3):
                # Use turbulence for more natural flame motion
                noise = turbulence2d(
                    x * 0.02 + time_pos * 2,
                    y * 0.03 + time_pos * 3,
                    octaves=3
                ) * 30
                flame_y = self.height - y + int(noise * (1 - progress))

                if 0 <= flame_y < self.height:
                    draw.point((x, flame_y), fill=(r, g, b, alpha))

    def _render_water(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render water ripple effect."""
        draw = ImageDraw.Draw(img)
        is_beat = ctx["is_beat"]
        energy = ctx["energy"]

        # Add new ripple on beat
        if is_beat:
            self.ripples.append(
                {
                    "x": random.randint(self.width // 4, 3 * self.width // 4),
                    "y": random.randint(self.height // 4, 3 * self.height // 4),
                    "radius": 0.0,
                    "life": 60.0,
                }
            )

        # Update and draw ripples
        new_ripples = []
        for ripple in self.ripples:
            ripple["radius"] += 5 + energy * 5
            ripple["life"] -= 1

            if ripple["life"] > 0:
                new_ripples.append(ripple)

                # Draw concentric circles
                alpha = int(100 * (ripple["life"] / 60) * self.intensity)
                for i in range(3):
                    r = ripple["radius"] - i * 10
                    if r > 0:
                        draw.ellipse(
                            [
                                ripple["x"] - r,
                                ripple["y"] - r,
                                ripple["x"] + r,
                                ripple["y"] + r,
                            ],
                            outline=(100, 150, 255, alpha // (i + 1)),
                            width=2,
                        )

        self.ripples = new_ripples

    def _render_aurora(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render aurora borealis effect with Perlin noise."""
        draw = ImageDraw.Draw(img)
        energy = ctx["energy"]
        mid = ctx["mid"]

        # Aurora parameters
        n_bands = 5
        base_y = self.height * 0.3

        for band in range(n_bands):
            points = []
            band_offset = band * 30

            for x in range(0, self.width, 5):
                # Use FBM noise for organic aurora movement
                noise_scale = 0.003
                y = base_y + band_offset
                # Primary wave using Perlin
                y += fbm2d(
                    x * noise_scale + time_pos * 0.2,
                    band * 0.5 + time_pos * 0.1,
                    octaves=3
                ) * 80 * self.intensity
                # Secondary modulation
                y += perlin2d(
                    x * noise_scale * 2 + time_pos * 0.3,
                    band * 0.3
                ) * 30 * energy
                points.append((x, y))

            # Aurora colors: green, blue, purple, pink
            colors = [
                (100, 255, 150),  # Green
                (50, 200, 255),  # Cyan
                (150, 100, 255),  # Purple
                (255, 100, 200),  # Pink
                (100, 255, 200),  # Teal
            ]
            base_color = colors[band % len(colors)]

            # Draw band with varying alpha
            if len(points) >= 2:
                alpha = int(80 * self.intensity * (0.5 + mid * 0.5))
                color = (*base_color, alpha)
                draw.line(points, fill=color, width=8 - band)

                # Add glow
                if band < 2:
                    glow_alpha = alpha // 2
                    glow_color = (*base_color, glow_alpha)
                    # Offset points for glow
                    glow_points = [(x, y - 5) for x, y in points]
                    draw.line(glow_points, fill=glow_color, width=15)

    # ========================================================================
    # CLASSIC EFFECTS
    # ========================================================================

    def _render_wave(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render wave effect (default)."""
        draw = ImageDraw.Draw(img)
        energy = ctx["energy"]

        # Draw flowing waves
        n_waves = 5
        for i in range(n_waves):
            points = []
            phase = time_pos * 2 + i * 0.5
            amplitude = 30 * (1 + energy) * self.intensity

            for x in range(0, self.width, 5):
                y = self.height // 2 + math.sin(x * 0.02 + phase) * amplitude
                y += math.sin(x * 0.01 - time_pos) * amplitude * 0.5
                points.append((x, int(y)))

            if len(points) >= 2:
                alpha = int(100 * self.intensity / (i + 1))
                color = (100, 200, 255, alpha)
                draw.line(points, fill=color, width=2)

    def _render_neon(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render neon glow effect."""
        draw = ImageDraw.Draw(img)
        energy = ctx["energy"]

        # Draw neon shapes
        colors = [
            (255, 0, 255, 150),  # Magenta
            (0, 255, 255, 150),  # Cyan
            (255, 255, 0, 150),  # Yellow
        ]

        n_shapes = 3
        for i in range(n_shapes):
            # Pulsating size
            base_size = 100 + i * 50
            pulse = math.sin(time_pos * 2 + i) * 20 * energy
            size = int((base_size + pulse) * self.intensity)

            x = self.width // 2 + math.cos(time_pos + i * 2) * 100
            y = self.height // 2 + math.sin(time_pos * 0.5 + i) * 50

            color = colors[i % len(colors)]

            # Draw glowing shape with multiple layers
            for offset in range(3, 0, -1):
                alpha = color[3] // offset
                draw.ellipse(
                    [
                        x - size - offset * 5,
                        y - size - offset * 5,
                        x + size + offset * 5,
                        y + size + offset * 5,
                    ],
                    outline=(*color[:3], alpha),
                    width=2,
                )

    def _render_vinyl(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render vinyl/record effect."""
        draw = ImageDraw.Draw(img)
        energy = ctx["energy"]
        center = (self.width // 2, self.height // 2)
        max_radius = min(self.width, self.height) // 3
        rotation = time_pos * 2 * math.pi * (0.5 + energy * 0.5)

        n_grooves = 15
        for i in range(n_grooves):
            radius = max_radius * (i + 1) / n_grooves
            alpha = int(60 * self.intensity)

            # Draw partial arc that rotates
            start_angle = rotation + i * 0.2
            arc_length = math.pi * (0.8 + energy * 0.4)

            # Draw arc as points
            n_points = 30
            for j in range(n_points):
                angle = start_angle + (j / n_points) * arc_length
                x = center[0] + radius * math.cos(angle)
                y = center[1] + radius * math.sin(angle)

                # Slight color variation
                gray = 180 + int(20 * math.sin(angle * 5))
                draw.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(gray, gray, gray, alpha))

    # ========================================================================
    # FRACTAL EFFECTS
    # ========================================================================

    def _init_fractal(self) -> None:
        """Initialize fractal computation grid.

        Pre-computes the coordinate grid for Julia set rendering.
        Uses lower resolution for performance, then upscales.
        """
        # Use lower resolution for performance (will be upscaled)
        self.fractal_scale = 4  # Render at 1/4 resolution
        self.fractal_width = self.width // self.fractal_scale
        self.fractal_height = self.height // self.fractal_scale

        # Pre-compute coordinate grids (complex plane)
        # These will be transformed per-frame based on zoom/position
        y_coords = np.linspace(-1.5, 1.5, self.fractal_height)
        x_coords = np.linspace(-2.0, 2.0, self.fractal_width)
        self.fractal_x, self.fractal_y = np.meshgrid(x_coords, y_coords)

        # Color palette for fractal (fire-like gradient)
        self.fractal_palette = self._create_fractal_palette()

    def _create_fractal_palette(self) -> NDArray:
        """Create a color palette for fractal coloring.

        Returns:
            Array of shape (256, 3) with RGB colors.
        """
        palette = np.zeros((256, 3), dtype=np.uint8)

        for i in range(256):
            t = i / 255.0

            if t < 0.16:
                # Black to dark blue
                palette[i] = [0, 0, int(t * 6 * 128)]
            elif t < 0.42:
                # Dark blue to blue-cyan
                p = (t - 0.16) / 0.26
                palette[i] = [0, int(p * 200), 128 + int(p * 127)]
            elif t < 0.6425:
                # Blue-cyan to yellow
                p = (t - 0.42) / 0.2225
                palette[i] = [int(p * 255), 200 + int(p * 55), int(255 * (1 - p))]
            elif t < 0.8575:
                # Yellow to orange-red
                p = (t - 0.6425) / 0.215
                palette[i] = [255, int(255 - p * 200), 0]
            else:
                # Orange-red to white
                p = (t - 0.8575) / 0.1425
                palette[i] = [255, int(55 + p * 200), int(p * 255)]

        return palette

    def _render_fractal(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render animated Julia set fractal.

        The Julia set is computed with parameters modulated by audio.
        Uses GPU acceleration when available.

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position in seconds.
            ctx: Audio context dict.
        """
        # Try GPU rendering first
        gpu_img = self._render_gpu_effect("fractal", time_pos, ctx)
        if gpu_img:
            img.paste(gpu_img, (0, 0), gpu_img)
            return

        # CPU fallback
        energy = ctx["energy"]
        bass = ctx["bass"]
        mid = ctx["mid"]

        # Julia set parameter c - animate it for morphing effect
        c_radius = 0.7 + bass * 0.15
        c_angle = time_pos * 0.5 + mid * math.pi
        c_real = c_radius * math.cos(c_angle)
        c_imag = c_radius * math.sin(c_angle)

        # Zoom level - affected by energy
        zoom = 1.5 + energy * 0.5

        # Rotation
        rotation = time_pos * 0.2

        # Create rotated and zoomed coordinate grid
        cos_r = math.cos(rotation)
        sin_r = math.sin(rotation)

        # Apply rotation and zoom to coordinates
        x_rot = (self.fractal_x * cos_r - self.fractal_y * sin_r) / zoom
        y_rot = (self.fractal_x * sin_r + self.fractal_y * cos_r) / zoom

        # Create complex grid
        z = x_rot + 1j * y_rot
        c = complex(c_real, c_imag)

        # Compute Julia set with vectorized operations
        max_iter = 50
        iterations = np.zeros(z.shape, dtype=np.int32)
        mask = np.ones(z.shape, dtype=bool)

        for i in range(max_iter):
            z[mask] = z[mask] ** 2 + c
            escaped = np.abs(z) > 4
            new_escaped = escaped & mask
            iterations[new_escaped] = i
            mask[escaped] = False
            if not np.any(mask):
                break

        iterations[mask] = max_iter
        normalized = (iterations * 255 // max_iter).astype(np.uint8)
        colored = self.fractal_palette[normalized]

        alpha_value = int(200 * self.intensity)
        fractal_small = Image.fromarray(colored, mode="RGB")
        fractal_full = fractal_small.resize(
            (self.width, self.height), Image.Resampling.BILINEAR
        )

        fractal_rgba = fractal_full.convert("RGBA")
        r, g, b, _ = fractal_rgba.split()
        alpha = Image.new("L", (self.width, self.height), alpha_value)
        fractal_rgba = Image.merge("RGBA", (r, g, b, alpha))

        img.paste(fractal_rgba, (0, 0), fractal_rgba)

    # ========================================================================
    # RADAR EFFECT
    # ========================================================================

    def _render_radar(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render radar sweep effect.

        Rotating beam with blips appearing on beats.

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position in seconds.
            ctx: Audio context dict.
        """
        draw = ImageDraw.Draw(img)
        energy = ctx["energy"]
        bass = ctx["bass"]
        is_beat = ctx["is_beat"]

        cx, cy = self.width // 2, self.height // 2
        max_radius = min(self.width, self.height) // 2 - 20

        # Sweep angle - rotates over time, speed affected by energy
        sweep_speed = 1.0 + energy * 0.5
        angle = time_pos * sweep_speed * 2

        # Draw concentric circles (grid)
        for r_ratio in [0.25, 0.5, 0.75, 1.0]:
            r = int(max_radius * r_ratio)
            draw.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                outline=(0, 100, 0, int(60 * self.intensity)),
                width=1,
            )

        # Draw cross lines
        alpha = int(60 * self.intensity)
        draw.line([(cx - max_radius, cy), (cx + max_radius, cy)], fill=(0, 100, 0, alpha))
        draw.line([(cx, cy - max_radius), (cx, cy + max_radius)], fill=(0, 100, 0, alpha))

        # Draw sweep beam with trail
        num_trail = 30
        for i in range(num_trail):
            trail_angle = angle - i * 0.03
            trail_alpha = int((1.0 - i / num_trail) * 180 * self.intensity)
            x_end = cx + int(math.cos(trail_angle) * max_radius)
            y_end = cy + int(math.sin(trail_angle) * max_radius)

            # Brighter green for main beam
            if i < 3:
                color = (100, 255, 100, trail_alpha)
            else:
                color = (0, int(200 * (1 - i / num_trail)), 0, trail_alpha)

            draw.line([(cx, cy), (x_end, y_end)], fill=color, width=2 if i < 5 else 1)

        # Draw blips on beats
        if is_beat:
            # Add new blip at random position on current sweep line
            if not hasattr(self, "radar_blips"):
                self.radar_blips = []
            blip_dist = random.random() * max_radius * 0.8 + max_radius * 0.1
            self.radar_blips.append({
                "angle": angle,
                "distance": blip_dist,
                "life": 30,
                "size": 3 + bass * 5,
            })

        # Draw and update blips
        if hasattr(self, "radar_blips"):
            new_blips = []
            for blip in self.radar_blips:
                blip["life"] -= 1
                if blip["life"] > 0:
                    bx = cx + int(math.cos(blip["angle"]) * blip["distance"])
                    by = cy + int(math.sin(blip["angle"]) * blip["distance"])
                    alpha = int((blip["life"] / 30) * 255 * self.intensity)
                    size = int(blip["size"])
                    draw.ellipse(
                        [bx - size, by - size, bx + size, by + size],
                        fill=(100, 255, 100, alpha),
                    )
                    new_blips.append(blip)
            self.radar_blips = new_blips[:50]  # Limit blips

    # ========================================================================
    # PLASMA EFFECT
    # ========================================================================

    def _init_plasma(self) -> None:
        """Initialize plasma effect coordinate grid."""
        self.plasma_scale = 4
        self.plasma_width = self.width // self.plasma_scale
        self.plasma_height = self.height // self.plasma_scale
        # Create coordinate grids
        y_coords = np.linspace(0, 4 * math.pi, self.plasma_height)
        x_coords = np.linspace(0, 4 * math.pi, self.plasma_width)
        self.plasma_x, self.plasma_y = np.meshgrid(x_coords, y_coords)

    def _render_plasma(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render animated plasma effect.

        Classic plasma using combined sine waves with audio modulation.
        Uses GPU acceleration when available.

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position in seconds.
            ctx: Audio context dict.
        """
        # Try GPU rendering first
        gpu_img = self._render_gpu_effect("plasma", time_pos, ctx)
        if gpu_img:
            img.paste(gpu_img, (0, 0), gpu_img)
            return

        # CPU fallback
        energy = ctx["energy"]
        bass = ctx["bass"]
        mid = ctx["mid"]

        # Time-based animation
        t = time_pos * 2

        # Plasma function - multiple sine waves combined
        # Each component modulated by different audio bands
        v1 = np.sin(self.plasma_x + t + bass * math.pi)
        v2 = np.sin(self.plasma_y + t * 0.7 + mid * math.pi)
        v3 = np.sin((self.plasma_x + self.plasma_y + t * 0.5) * 0.5)
        v4 = np.sin(
            np.sqrt(
                (self.plasma_x - 2 * math.pi) ** 2 + (self.plasma_y - 2 * math.pi) ** 2
            )
            + t
            + energy * math.pi
        )

        # Combine waves
        plasma = (v1 + v2 + v3 + v4) / 4.0

        # Normalize to 0-1
        plasma = (plasma + 1.0) / 2.0

        # Create RGB from plasma value
        # Use cycling colors based on time
        r = ((np.sin(plasma * math.pi * 2 + t) + 1) / 2 * 255).astype(np.uint8)
        g = ((np.sin(plasma * math.pi * 2 + t + 2 * math.pi / 3) + 1) / 2 * 255).astype(
            np.uint8
        )
        b = ((np.sin(plasma * math.pi * 2 + t + 4 * math.pi / 3) + 1) / 2 * 255).astype(
            np.uint8
        )

        # Stack to RGB
        rgb = np.stack([r, g, b], axis=-1)

        # Create image and upscale
        plasma_small = Image.fromarray(rgb, mode="RGB")
        plasma_full = plasma_small.resize(
            (self.width, self.height), Image.Resampling.BILINEAR
        )

        # Convert to RGBA with alpha
        plasma_rgba = plasma_full.convert("RGBA")
        r_ch, g_ch, b_ch, _ = plasma_rgba.split()
        alpha_value = int(180 * self.intensity)
        alpha = Image.new("L", (self.width, self.height), alpha_value)
        plasma_rgba = Image.merge("RGBA", (r_ch, g_ch, b_ch, alpha))

        # Composite
        img.paste(plasma_rgba, (0, 0), plasma_rgba)

    # ========================================================================
    # WORMHOLE EFFECT
    # ========================================================================

    def _init_wormhole(self) -> None:
        """Initialize wormhole effect coordinate grid."""
        self.wormhole_scale = 3
        self.wormhole_width = self.width // self.wormhole_scale
        self.wormhole_height = self.height // self.wormhole_scale
        # Create coordinate grid centered at origin
        y_coords = np.linspace(-1, 1, self.wormhole_height)
        x_coords = np.linspace(-1.5, 1.5, self.wormhole_width)  # Adjust for aspect ratio
        x_grid, y_grid = np.meshgrid(x_coords, y_coords)
        # Pre-compute polar coordinates
        self.wormhole_r = np.sqrt(x_grid**2 + y_grid**2)
        self.wormhole_theta = np.arctan2(y_grid, x_grid)

    def _render_wormhole(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render wormhole/tunnel vortex effect.

        Spiraling tunnel with depth illusion, pulled by bass.
        Uses GPU acceleration when available.

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position in seconds.
            ctx: Audio context dict.
        """
        # Try GPU rendering first
        gpu_img = self._render_gpu_effect("wormhole", time_pos, ctx)
        if gpu_img:
            img.paste(gpu_img, (0, 0), gpu_img)
            return

        # CPU fallback
        energy = ctx["energy"]
        bass = ctx["bass"]
        mid = ctx["mid"]
        is_beat = ctx["is_beat"]

        t = time_pos * 3
        twist = 3.0 + bass * 2.0
        pull = t * 2 + bass * 0.5

        spiral_angle = self.wormhole_theta + self.wormhole_r * twist - pull
        ring_pattern = np.sin(self.wormhole_r * 15 - pull * 3 + mid * math.pi)
        spiral_pattern = np.sin(spiral_angle * 8 + energy * math.pi)

        combined = (ring_pattern + spiral_pattern) / 2
        depth_fade = np.clip(self.wormhole_r * 1.5, 0.1, 1.0)
        combined = (combined + 1) / 2 * depth_fade

        hue_shift = t * 0.5
        r = ((np.sin(combined * math.pi + hue_shift) + 1) / 2 * 100 + 50).astype(np.uint8)
        g = ((np.sin(combined * math.pi + hue_shift + 1) + 1) / 2 * 50).astype(np.uint8)
        b = ((np.sin(combined * math.pi + hue_shift + 2) + 1) / 2 * 200 + 55).astype(
            np.uint8
        )

        if is_beat:
            r = np.clip(r.astype(np.int16) + 80, 0, 255).astype(np.uint8)
            g = np.clip(g.astype(np.int16) + 60, 0, 255).astype(np.uint8)
            b = np.clip(b.astype(np.int16) + 60, 0, 255).astype(np.uint8)

        rgb = np.stack([r, g, b], axis=-1)
        wormhole_small = Image.fromarray(rgb, mode="RGB")
        wormhole_full = wormhole_small.resize(
            (self.width, self.height), Image.Resampling.BILINEAR
        )

        wormhole_rgba = wormhole_full.convert("RGBA")
        r_ch, g_ch, b_ch, _ = wormhole_rgba.split()
        alpha_value = int(200 * self.intensity)
        alpha = Image.new("L", (self.width, self.height), alpha_value)
        wormhole_rgba = Image.merge("RGBA", (r_ch, g_ch, b_ch, alpha))

        img.paste(wormhole_rgba, (0, 0), wormhole_rgba)

    # ========================================================================
    # STARFIELD EFFECT
    # ========================================================================

    def _init_starfield(self) -> None:
        """Initialize starfield with 3D star positions."""
        self.num_stars = 300
        self.stars: list[dict[str, float]] = []
        for _ in range(self.num_stars):
            self._spawn_star()

    def _spawn_star(self, z: float | None = None) -> None:
        """Spawn a new star at random position.

        Args:
            z: Optional z depth (if None, random deep position).
        """
        self.stars.append({
            "x": (random.random() - 0.5) * 2,  # -1 to 1
            "y": (random.random() - 0.5) * 2,  # -1 to 1
            "z": z if z is not None else random.random() * 2 + 0.5,  # depth
            "brightness": random.random() * 0.5 + 0.5,
        })

    def _render_starfield(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render 3D starfield flying through space.

        Stars move towards camera, speed affected by energy.
        Brightness pulses on beats.

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position in seconds.
            ctx: Audio context dict.
        """
        draw = ImageDraw.Draw(img)
        energy = ctx["energy"]
        is_beat = ctx["is_beat"]
        bass = ctx["bass"]

        cx, cy = self.width // 2, self.height // 2

        # Speed based on energy
        speed = 0.02 + energy * 0.04

        new_stars = []
        for star in self.stars:
            # Move star towards camera
            star["z"] -= speed

            # Reset if passed camera
            if star["z"] <= 0.01:
                self._spawn_star(z=2.0 + random.random())
                continue

            # Project to 2D (perspective)
            px = int(cx + (star["x"] / star["z"]) * cx)
            py = int(cy + (star["y"] / star["z"]) * cy)

            # Check bounds
            if 0 <= px < self.width and 0 <= py < self.height:
                # Size based on depth (closer = bigger)
                size = max(1, int(3 / star["z"]))

                # Brightness based on depth and beat
                base_brightness = int((1 - star["z"] / 2.5) * 255 * star["brightness"])
                if is_beat:
                    base_brightness = min(255, base_brightness + 100)

                # Color - slight blue tint, whiter when closer
                blue_tint = int(star["z"] * 50)
                r = max(0, min(255, base_brightness - blue_tint // 2))
                g = max(0, min(255, base_brightness - blue_tint // 3))
                b = max(0, min(255, base_brightness + blue_tint))
                alpha = int(min(255, base_brightness) * self.intensity)

                # Draw star
                if size <= 1:
                    draw.point((px, py), fill=(r, g, b, alpha))
                else:
                    draw.ellipse(
                        [px - size, py - size, px + size, py + size],
                        fill=(r, g, b, alpha),
                    )

                # Motion trail for fast stars (close ones)
                if star["z"] < 0.5 and bass > 0.5:
                    trail_length = int((1 - star["z"]) * 20 * bass)
                    trail_x = int(cx + (star["x"] / (star["z"] + speed * 3)) * cx)
                    trail_y = int(cy + (star["y"] / (star["z"] + speed * 3)) * cy)
                    draw.line(
                        [(px, py), (trail_x, trail_y)],
                        fill=(r, g, b, alpha // 2),
                        width=max(1, size - 1),
                    )

            new_stars.append(star)

        self.stars = new_stars

        # Spawn new stars to maintain count
        while len(self.stars) < self.num_stars:
            self._spawn_star(z=2.0 + random.random())

    # ========================================================================
    # LIGHTNING EFFECT
    # ========================================================================

    def _render_lightning(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render lightning bolts on beats.

        Branching lightning from top to bottom or random points.
        Triggered by beats, intensity by bass.

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position in seconds.
            ctx: Audio context dict.
        """
        draw = ImageDraw.Draw(img)
        is_beat = ctx["is_beat"]
        bass = ctx["bass"]
        energy = ctx["energy"]

        # Only draw lightning on beats or high energy
        if not is_beat and energy < 0.7:
            return

        # Number of bolts based on energy
        num_bolts = 1 if is_beat else 0
        if energy > 0.8:
            num_bolts += 1

        for _ in range(num_bolts):
            # Start point (top area)
            start_x = random.randint(self.width // 4, 3 * self.width // 4)
            start_y = random.randint(0, self.height // 4)

            # End point (bottom area)
            end_x = start_x + random.randint(-self.width // 3, self.width // 3)
            end_y = random.randint(3 * self.height // 4, self.height)

            # Generate lightning path
            self._draw_lightning_bolt(draw, start_x, start_y, end_x, end_y, bass, depth=0)

    def _draw_lightning_bolt(
        self,
        draw: ImageDraw.ImageDraw,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        intensity: float,
        depth: int,
    ) -> None:
        """Recursively draw a branching lightning bolt.

        Args:
            draw: ImageDraw object.
            x1, y1: Start point.
            x2, y2: End point.
            intensity: Bolt intensity (affects brightness and branching).
            depth: Recursion depth.
        """
        if depth > 5:
            return

        # Calculate distance
        dx = x2 - x1
        dy = y2 - y1
        dist = math.sqrt(dx * dx + dy * dy)

        if dist < 10:
            return

        # Number of segments
        num_segments = max(3, int(dist / 30))

        # Build path with random offsets
        points = [(x1, y1)]
        for i in range(1, num_segments):
            t = i / num_segments
            # Base position
            px = x1 + dx * t
            py = y1 + dy * t
            # Add perpendicular offset
            offset = (random.random() - 0.5) * dist * 0.3 / (depth + 1)
            # Perpendicular direction
            perp_x = -dy / dist
            perp_y = dx / dist
            px += perp_x * offset
            py += perp_y * offset
            points.append((int(px), int(py)))
        points.append((x2, y2))

        # Draw main bolt
        brightness = int(255 * intensity * (1 - depth * 0.15))
        alpha = int(min(255, brightness + 50) * self.intensity)
        width = max(1, 4 - depth)

        # Core (white/blue)
        for i in range(len(points) - 1):
            draw.line(
                [points[i], points[i + 1]],
                fill=(200, 220, 255, alpha),
                width=width,
            )

        # Glow (wider, dimmer)
        if depth < 2:
            glow_alpha = alpha // 3
            for i in range(len(points) - 1):
                draw.line(
                    [points[i], points[i + 1]],
                    fill=(100, 150, 255, glow_alpha),
                    width=width + 4,
                )

        # Branching
        if depth < 3 and random.random() < 0.4 * intensity:
            # Pick a random point to branch from
            branch_idx = random.randint(1, len(points) - 2)
            bx, by = points[branch_idx]
            # Branch direction (angled from main)
            angle = math.atan2(dy, dx) + (random.random() - 0.5) * math.pi / 2
            branch_len = dist * (0.3 + random.random() * 0.3) / (depth + 1)
            bex = int(bx + math.cos(angle) * branch_len)
            bey = int(by + math.sin(angle) * branch_len)
            self._draw_lightning_bolt(draw, bx, by, bex, bey, intensity * 0.7, depth + 1)

    # ========================================================================
    # VORONOI EFFECT
    # ========================================================================

    def _init_voronoi(self) -> None:
        """Initialize Voronoi diagram points."""
        self.voronoi_num_points = 20
        self.voronoi_points: list[dict[str, Any]] = []
        for _ in range(self.voronoi_num_points):
            self.voronoi_points.append({
                "x": random.random() * self.width,
                "y": random.random() * self.height,
                "vx": (random.random() - 0.5) * 2,
                "vy": (random.random() - 0.5) * 2,
                "color": (
                    random.randint(50, 255),
                    random.randint(50, 255),
                    random.randint(50, 255),
                ),
            })

    def _render_voronoi(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render animated Voronoi diagram.

        Cells colored by nearest point, points move with audio.
        Uses GPU acceleration when available.

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position in seconds.
            ctx: Audio context dict.
        """
        # Try GPU rendering first
        gpu_img = self._render_gpu_effect("voronoi", time_pos, ctx)
        if gpu_img:
            img.paste(gpu_img, (0, 0), gpu_img)
            return

        # CPU fallback
        energy = ctx["energy"]
        bass = ctx["bass"]
        is_beat = ctx["is_beat"]

        # Update point positions
        speed_mult = 1 + energy * 3
        for point in self.voronoi_points:
            point["x"] += point["vx"] * speed_mult
            point["y"] += point["vy"] * speed_mult

            if point["x"] < 0 or point["x"] >= self.width:
                point["vx"] *= -1
                point["x"] = max(0, min(self.width - 1, point["x"]))
            if point["y"] < 0 or point["y"] >= self.height:
                point["vy"] *= -1
                point["y"] = max(0, min(self.height - 1, point["y"]))

            if is_beat:
                point["vx"] += (random.random() - 0.5) * bass * 4
                point["vy"] += (random.random() - 0.5) * bass * 4

        # Render at lower resolution for performance
        scale = 4
        small_w = self.width // scale
        small_h = self.height // scale

        y_coords, x_coords = np.ogrid[:small_h, :small_w]
        x_coords = x_coords * scale
        y_coords = y_coords * scale

        min_dist = np.full((small_h, small_w), np.inf)
        nearest = np.zeros((small_h, small_w), dtype=np.int32)

        for i, point in enumerate(self.voronoi_points):
            dist = np.sqrt((x_coords - point["x"]) ** 2 + (y_coords - point["y"]) ** 2)
            mask = dist < min_dist
            min_dist[mask] = dist[mask]
            nearest[mask] = i

        rgb = np.zeros((small_h, small_w, 3), dtype=np.uint8)
        for i, point in enumerate(self.voronoi_points):
            mask = nearest == i
            for c in range(3):
                rgb[mask, c] = point["color"][c]

        edge_x = np.abs(np.diff(nearest.astype(np.float32), axis=1, prepend=nearest[:, :1]))
        edge_y = np.abs(np.diff(nearest.astype(np.float32), axis=0, prepend=nearest[:1, :]))
        edges = np.clip((edge_x + edge_y) * 50, 0, 100).astype(np.uint8)

        for c in range(3):
            rgb[:, :, c] = np.clip(rgb[:, :, c].astype(np.int16) - edges, 0, 255).astype(
                np.uint8
            )

        voronoi_small = Image.fromarray(rgb, mode="RGB")
        voronoi_full = voronoi_small.resize(
            (self.width, self.height), Image.Resampling.NEAREST
        )

        voronoi_rgba = voronoi_full.convert("RGBA")
        r_ch, g_ch, b_ch, _ = voronoi_rgba.split()
        alpha_value = int(180 * self.intensity)
        alpha = Image.new("L", (self.width, self.height), alpha_value)
        voronoi_rgba = Image.merge("RGBA", (r_ch, g_ch, b_ch, alpha))

        img.paste(voronoi_rgba, (0, 0), voronoi_rgba)

    # ========================================================================
    # METABALLS EFFECT
    # ========================================================================

    def _init_metaballs(self) -> None:
        """Initialize metaballs with positions and velocities."""
        self.metaball_count = 6
        self.metaballs: list[dict[str, float]] = []
        for _ in range(self.metaball_count):
            self.metaballs.append({
                "x": random.random() * self.width,
                "y": random.random() * self.height,
                "vx": (random.random() - 0.5) * 4,
                "vy": (random.random() - 0.5) * 4,
                "radius": random.random() * 80 + 60,
            })
        # Pre-compute coordinate grid at lower resolution
        self.metaball_scale = 4
        self.metaball_w = self.width // self.metaball_scale
        self.metaball_h = self.height // self.metaball_scale
        y_coords = np.arange(self.metaball_h) * self.metaball_scale
        x_coords = np.arange(self.metaball_w) * self.metaball_scale
        self.metaball_x, self.metaball_y = np.meshgrid(x_coords, y_coords)

    def _render_metaballs(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render metaballs (blob/liquid effect).

        Balls that merge smoothly when close together using field function.
        Uses GPU acceleration when available.

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position in seconds.
            ctx: Audio context dict.
        """
        # Try GPU rendering first
        gpu_img = self._render_gpu_effect("metaballs", time_pos, ctx)
        if gpu_img:
            img.paste(gpu_img, (0, 0), gpu_img)
            return

        # CPU fallback
        energy = ctx["energy"]
        bass = ctx["bass"]
        is_beat = ctx["is_beat"]

        # Update metaball positions
        speed_mult = 1 + energy * 2
        for ball in self.metaballs:
            ball["x"] += ball["vx"] * speed_mult
            ball["y"] += ball["vy"] * speed_mult

            if ball["x"] < 0 or ball["x"] >= self.width:
                ball["vx"] *= -1
                ball["x"] = max(0, min(self.width - 1, ball["x"]))
            if ball["y"] < 0 or ball["y"] >= self.height:
                ball["vy"] *= -1
                ball["y"] = max(0, min(self.height - 1, ball["y"]))

            if is_beat:
                ball["vx"] += (random.random() - 0.5) * bass * 6
                ball["vy"] += (random.random() - 0.5) * bass * 6

        # Compute metaball field
        field = np.zeros((self.metaball_h, self.metaball_w), dtype=np.float32)

        for ball in self.metaballs:
            radius = ball["radius"] * (1 + bass * 0.5)
            dx = self.metaball_x - ball["x"]
            dy = self.metaball_y - ball["y"]
            dist_sq = dx * dx + dy * dy + 1
            field += (radius * radius) / dist_sq

        threshold = 1.0
        inside = field > threshold
        glow = np.clip((field - threshold * 0.5) / threshold, 0, 1)

        hue_shift = time_pos * 0.5
        r = (np.sin(glow * math.pi + hue_shift) * 127 + 128).astype(np.uint8)
        g = (np.sin(glow * math.pi + hue_shift + 2) * 127 + 128).astype(np.uint8)
        b = (np.sin(glow * math.pi + hue_shift + 4) * 127 + 128).astype(np.uint8)

        r[inside] = np.clip(r[inside].astype(np.int16) + 80, 0, 255).astype(np.uint8)
        g[inside] = np.clip(g[inside].astype(np.int16) + 80, 0, 255).astype(np.uint8)
        b[inside] = np.clip(b[inside].astype(np.int16) + 80, 0, 255).astype(np.uint8)

        rgb = np.stack([r, g, b], axis=-1)
        alpha_arr = (glow * 200 * self.intensity).astype(np.uint8)
        rgba = np.dstack([rgb, alpha_arr])

        metaball_small = Image.fromarray(rgba, mode="RGBA")
        metaball_full = metaball_small.resize(
            (self.width, self.height), Image.Resampling.BILINEAR
        )

        img.paste(metaball_full, (0, 0), metaball_full)

    # ========================================================================
    # SMOKE EFFECT
    # ========================================================================

    def _init_smoke(self) -> None:
        """Initialize smoke particle system."""
        self.smoke_particles: list[dict[str, float]] = []
        self.max_smoke_particles = 150
        # Smoke rises from bottom
        self.smoke_spawn_y = self.height

    def _spawn_smoke_particle(self, x: float | None = None, energy: float = 0.5) -> None:
        """Spawn a smoke particle.

        Args:
            x: X position (random if None).
            energy: Affects initial velocity.
        """
        if len(self.smoke_particles) >= self.max_smoke_particles:
            return

        self.smoke_particles.append({
            "x": x if x is not None else random.random() * self.width,
            "y": self.smoke_spawn_y,
            "vx": (random.random() - 0.5) * 2,
            "vy": -random.random() * 3 - 1,  # Rises up
            "size": random.random() * 30 + 20,
            "life": 1.0,
            "decay": random.random() * 0.01 + 0.005,
            "alpha": random.random() * 0.3 + 0.2,
            "turbulence_offset": random.random() * 100,
        })

    def _render_smoke(
        self, img: Image.Image, frame_idx: int, time_pos: float, ctx: dict
    ) -> None:
        """Render smoke/mist effect with Perlin turbulence.

        Particles rise and dissipate with turbulent motion.
        Spawn rate and movement react to audio.

        Args:
            img: Image to draw on.
            frame_idx: Frame index.
            time_pos: Time position in seconds.
            ctx: Audio context dict.
        """
        draw = ImageDraw.Draw(img)
        energy = ctx["energy"]
        bass = ctx["bass"]
        is_beat = ctx["is_beat"]

        # Spawn new particles based on energy
        spawn_rate = int(3 + energy * 8)
        for _ in range(spawn_rate):
            # Spawn across bottom, more in center
            x = self.width / 2 + (random.random() - 0.5) * self.width * 0.6
            self._spawn_smoke_particle(x, energy)

        # Extra burst on beat
        if is_beat:
            for _ in range(5):
                x = self.width / 2 + (random.random() - 0.5) * self.width * 0.4
                self._spawn_smoke_particle(x, bass)

        # Update and render particles
        new_particles = []
        for p in self.smoke_particles:
            # Turbulence using Perlin noise for more natural motion
            noise_scale = 0.005
            turb_x = perlin2d(
                p["x"] * noise_scale + time_pos * 0.5,
                p["y"] * noise_scale + p["turbulence_offset"],
            ) * 1.5
            turb_y = perlin2d(
                p["x"] * noise_scale + p["turbulence_offset"],
                p["y"] * noise_scale + time_pos * 0.3,
            ) * 0.8

            # Update position
            p["x"] += p["vx"] + turb_x + (random.random() - 0.5) * energy
            p["y"] += p["vy"] + turb_y
            p["vy"] *= 0.99  # Slow down rising

            # Grow as it rises
            p["size"] += 0.3

            # Decay
            p["life"] -= p["decay"]

            # Remove dead particles
            if p["life"] <= 0 or p["y"] < -p["size"]:
                continue

            # Calculate alpha based on life
            alpha = int(p["alpha"] * p["life"] * 255 * self.intensity)
            if alpha < 5:
                continue

            # Smoke color (gray with slight variation)
            gray = int(180 + p["turbulence_offset"] % 40)
            color = (gray, gray, gray, alpha)

            # Draw as ellipse (wider than tall for smoke look)
            size = p["size"]
            x, y = p["x"], p["y"]
            draw.ellipse(
                [x - size, y - size * 0.6, x + size, y + size * 0.6],
                fill=color,
            )

            new_particles.append(p)

        self.smoke_particles = new_particles
