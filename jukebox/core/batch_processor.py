"""Generic batch processor for background tasks with queue management."""

import logging
import time
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from jukebox.core.event_bus import Events

# Cleanup interval for orphan workers (in milliseconds)
ORPHAN_CLEANUP_INTERVAL_MS = 30_000  # 30 seconds


class BatchProcessor(QObject):
    """Generic batch processor that processes items one at a time with a queue.

    Architecture:
    - Maintains a queue of items to process
    - Processes one item at a time (sequential)
    - Delegates actual work to worker threads
    - Saves progress incrementally (via callbacks)
    - Can be interrupted without losing completed work

    Usage:
        processor = BatchProcessor(
            name="Waveform Generation",
            worker_factory=lambda item: WaveformWorker(item),
            context=plugin_context
        )
        processor.progress.connect(on_progress)
        processor.item_complete.connect(on_item_complete)
        processor.finished.connect(on_finished)
        processor.start(items_to_process)
    """

    # Class variables for orphan worker management
    _global_orphan_workers: list[QThread] = []
    _cleanup_timer: QTimer | None = None

    @classmethod
    def _start_cleanup_timer(cls) -> None:
        """Start the periodic cleanup timer if not already running."""
        if cls._cleanup_timer is None:
            cls._cleanup_timer = QTimer()
            cls._cleanup_timer.timeout.connect(cls._cleanup_orphan_workers)
        if not cls._cleanup_timer.isActive():
            cls._cleanup_timer.start(ORPHAN_CLEANUP_INTERVAL_MS)
            logging.debug("[BatchProcessor] Started orphan worker cleanup timer")

    @classmethod
    def _cleanup_orphan_workers(cls) -> None:
        """Remove finished workers from the orphan list.

        Stops the timer when no orphans remain to avoid unnecessary polling.
        """
        before_count = len(cls._global_orphan_workers)
        cls._global_orphan_workers = [
            w for w in cls._global_orphan_workers if w.isRunning()
        ]
        after_count = len(cls._global_orphan_workers)

        if before_count != after_count:
            logging.debug(
                f"[BatchProcessor] Cleaned up {before_count - after_count} "
                f"finished orphan workers ({after_count} remaining)"
            )

        # Stop timer if no orphans remain
        if after_count == 0 and cls._cleanup_timer is not None:
            cls._cleanup_timer.stop()
            logging.debug("[BatchProcessor] Stopped orphan worker cleanup timer (no orphans)")

    # Signals
    progress = Signal(int, int, object)  # current, total, current_item
    item_complete = Signal(object, object)  # item, result
    item_error = Signal(object, str)  # item, error_message
    finished = Signal(int)  # number of items processed successfully
    item_skipped = Signal(object)  # item skipped (already in queue)

    def __init__(
        self,
        name: str,
        worker_factory: Callable[[Any], QThread],
        context: Any,
        parent: QObject | None = None,
    ):
        """Initialize batch processor.

        Args:
            name: Human-readable name for logging (e.g., "Waveform Generation")
            worker_factory: Function that creates a worker thread for an item
            context: Plugin context (for event bus, status updates)
            parent: Parent QObject
        """
        super().__init__(parent)
        self.name = name
        self.worker_factory = worker_factory
        self.context = context

        # Queue management
        self.queue: list[Any] = []
        self.current_index = 0
        self.total_items = 0
        self.completed_count = 0

        # Worker management
        self.current_worker: QThread | None = None

        # State
        self.is_running = False

        # Timing
        self.batch_start_time: float = 0.0
        self.current_item_start_time: float = 0.0

    def start(self, items: list[Any]) -> None:
        """Start batch processing.

        Args:
            items: List of items to process
        """
        if self.is_running:
            logging.warning(f"[{self.name}] Already running, ignoring start request")
            return

        if not items:
            logging.info(f"[{self.name}] No items to process")
            return

        self.queue = items.copy()
        self.total_items = len(items)
        self.current_index = 0
        self.completed_count = 0
        self.is_running = True
        self.batch_start_time = time.time()

        logging.info(f"[{self.name}] Starting: {self.total_items} items to process")
        self.context.emit(
            Events.STATUS_MESSAGE,
            message=f"{self.name}: Starting ({self.total_items} items)",
            color="#00FF00",
        )

        # Start processing first item
        self._process_next()

    def add_priority_item(self, item: Any) -> bool:
        """Add an item at the front of the queue (priority processing).

        Args:
            item: Item to process with priority

        Returns:
            True if item was added, False if already in queue or currently processing
        """
        if not self.is_running:
            logging.warning(f"[{self.name}] Cannot add priority item: batch not running")
            return False

        # Check if already processing this exact item
        if self.current_index < len(self.queue) and self.queue[self.current_index] == item:
            logging.debug(f"[{self.name}] Item already being processed, skipping")
            self.item_skipped.emit(item)
            return False

        # Check if item already in remaining queue
        remaining_queue = self.queue[self.current_index + 1 :]
        if item in remaining_queue:
            # Remove from its current position
            idx = remaining_queue.index(item)
            actual_idx = self.current_index + 1 + idx
            self.queue.pop(actual_idx)
            logging.debug(f"[{self.name}] Item already in queue, moving to front")
        else:
            # Adjust total count since we're adding a new item
            self.total_items += 1
            logging.debug(f"[{self.name}] Adding new priority item")

        # Insert at front of remaining queue (right after current item)
        self.queue.insert(self.current_index + 1, item)

        logging.info(f"[{self.name}] Priority item added (will be processed next)")
        return True

    def stop(self) -> None:
        """Stop batch processing (graceful, completes current item)."""
        if not self.is_running:
            return

        logging.info(f"[{self.name}] Stop requested (will finish current item)")
        self.is_running = False

        # Cancel current worker
        if self.current_worker:
            self._cleanup_current_worker()

    def _process_next(self) -> None:
        """Process next item in queue."""
        if not self.is_running:
            return

        # Check if queue is empty
        if self.current_index >= len(self.queue):
            self._finish()
            return

        # Get next item
        item = self.queue[self.current_index]
        current = self.current_index + 1

        # Start timing this item
        self.current_item_start_time = time.time()

        # Log progress (INFO level: just the essentials)
        logging.info(f"[{self.name}] [{current}/{self.total_items}] Processing...")

        # DEBUG level: show the actual item
        logging.debug(f"[{self.name}] Item details: {item}")

        self.progress.emit(current, self.total_items, item)

        # Update status bar
        self.context.emit(
            Events.STATUS_MESSAGE,
            message=f"{self.name}: {current}/{self.total_items}",
            color="#00FF00",
        )

        # Create worker
        try:
            self.current_worker = self.worker_factory(item)

            # Connect signals (worker must emit 'complete' or 'error')
            if hasattr(self.current_worker, "complete"):
                self.current_worker.complete.connect(
                    lambda result: self._on_item_complete(item, result)
                )
            if hasattr(self.current_worker, "error"):
                self.current_worker.error.connect(lambda error: self._on_item_error(item, error))

            # Start worker
            self.current_worker.start()

        except Exception as e:
            logging.error(f"[{self.name}] Failed to create worker: {e}", exc_info=True)
            self._on_item_error(item, str(e))

    def _on_item_complete(self, item: Any, result: Any) -> None:
        """Handle item processing completion.

        Args:
            item: The item that was processed
            result: Result from worker
        """
        # Calculate duration
        duration = time.time() - self.current_item_start_time

        # Log with duration (INFO level)
        logging.info(
            f"[{self.name}] [{self.current_index + 1}/{self.total_items}] ✓ Complete ({duration:.1f}s)"
        )

        # DEBUG level: show the actual item
        logging.debug(f"[{self.name}] Completed item: {item}")

        # Emit completion signal (caller handles saving to database)
        self.item_complete.emit(item, result)

        self.completed_count += 1
        self.current_index += 1

        # Cleanup worker
        self._cleanup_current_worker()

        # Process next item
        self._process_next()

    def _on_item_error(self, item: Any, error: str) -> None:
        """Handle item processing error.

        Args:
            item: The item that failed
            error: Error message
        """
        # Calculate duration
        duration = time.time() - self.current_item_start_time

        # Use warning level for expected errors (skipped files), error level for unexpected
        if error.startswith("Skipping"):
            logging.warning(
                f"[{self.name}] [{self.current_index + 1}/{self.total_items}] ⊘ Skipped ({duration:.1f}s): {error}"
            )
        else:
            logging.error(
                f"[{self.name}] [{self.current_index + 1}/{self.total_items}] ✗ Error ({duration:.1f}s): {error}"
            )

        # DEBUG level: show the actual item
        logging.debug(f"[{self.name}] Failed item: {item}")

        # Emit error signal
        self.item_error.emit(item, error)

        self.current_index += 1

        # Cleanup worker
        self._cleanup_current_worker()

        # Continue with next item
        self._process_next()

    def _cleanup_current_worker(self) -> None:
        """Cleanup current worker thread."""
        if not self.current_worker:
            return

        # Disconnect custom signals only (not Qt internal signals)
        # Qt internal signals to skip: destroyed, objectNameChanged, started, finished
        qt_internal_signals = {
            b"destroyed",
            b"objectNameChanged",
            b"started",
            b"finished",
            b"deleteLater",
        }

        try:
            # Get all signals from the worker's metaobject
            meta = self.current_worker.metaObject()
            for i in range(meta.methodCount()):
                method = meta.method(i)
                if method.methodType() == method.MethodType.Signal:
                    signal_name = method.name().data()
                    # Skip Qt internal signals
                    if signal_name in qt_internal_signals:
                        continue
                    # Disconnect custom signals only
                    signal_name_str = signal_name.decode()
                    if hasattr(self.current_worker, signal_name_str):
                        signal_obj = getattr(self.current_worker, signal_name_str)
                        try:
                            signal_obj.disconnect()
                        except (RuntimeWarning, RuntimeError, TypeError) as e:
                            logging.debug(
                                f"[{self.name}] Could not disconnect {signal_name_str}: {e}"
                            )
        except Exception as e:
            logging.warning(f"[{self.name}] Error during signal cleanup: {e}", exc_info=True)
            # Fallback: try known custom signals
            try:
                if hasattr(self.current_worker, "complete"):
                    self.current_worker.complete.disconnect()
                if hasattr(self.current_worker, "error"):
                    self.current_worker.error.disconnect()
                if hasattr(self.current_worker, "progress_update"):
                    self.current_worker.progress_update.disconnect()
            except (RuntimeWarning, RuntimeError, TypeError) as e:
                logging.debug(f"[{self.name}] Could not disconnect fallback signals: {e}")

        # Move to orphan list (let it finish naturally)
        self.current_worker.setParent(None)
        BatchProcessor._global_orphan_workers.append(self.current_worker)

        # Start periodic cleanup timer (will clean up finished workers)
        BatchProcessor._start_cleanup_timer()

        self.current_worker = None

    def _finish(self) -> None:
        """Finish batch processing."""
        self.is_running = False

        # Calculate total duration
        total_duration = time.time() - self.batch_start_time
        minutes = int(total_duration // 60)
        seconds = total_duration % 60

        # Format duration
        duration_str = f"{minutes}m {seconds:.0f}s" if minutes > 0 else f"{seconds:.1f}s"

        failed_count = self.total_items - self.completed_count

        # Log summary
        if failed_count > 0:
            logging.info(
                f"[{self.name}] Complete: {self.completed_count} succeeded, {failed_count} failed ({duration_str})"
            )
        else:
            logging.info(
                f"[{self.name}] Complete: {self.completed_count}/{self.total_items} successful ({duration_str})"
            )

        # Update status bar
        status_msg = f"{self.name}: Complete ({self.completed_count}/{self.total_items})"
        self.context.emit(
            Events.STATUS_MESSAGE,
            message=status_msg,
            color="#00FF00" if failed_count == 0 else "#FFA500",
        )

        # Emit finished signal
        self.finished.emit(self.completed_count)

        # Clear queue
        self.queue = []
        self.current_index = 0
        self.total_items = 0
