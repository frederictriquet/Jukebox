"""File scanner for audio directories."""

import logging
from collections.abc import Callable
from pathlib import Path

from jukebox.core.database import Database
from jukebox.utils.metadata import MetadataExtractor


class FileScanner:
    """Scan directories for audio files."""

    def __init__(
        self,
        database: Database,
        supported_formats: list[str],
        progress_callback: Callable[[int, int], None] | None = None,
    ):
        """Initialize scanner.

        Args:
            database: Database instance
            supported_formats: List of supported file extensions
            progress_callback: Optional callback(current, total)
        """
        self.database = database
        self.supported_formats = [f".{fmt}" for fmt in supported_formats]
        self.progress_callback = progress_callback

    def scan_directory(self, directory: Path, recursive: bool = True) -> int:
        """Scan directory for audio files.

        Args:
            directory: Directory to scan
            recursive: Whether to scan recursively

        Returns:
            Number of files added

        Raises:
            ValueError: If directory doesn't exist
        """
        if not directory.exists():
            raise ValueError(f"Directory does not exist: {directory}")

        files = self._find_audio_files(directory, recursive)
        total = len(files)
        added = 0

        for idx, filepath in enumerate(files):
            try:
                # Check if already in database
                if self.database.conn is None:
                    continue

                existing = self.database.conn.execute(
                    "SELECT id FROM tracks WHERE filepath = ?", (str(filepath),)
                ).fetchone()

                if existing:
                    continue

                # Extract and add
                metadata = MetadataExtractor.extract(filepath)
                self.database.add_track(metadata)
                added += 1

                # Progress
                if self.progress_callback:
                    self.progress_callback(idx + 1, total)

            except ValueError as e:
                # Empty or invalid audio file - skip it
                logging.warning(f"Skipping invalid file {filepath}: {e}")
            except Exception as e:
                logging.error(f"Error processing {filepath}: {e}")

        return added

    def _find_audio_files(self, directory: Path, recursive: bool) -> list[Path]:
        """Find all audio files in directory.

        Args:
            directory: Directory to search
            recursive: Whether to search recursively

        Returns:
            List of audio file paths
        """
        files: list[Path] = []

        if recursive:
            for ext in self.supported_formats:
                files.extend(directory.rglob(f"*{ext}"))
        else:
            for ext in self.supported_formats:
                files.extend(directory.glob(f"*{ext}"))

        return sorted(files)
