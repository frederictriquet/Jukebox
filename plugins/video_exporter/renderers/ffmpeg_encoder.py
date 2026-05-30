"""FFmpeg encoder wrapper for video export."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


class FFmpegEncoder:
    """Wrapper for FFmpeg subprocess to encode video frames."""

    def __init__(
        self,
        output_path: Path,
        width: int,
        height: int,
        fps: int,
        audio_path: Path,
        audio_start: float,
        audio_duration: float,
        fade_duration: float = 1.0,
        *,
        video_codec: str = "libx264",
        preset: str = "medium",
        crf: int = 23,
        pixel_format: str = "yuv420p",
        audio_codec: str = "aac",
        audio_bitrate: str = "192k",
        min_video_bitrate: str = "3500k",
        max_video_bitrate: str = "5000k",
        bufsize: str = "7000k",
    ) -> None:
        """Initialize FFmpeg encoder.

        Args:
            output_path: Path for the output video file.
            width: Video width in pixels.
            height: Video height in pixels.
            fps: Frames per second.
            audio_path: Path to the audio file.
            audio_start: Start time in the audio file (seconds).
            audio_duration: Duration of audio to include (seconds).
            fade_duration: Duration of fade in/out in seconds (0 to disable).
            video_codec: FFmpeg video codec (default: libx264).
            preset: FFmpeg encoding preset (default: medium).
            crf: FFmpeg constant rate factor (default: 23).
            pixel_format: FFmpeg pixel format (default: yuv420p).
            audio_codec: FFmpeg audio codec (default: aac).
            audio_bitrate: FFmpeg audio bitrate (default: 192k).
            min_video_bitrate: Débit vidéo minimum pour le constrained CRF (default: 3500k).
            max_video_bitrate: Débit vidéo maximum pour le constrained CRF (default: 5000k).
            bufsize: Taille du buffer VBV pour le constrained CRF (default: 7000k).

        Raises:
            RuntimeError: If FFmpeg is not found.
        """
        self.output_path = output_path
        self.width = width
        self.height = height
        self.fps = fps
        self.audio_path = audio_path
        self.audio_start = audio_start
        self.audio_duration = audio_duration
        self.fade_duration = fade_duration
        self.video_codec = video_codec
        self.preset = preset
        self.crf = crf
        self.pixel_format = pixel_format
        self.audio_codec = audio_codec
        self.audio_bitrate = audio_bitrate
        # Paramètres de constrained CRF pour garantir le débit minimum Instagram Reels
        self.min_video_bitrate = min_video_bitrate
        self.max_video_bitrate = max_video_bitrate
        self.bufsize = bufsize
        self.process: subprocess.Popen | None = None
        self._frame_count = 0

        # Vérification de la disponibilité de FFmpeg
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise RuntimeError("FFmpeg not found. Please install FFmpeg.")
        self.ffmpeg_path: str = ffmpeg_path

    def start(self) -> None:
        """Start the FFmpeg process."""
        # Ensure output directory exists
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # Construction de la commande FFmpeg
        cmd: list[str] = [
            self.ffmpeg_path,
            "-y",  # Overwrite output file
            # Video input from pipe
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{self.width}x{self.height}",
            "-r",
            str(self.fps),
            "-i",
            "-",  # stdin
            # Audio input
            "-ss",
            str(self.audio_start),
            "-t",
            str(self.audio_duration),
            "-i",
            str(self.audio_path),
        ]

        # Add fade filters if enabled
        if self.fade_duration > 0:
            fade_out_start = max(0, self.audio_duration - self.fade_duration)
            # Video fade: fade in at start, fade out at end
            video_filter = (
                f"fade=t=in:st=0:d={self.fade_duration},"
                f"fade=t=out:st={fade_out_start}:d={self.fade_duration}"
            )
            # Audio fade: fade in at start, fade out at end
            audio_filter = (
                f"afade=t=in:st=0:d={self.fade_duration},"
                f"afade=t=out:st={fade_out_start}:d={self.fade_duration}"
            )
            cmd.extend(["-vf", video_filter])
            cmd.extend(["-af", audio_filter])

        # Paramètres de sortie : constrained CRF pour garantir le débit minimum Instagram Reels
        cmd.extend([
            "-c:v",
            self.video_codec,
            "-preset",
            self.preset,
            "-crf",
            str(self.crf),
            # Constrained CRF : impose un débit plancher sans abandonner le CRF
            "-b:v",
            self.min_video_bitrate,
            "-maxrate",
            self.max_video_bitrate,
            "-bufsize",
            self.bufsize,
            "-pix_fmt",
            self.pixel_format,
            "-c:a",
            self.audio_codec,
            "-b:a",
            self.audio_bitrate,
            "-shortest",  # Fin quand le flux le plus court se termine
            "-movflags",
            "+faststart",  # MOOV atom en tête : requis pour streaming web / Instagram boost
            str(self.output_path),
        ])

        logging.info(f"[FFmpeg] Starting encoder: {' '.join(cmd)}")

        self.process = subprocess.Popen(  # noqa: S603
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def write_frame(self, frame: NDArray[np.uint8]) -> None:
        """Write a frame to the FFmpeg process.

        Args:
            frame: RGB frame as numpy array (height, width, 3).

        Raises:
            RuntimeError: If encoder is not started or write fails.
        """
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("Encoder not started")

        # Check if process is still running
        if self.process.poll() is not None:
            _, stderr = self.process.communicate()
            raise RuntimeError(f"FFmpeg process terminated: {stderr.decode()}")

        # Ensure frame is in correct format
        if frame.shape != (self.height, self.width, 3):
            raise ValueError(
                f"Frame shape {frame.shape} doesn't match "
                f"expected ({self.height}, {self.width}, 3)"
            )

        # Write frame data
        try:
            self.process.stdin.write(frame.tobytes())
            self._frame_count += 1
            # Flush every 30 frames to prevent buffer issues
            if self._frame_count % 30 == 0:
                self.process.stdin.flush()
        except BrokenPipeError as e:
            # Get FFmpeg error output
            _, stderr = self.process.communicate()
            raise RuntimeError(f"FFmpeg pipe broken: {stderr.decode()}") from e
        except ValueError as e:
            # Handle "flush of closed file" error
            if self.process.poll() is not None:
                _, stderr = self.process.communicate()
                raise RuntimeError(f"FFmpeg process terminated: {stderr.decode()}") from e
            raise

    def finish(self) -> Path:
        """Finish encoding and close the process.

        Returns:
            Path to the output video file.

        Raises:
            RuntimeError: If encoding failed.
        """
        if self.process is None:
            raise RuntimeError("Encoder not started")

        # Check if process already terminated
        poll_result = self.process.poll()
        if poll_result is not None:
            # Process already finished - get any remaining stderr
            stderr = self.process.stderr.read() if self.process.stderr else b""
            error_msg = stderr.decode() if stderr else "No error output"
            if poll_result != 0:
                raise RuntimeError(
                    f"FFmpeg terminated early (code {poll_result}): {error_msg}"
                )
            logging.info(
                f"[FFmpeg] Encoding complete: {self._frame_count} frames -> {self.output_path}"
            )
            return self.output_path

        # Close stdin to signal end of input
        if self.process.stdin:
            try:
                self.process.stdin.flush()
            except (BrokenPipeError, ValueError, OSError) as e:
                logging.debug("[FFmpegEncoder] stdin flush ignoré (pipe fermé) : %s", e)
            try:
                self.process.stdin.close()
            except (BrokenPipeError, ValueError, OSError) as e:
                logging.debug("[FFmpegEncoder] stdin close ignoré (pipe fermé) : %s", e)
            # Set to None so communicate() doesn't try to flush it
            self.process.stdin = None

        # Wait for process to finish (stdin is None so communicate won't flush it)
        try:
            _, stderr = self.process.communicate(timeout=120)
        except subprocess.TimeoutExpired as e:
            self.process.kill()
            self.process.communicate()
            raise RuntimeError("FFmpeg timed out during finalization") from e

        if self.process.returncode != 0:
            error_msg = stderr.decode() if stderr else "No error output"
            raise RuntimeError(
                f"FFmpeg failed (code {self.process.returncode}): {error_msg}"
            )

        logging.info(
            f"[FFmpeg] Encoding complete: {self._frame_count} frames -> {self.output_path}"
        )

        return self.output_path

    def cancel(self) -> None:
        """Cancel encoding and terminate FFmpeg process."""
        if self.process:
            # Fermer stdin avant terminate() : un FFmpeg bloqué en lecture sur stdin
            # ne réagit pas toujours à SIGTERM sur certains OS tant que le pipe est ouvert.
            if self.process.stdin:
                try:
                    self.process.stdin.close()
                except Exception as e:
                    logging.debug("[FFmpeg] cancel: stdin close ignoré (pipe fermé) : %s", e)
                self.process.stdin = None
            self.process.terminate()
            self.process.wait()
            logging.info("[FFmpeg] Encoding cancelled")

    @property
    def frame_count(self) -> int:
        """Get the number of frames written."""
        return self._frame_count
