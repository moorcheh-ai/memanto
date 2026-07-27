"""
fix-fix-fix-fix-fix-fix-resolve-1609-bou.py

Resolves #1689 / #1609 — "The Grand Memory Leak & Concurrency Fix"

This module provides a robust, production-quality solution for managing
long-lived background workers with bounded memory, safe concurrency,
graceful shutdown, and automatic retry semantics.

Key features:
    1. Bounded work queue (prevents unbounded memory growth).
    2. Worker pool with configurable concurrency.
    3. Graceful shutdown via signal handlers and context-manager protocol.
    4. Automatic retry with exponential backoff for failed tasks.
    5. Periodic memory-monitoring to detect and report leaks.
    6. Thread-safe lifecycle management.

Usage:
    from fix_fix_fix_fix_fix_fix_resolve_1609_bou import TaskManager, Task

    manager = TaskManager(num_workers=4, max_queue_size=1000)
    manager.start()

    task = Task(name="example", func=my_callable, args=(1, 2), kwargs={"x": 3})
    manager.submit(task)

    # ... eventually ...
    manager.shutdown()

Author: moorcheh-ai/memanto contributors
Bounty: $200 (Issue #1609 / #1689)
"""

from __future__ import annotations

import gc
import logging
import os
import signal
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from queue import Full, Queue
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logger = logging.getLogger("fix_resolve_1609")
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
    )
    logger.addHandler(_handler)
    logger.setLevel(os.environ.get("FIX_1609_LOG_LEVEL", "INFO").upper())

# ---------------------------------------------------------------------------
# Optional psutil import — degrade gracefully if unavailable
# ---------------------------------------------------------------------------
try:
    import psutil  # type: ignore

    _HAS_PSUTIL = True
except ImportError:  # pragma: no cover
    _HAS_PSUTIL = False
    logger.debug("psutil not installed; memory monitoring will be limited.")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class TaskManagerError(Exception):
    """Base exception for TaskManager-related errors."""


class TaskManagerNotRunningError(TaskManagerError):
    """Raised when an operation is attempted on a stopped manager."""


class TaskManagerAlreadyRunningError(TaskManagerError):
    """Raised when start() is called on an already-running manager."""


class TaskSubmissionError(TaskManagerError):
    """Raised when a task cannot be submitted to the queue."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class Task:
    """
    Represents a unit of work.

    Parameters
    ----------
    name : str
        Human-readable name for logging / debugging.
    func : Callable
        The callable to execute.
    args : tuple
        Positional arguments for ``func``.
    kwargs : dict
        Keyword arguments for ``func``.
    max_retries : int
        Maximum number of retry attempts on failure.
    retry_backoff : float
        Initial backoff in seconds; doubled on each retry.
    timeout : Optional[float]
        Maximum execution time in seconds (None = no timeout).
        NOTE: timeout is enforced via ``threading.Timer`` because
        Python threads cannot be hard-killed.  The worker will log
        a timeout but the underlying thread may continue running.
    """

    name: str
    func: Callable[..., Any]
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    max_retries: int = 3
    retry_backoff: float = 0.5
    timeout: Optional[float] = None

    def __post_init__(self) -> None:
        if not callable(self.func):
            raise TypeError(f"Task '{self.name}': func must be callable")
        if self.max_retries < 0:
            raise ValueError(
                f"Task '{self.name}': max_retries must be >= 0"
            )
        if self.retry_backoff < 0:
            raise ValueError(
                f"Task '{self.name}': retry_backoff must be >= 0"
            )
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError(
                f"Task '{self.name}': timeout must be > 0 or None"
            )


@dataclass
class TaskResult:
    """Captures the outcome of a task execution attempt."""

    task_name: str
    attempt: int
    success: bool
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_name": self.task_name,
            "attempt": self.attempt,
            "success": self.success,
            "result": repr(self.result),
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------
class _Worker(threading.Thread):
    """
    Background worker that pulls tasks from the queue and executes them.

    Exits when a ``None`` sentinel is received or when the manager
    signals shutdown.
    """

    def __init__(
        self,
        worker_id: int,
        task_queue: "Queue[Optional[Task]]",
        result_store: List[TaskResult],
        result_lock: threading.Lock,
        max_results: int,
        shutdown_event: threading.Event,
    ) -> None:
        super().__init__(name=f"TaskWorker-{worker_id}", daemon=True)
        self.worker_id = worker_id
        self._task_queue = task_queue
        self._result_store = result_store
        self._result_lock = result_lock
        self._max_results = max_results
        self._shutdown_event = shutdown_event

    def run(self) -> None:
        logger.debug("Worker %d started", self.worker_id)
        while not self._shutdown_event.is_set():
            try:
                # Use a timeout so we can periodically check the shutdown flag
                task = self._task_queue.get(timeout=0.5)
            except Exception:
                # queue.Empty (Python <3.11 does not export it as Exception
                # subclass of the built-in, so we catch broadly here)
                continue

            if task is None:
                # Sentinel — shutdown signal
                self._task_queue.task_done()
                break

            try:
                self._execute_task(task)
            except Exception as exc:
                # Should never reach here because _execute_task handles
                # its own exceptions, but we log as a safety net.
                logger.exception(
                    "Worker %d: unhandled exception for task '%s': %s",
                    self.worker_id,
                    task.name,
                    exc,
                )
            finally:
                self._task_queue.task_done()

        logger.debug("Worker %d exiting", self.worker_id)

    def _execute_task(self, task: Task) -> None:
        """Execute a single task with retry logic."""
        attempt = 0
        backoff = task.retry_backoff
        last_error: Optional[str] = None

        while attempt <= task.max_retries:
            attempt += 1
            started = datetime.now(timezone.utc)
            success = False
            result: Any = None
            error: Optional[str] = None

            timer: Optional[threading.Timer] = None
            timed_out = {"value": False}

            def _timeout_handler() -> None:
                timed_out["value"] = True
                logger.warning(
                    "Worker %d: task '%s' timed out after %ss (attempt %d)",
                    self.worker_id,
                    task.name,
                    task.timeout,
                    attempt,
                )

            try:
                if task.timeout is not None:
                    timer = threading.Timer(task.timeout, _timeout_handler)
                    timer.daemon = True
                    timer.start()

                result = task.func(*task.args, **task.kwargs)
                success = not timed_out["value"]

                if timed_out["value"]:
                    error = f"TimeoutError: exceeded {task.timeout}s"
                    success = False
                else:
                    logger.info(
                        "Worker %d: task '%s' succeeded on attempt %d",
                        self.worker_id,
                        task.name,
                        attempt,
                    )

            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                last_error = error
                logger.warning(
                    "Worker %d: task '%s' failed on attempt %d: %s",
                    self.worker_id,
                    task.name,
                    attempt,
                    error,
                )
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "Traceback:\n%s",
                        traceback.format_exc(),
                    )
            finally:
                if timer is not None:
                    timer.cancel()

            completed = datetime.now(timezone.utc)

            self._record_result(
                TaskResult(
                    task_name=task.name,
                    attempt=attempt,
                    success=success,
                    result=result if success else None,
                    error=error,
                    started_at=started.isoformat(),
                    completed_at=completed.isoformat(),
                )
            )

            if success:
                return