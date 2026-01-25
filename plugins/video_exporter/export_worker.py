"""Worker thread for video export processing."""

from __future__ import annotations

import logging
import os
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PySide6.QtCore import QThread, Signal

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from jukebox.core.protocols import PluginContextProtocol


class VideoExportWorker(QThread):
    """Worker thread for rendering and encoding video frames."""

    # Signals
    progress = Signal(int)  # Progress percentage (0-100)
    status = Signal(str)  # Status message
    finished = Signal(str)  # Output path
    error = Signal(str)  # Error message

    def __init__(
        self,
        config: dict[str, Any],
        context: PluginContextProtocol,
    ) -> None:
        """Initialize export worker.

        Args:
            config: Export configuration dictionary.
            context: Plugin context.
        """
        super().__init__()
        self.config = config
        self.context = context
        self._cancelled = False
        # Number of parallel render threads (use CPU count, max 8)
        self._num_workers = min(os.cpu_count() or 4, 8)

    def run(self) -> None:
        """Run the export process."""
        try:
            self._export_parallel()
        except Exception as e:
            logging.exception("[Video Export Worker] Export failed")
            self.error.emit(str(e))

    def cancel(self) -> None:
        """Cancel the export process."""
        self._cancelled = True

    def _export_parallel(self) -> None:
        """Perform the export with parallel frame rendering."""
        # Import dependencies
        try:
            import librosa
        except ImportError as e:
            self.error.emit(f"Missing dependency: {e}. Install with: pip install librosa")
            return

        from plugins.video_exporter.renderers.ffmpeg_encoder import FFmpegEncoder
        from plugins.video_exporter.renderers.frame_renderer import FrameRenderer

        # Extract config
        filepath = self.config["filepath"]
        loop_start = self.config["loop_start"]
        loop_end = self.config["loop_end"]
        width = self.config["width"]
        height = self.config["height"]
        fps = self.config["fps"]
        output_path = self.config["output_path"]
        layers_config = self.config["layers"]
        track_metadata = self.config["track_metadata"]

        duration = loop_end - loop_start
        total_frames = int(duration * fps)

        self.status.emit("Loading audio...")
        logging.info(f"[Video Export Worker] Loading audio from {filepath}")

        # Load audio segment
        try:
            audio, sr = librosa.load(
                str(filepath),
                sr=22050,
                offset=loop_start,
                duration=duration,
                mono=True,
            )
        except Exception as e:
            self.error.emit(f"Failed to load audio: {e}")
            return

        self.status.emit("Initializing layers...")

        # Initialize frame renderer with enabled layers
        try:
            # Build waveform config from main config
            waveform_config = {
                "height_ratio": self.config.get("waveform_height_ratio", 0.3),
                "bass_color": self.config.get("waveform_bass_color"),
                "mid_color": self.config.get("waveform_mid_color"),
                "treble_color": self.config.get("waveform_treble_color"),
                "cursor_color": self.config.get("waveform_cursor_color"),
            }
            renderer = FrameRenderer(
                width=width,
                height=height,
                fps=fps,
                audio=audio,
                sr=sr,
                duration=duration,
                layers_config=layers_config,
                track_metadata=track_metadata,
                video_clips_folder=self.config.get("video_clips_folder", ""),
                vjing_mappings=self.config.get("vjing_mappings", {}),
                vjing_preset=self.config.get("vjing_preset", ""),
                vjing_presets=self.config.get("vjing_presets", {}),
                waveform_config=waveform_config,
                effect_intensities=self.config.get("effect_intensities", {}),
                color_palette=self.config.get("color_palette", "neon"),
            )
        except Exception as e:
            self.error.emit(f"Failed to initialize renderer: {e}")
            return

        # Pre-render GPU effects before parallel workers start
        # (OpenGL contexts are not thread-safe, so we cache GPU frames first)
        if self._num_workers > 1:
            self.status.emit("Pre-rendering GPU effects...")
            gpu_frames = renderer.prerender_gpu()
            if gpu_frames > 0:
                logging.info(f"[Video Export Worker] Pre-rendered {gpu_frames} GPU frames")

        self.status.emit("Starting FFmpeg encoder...")

        # Initialize FFmpeg encoder
        try:
            encoder = FFmpegEncoder(
                output_path=Path(output_path),
                width=width,
                height=height,
                fps=fps,
                audio_path=Path(filepath),
                audio_start=loop_start,
                audio_duration=duration,
            )
            encoder.start()
        except Exception as e:
            self.error.emit(f"Failed to start encoder: {e}")
            return

        self.status.emit(f"Rendering frames ({self._num_workers} threads)...")
        logging.info(
            f"[Video Export Worker] Starting parallel render with {self._num_workers} workers"
        )

        # Parallel rendering with ordered output
        try:
            self._render_parallel(renderer, encoder, total_frames, fps)
        except Exception as e:
            encoder.cancel()
            self.error.emit(f"Rendering failed: {e}")
            return

        if self._cancelled:
            return

        # Finish encoding
        self.status.emit(f"Finalizing video... ({encoder.frame_count} frames written)")
        logging.info(
            f"[Video Export Worker] Finishing, {encoder.frame_count}/{total_frames} frames"
        )
        try:
            output = encoder.finish()
            self.finished.emit(str(output))
        except Exception as e:
            logging.exception("[Video Export Worker] Finish failed")
            self.error.emit(f"Encoding failed: {e}")

    def _render_parallel(
        self,
        renderer: Any,
        encoder: Any,
        total_frames: int,
        fps: int,
    ) -> None:
        """Render frames in parallel and write to encoder in order.

        Args:
            renderer: FrameRenderer instance.
            encoder: FFmpegEncoder instance.
            total_frames: Total number of frames to render.
            fps: Frames per second.
        """
        # Buffer to store rendered frames waiting to be written
        frame_buffer: dict[int, NDArray[np.uint8]] = {}
        next_frame_to_write = 0

        # Maximum frames to buffer (prevent memory issues)
        max_buffer_size = self._num_workers * 4

        def render_frame(frame_idx: int) -> tuple[int, NDArray[np.uint8]]:
            """Render a single frame (called in thread pool)."""
            time_pos = frame_idx / fps
            frame = renderer.render_frame(frame_idx, time_pos)
            return frame_idx, frame

        with ThreadPoolExecutor(max_workers=self._num_workers) as executor:
            pending_futures: set = set()
            future_to_idx: dict = {}
            frames_submitted = 0

            # Submit first batch
            batch_size = min(max_buffer_size, total_frames)
            for frame_idx in range(batch_size):
                future = executor.submit(render_frame, frame_idx)
                pending_futures.add(future)
                future_to_idx[future] = frame_idx
                frames_submitted += 1

            # Process completed frames and submit new ones
            while pending_futures:
                if self._cancelled:
                    for future in pending_futures:
                        future.cancel()
                    encoder.cancel()
                    self.status.emit("Export cancelled")
                    return

                # Wait for at least one future to complete
                done, pending_futures = wait(
                    pending_futures, timeout=0.5, return_when=FIRST_COMPLETED
                )

                # Process completed futures
                for future in done:
                    frame_idx = future_to_idx.pop(future)
                    try:
                        idx, frame = future.result()
                        frame_buffer[idx] = frame
                    except Exception as e:
                        logging.error(f"[Video Export Worker] Frame {frame_idx} failed: {e}")
                        raise

                # Write consecutive frames from buffer
                while next_frame_to_write in frame_buffer:
                    frame = frame_buffer.pop(next_frame_to_write)
                    encoder.write_frame(frame)
                    next_frame_to_write += 1

                # Update progress
                progress_pct = int(next_frame_to_write / total_frames * 100)
                self.progress.emit(progress_pct)

                if next_frame_to_write % fps == 0 or not pending_futures:
                    self.status.emit(
                        f"Rendering: {next_frame_to_write}/{total_frames} frames "
                        f"({self._num_workers} threads)"
                    )

                # Submit more frames if buffer has room
                while (
                    frames_submitted < total_frames
                    and len(frame_buffer) + len(pending_futures) < max_buffer_size
                ):
                    future = executor.submit(render_frame, frames_submitted)
                    pending_futures.add(future)
                    future_to_idx[future] = frames_submitted
                    frames_submitted += 1

        # Write any remaining buffered frames
        while next_frame_to_write in frame_buffer:
            frame = frame_buffer.pop(next_frame_to_write)
            encoder.write_frame(frame)
            next_frame_to_write += 1
