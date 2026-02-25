"""Utility module for batch processing operations."""

import logging
import os
from collections.abc import Callable
from typing import Any, TypeVar

from PySide6.QtCore import QThread

from jukebox.core.batch_processor import BatchProcessor
from jukebox.core.constants import StatusColors
from jukebox.core.event_bus import Events

T = TypeVar("T")


class BatchProcessingHelper:
    """Helper class to manage batch processing with common boilerplate.

    This class centralizes the logic for:
    - Stopping existing batch if running
    - Filtering items that need processing
    - Logging status
    - Creating and starting BatchProcessor
    - Connecting signals

    Example:
        helper = BatchProcessingHelper(
            name="Waveform Generation",
            batch_processor_holder=WaveformVisualizerPlugin,
            context=self.context,
        )
        processor = helper.start(
            items=tracks_to_process,
            needs_processing_fn=lambda track_id, filepath: not has_waveform(track_id),
            worker_factory=lambda item: WaveformWorker(*item),
            on_complete=self._on_complete,
            on_error=self._on_error,
        )
    """

    def __init__(
        self,
        name: str,
        batch_processor_holder: Any,
        context: Any,
        *,
        batch_processor_attr: str = "_batch_processor",
    ) -> None:
        """Initialize helper.

        Args:
            name: Name for the batch process (used in logging and status)
            batch_processor_holder: Class or object that holds the _batch_processor attribute
            context: Plugin context with database, event_bus, etc.
            batch_processor_attr: Name of the attribute holding the BatchProcessor (default: "_batch_processor")
        """
        self.name = name
        self.batch_processor_holder = batch_processor_holder
        self.context = context
        self.batch_processor_attr = batch_processor_attr

    def _get_processor(self) -> BatchProcessor | None:
        """Get current batch processor."""
        return getattr(self.batch_processor_holder, self.batch_processor_attr, None)

    def _set_processor(self, processor: BatchProcessor | None) -> None:
        """Set batch processor."""
        setattr(self.batch_processor_holder, self.batch_processor_attr, processor)

    def stop_if_running(self) -> None:
        """Stop current batch processor if running."""
        processor = self._get_processor()
        if processor and processor.is_running:
            logging.info(f"[{self.name}] Batch processor already running, stopping it first")
            processor.stop()

    def filter_items(
        self,
        items: list[tuple[int, str]],
        needs_processing_fn: Callable[[int, str], bool],
        *,
        log_status: bool = True,
    ) -> tuple[list[tuple[int, str]], int]:
        """Filter items that need processing.

        Args:
            items: List of (track_id, filepath) tuples
            needs_processing_fn: Function that returns True if item needs processing
            log_status: Whether to log status for each item

        Returns:
            Tuple of (items_to_process, already_processed_count)
        """
        items_to_process: list[tuple[int, str]] = []
        already_processed = 0

        for track_id, filepath in items:
            filename = os.path.basename(filepath)
            needs = needs_processing_fn(track_id, filepath)

            if needs:
                items_to_process.append((track_id, filepath))
                if log_status:
                    logging.debug(f"  Track {track_id}: {filename} - NEEDS PROCESSING")
            else:
                already_processed += 1
                if log_status:
                    logging.debug(f"  Track {track_id}: {filename} - already processed")

        return items_to_process, already_processed

    def start(
        self,
        items: list[tuple[int, str]],
        needs_processing_fn: Callable[[int, str], bool],
        worker_factory: Callable[[tuple[int, str]], QThread],
        on_complete: Callable[[tuple[int, str], Any], None],
        on_error: Callable[[tuple[int, str], str], None],
        *,
        no_work_message: str | None = None,
        success_status_color: str = StatusColors.SUCCESS,
        log_status: bool = True,
    ) -> BatchProcessor | None:
        """Start batch processing.

        Args:
            items: List of (track_id, filepath) tuples to potentially process
            needs_processing_fn: Function that returns True if item needs processing
            worker_factory: Function to create worker thread for an item
            on_complete: Callback for item completion (item, result)
            on_error: Callback for item error (item, error_message)
            no_work_message: Message to show when all items already processed
            success_status_color: Color for status message when all done
            log_status: Whether to log detailed status for each item

        Returns:
            BatchProcessor instance if started, None if no work to do
        """
        # Stop existing batch
        self.stop_if_running()

        if not items:
            logging.info(f"[{self.name}] No items to process")
            return None

        total_items = len(items)

        # Filter items that need processing
        items_to_process, already_processed = self.filter_items(
            items, needs_processing_fn, log_status=log_status
        )

        logging.info(
            f"[{self.name}] Status: {already_processed} already done, "
            f"{len(items_to_process)} to process (total: {total_items})"
        )

        if not items_to_process:
            message = no_work_message or f"All {self.name.lower()} complete"
            logging.info(f"[{self.name}] {message}")
            self.context.emit(Events.STATUS_MESSAGE, message=message, color=success_status_color)
            return None

        # Create batch processor
        processor = BatchProcessor(
            name=self.name,
            worker_factory=worker_factory,
            context=self.context,
        )

        # Store reference
        self._set_processor(processor)

        # Connect signals
        processor.item_complete.connect(on_complete)
        processor.item_error.connect(on_error)

        # Start processing
        processor.start(items_to_process)

        return processor


def start_batch_processing(
    name: str,
    batch_processor_holder: Any,
    context: Any,
    items: list[tuple[int, str]],
    needs_processing_fn: Callable[[int, str], bool],
    worker_factory: Callable[[tuple[int, str]], QThread],
    on_complete: Callable[[tuple[int, str], Any], None],
    on_error: Callable[[tuple[int, str], str], None],
    *,
    batch_processor_attr: str = "_batch_processor",
    no_work_message: str | None = None,
    success_status_color: str = StatusColors.SUCCESS,
    log_status: bool = True,
) -> BatchProcessor | None:
    """Convenience function to start batch processing.

    This is a simpler API for one-off batch operations. For more control,
    use BatchProcessingHelper directly.

    Args:
        name: Name for the batch process (used in logging)
        batch_processor_holder: Class or object that holds the _batch_processor attribute
        context: Plugin context
        items: List of (track_id, filepath) tuples
        needs_processing_fn: Function that returns True if item needs processing
        worker_factory: Function to create worker thread for an item
        on_complete: Callback for item completion
        on_error: Callback for item error
        batch_processor_attr: Name of the batch processor attribute
        no_work_message: Message when all items already processed
        success_status_color: Color for completion status message
        log_status: Whether to log detailed status for each item

    Returns:
        BatchProcessor instance if started, None if no work to do
    """
    helper = BatchProcessingHelper(
        name=name,
        batch_processor_holder=batch_processor_holder,
        context=context,
        batch_processor_attr=batch_processor_attr,
    )
    return helper.start(
        items=items,
        needs_processing_fn=needs_processing_fn,
        worker_factory=worker_factory,
        on_complete=on_complete,
        on_error=on_error,
        no_work_message=no_work_message,
        success_status_color=success_status_color,
        log_status=log_status,
    )
