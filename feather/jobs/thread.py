"""
Thread Pool Job Queue
=====================

Background job execution using a thread pool with concurrency control.

This backend provides true background execution without requiring external
infrastructure (like Redis). Jobs run in daemon threads and support
per-task concurrency limits via semaphores.

Ideal for resource-intensive tasks like:
- Audio/video transcription (Whisper)
- Image processing
- ML model inference

Configuration
-------------
::

    JOB_BACKEND=thread
    JOB_MAX_WORKERS=4              # Thread pool size (default: 4)
    JOB_ENABLE_MONITORING=true     # Enable psutil resource tracking

Usage
-----
::

    from feather.jobs import job

    @job(concurrency=2)  # Max 2 concurrent executions
    def transcribe_video(video_id):
        # Heavy processing that won't crash server
        pass

    # Enqueue - returns immediately
    result = transcribe_video.enqueue(video_id)

Note:
    Jobs are lost on server restart (in-memory only).
    For persistence, use RQQueue with Redis.
"""

import logging
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from feather.jobs.base import JobQueue, JobResult, JobStatus

logger = logging.getLogger(__name__)


class ThreadPoolQueue(JobQueue):
    """Thread pool job queue with concurrency control.

    Executes jobs in background threads with optional per-task
    concurrency limits using semaphores. Perfect for solo developers
    who need background processing without Redis infrastructure.

    Args:
        max_workers: Maximum number of worker threads (default: 4).
        enable_monitoring: Enable psutil resource tracking on failures.
        capture_exceptions: Store exceptions in result vs propagate.

    Example::

        queue = ThreadPoolQueue(max_workers=4)

        @job(concurrency=2)
        def heavy_task(data):
            return process(data)

        result = queue.enqueue(heavy_task, data)
        # Returns immediately, job runs in background
    """

    def __init__(
        self,
        max_workers: int = 4,
        enable_monitoring: bool = False,
        capture_exceptions: bool = True,
    ):
        # Warn about Flask reloader killing threads
        import os
        import warnings

        if os.environ.get("FLASK_DEBUG") == "1":
            warnings.warn(
                "JOB_BACKEND=thread with FLASK_DEBUG=1 may cause issues. "
                "The Flask reloader kills background threads on file changes. "
                "Consider using JOB_BACKEND=sync for debugging or disable debug mode.",
                RuntimeWarning,
                stacklevel=2,
            )

        self.max_workers = max_workers
        self.enable_monitoring = enable_monitoring
        self._capture_exceptions = capture_exceptions

        # Thread pool for execution
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="feather-job-",
        )

        # Per-task-type semaphores for concurrency control
        self._semaphores: Dict[str, threading.Semaphore] = {}
        self._semaphore_lock = threading.Lock()

        # In-memory job tracking
        self._jobs: Dict[str, JobResult] = {}
        self._jobs_lock = threading.Lock()

        # Track pending jobs for queue length
        self._pending_count = 0
        self._pending_lock = threading.Lock()

        # Store task metadata (concurrency, retry config)
        self._task_metadata: Dict[str, dict] = {}

        # Flask app reference for context
        self._app = None

    def set_app(self, app) -> None:
        """Set Flask app for context management.

        Args:
            app: Flask application instance.
        """
        self._app = app

    def _get_semaphore(self, task_name: str, concurrency: Optional[int]) -> Optional[threading.Semaphore]:
        """Get or create a semaphore for a task type.

        Args:
            task_name: Unique task identifier (function name).
            concurrency: Max concurrent executions, None for unlimited.

        Returns:
            Semaphore or None if no concurrency limit.
        """
        if concurrency is None:
            return None

        with self._semaphore_lock:
            if task_name not in self._semaphores:
                self._semaphores[task_name] = threading.Semaphore(concurrency)
                logger.debug(f"Created semaphore for {task_name} with concurrency={concurrency}")
            return self._semaphores[task_name]

    def register_task(
        self,
        func: Callable,
        concurrency: Optional[int] = None,
        retry: int = 0,
        timeout: Optional[int] = None,
    ) -> None:
        """Register task metadata for a function.

        Called by the @job decorator to store concurrency, retry, and timeout settings.

        Args:
            func: The job function.
            concurrency: Max concurrent executions.
            retry: Number of retries on failure.
            timeout: Max execution time in seconds.
        """
        task_name = self._get_task_name(func)
        self._task_metadata[task_name] = {
            "concurrency": concurrency,
            "retry": retry,
            "timeout": timeout,
        }

        # Pre-create semaphore if concurrency is set
        if concurrency is not None:
            self._get_semaphore(task_name, concurrency)

    def _get_task_name(self, func: Callable) -> str:
        """Get unique identifier for a task function."""
        return f"{func.__module__}.{func.__qualname__}"

    def _get_task_metadata(self, func: Callable) -> dict:
        """Get registered metadata for a task function."""
        task_name = self._get_task_name(func)
        return self._task_metadata.get(task_name, {"concurrency": None, "retry": 0, "timeout": None})

    def enqueue(
        self,
        func: Callable,
        *args,
        queue_name: str = "default",
        delay: Optional[int] = None,
        concurrency: Optional[int] = None,
        retry: Optional[int] = None,
        timeout: Optional[int] = None,
        **kwargs,
    ) -> JobResult:
        """Add a job to the thread pool.

        Args:
            func: Function to execute.
            *args: Positional arguments for the function.
            queue_name: Ignored (no queue separation in thread pool).
            delay: Delay execution by N seconds (optional).
            concurrency: Override concurrency limit for this call.
            retry: Override retry count for this call.
            timeout: Override timeout in seconds for this call.
            **kwargs: Keyword arguments for the function.

        Returns:
            JobResult with job_id and QUEUED status.
        """
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Get task metadata (from decorator or override)
        metadata = self._get_task_metadata(func)
        task_concurrency = concurrency if concurrency is not None else metadata["concurrency"]
        task_retry = retry if retry is not None else metadata["retry"]
        task_timeout = timeout if timeout is not None else metadata["timeout"]

        # Create initial result
        result = JobResult(
            job_id=job_id,
            status=JobStatus.SCHEDULED if delay else JobStatus.QUEUED,
            enqueued_at=now,
        )

        with self._jobs_lock:
            self._jobs[job_id] = result

        with self._pending_lock:
            self._pending_count += 1

        # Submit to thread pool
        task_name = self._get_task_name(func)
        semaphore = self._get_semaphore(task_name, task_concurrency)

        self._executor.submit(
            self._execute_job,
            job_id=job_id,
            func=func,
            args=args,
            kwargs=kwargs,
            semaphore=semaphore,
            delay=delay,
            max_retries=task_retry,
            timeout=task_timeout,
            task_name=task_name,
        )

        logger.debug(f"Enqueued job {job_id} for {task_name}")
        return result

    def _execute_job(
        self,
        job_id: str,
        func: Callable,
        args: tuple,
        kwargs: dict,
        semaphore: Optional[threading.Semaphore],
        delay: Optional[int],
        max_retries: int,
        timeout: Optional[int],
        task_name: str,
    ) -> None:
        """Execute a job in a worker thread.

        Handles:
        - Delay before execution
        - Semaphore acquisition for concurrency control
        - Flask app context
        - Retry logic with exponential backoff
        - Timeout enforcement
        - Resource monitoring on failure
        """
        try:
            # Handle delay
            if delay and delay > 0:
                time.sleep(delay)

            # Update status to started
            with self._jobs_lock:
                if job_id in self._jobs:
                    self._jobs[job_id].status = JobStatus.STARTED
                    self._jobs[job_id].started_at = datetime.now(timezone.utc)

            # Acquire semaphore if concurrency limited
            if semaphore is not None:
                logger.debug(f"Job {job_id} waiting for semaphore ({task_name})")
                semaphore.acquire()
                logger.debug(f"Job {job_id} acquired semaphore ({task_name})")

            try:
                # Execute with retry logic
                result = self._execute_with_retry(
                    job_id=job_id,
                    func=func,
                    args=args,
                    kwargs=kwargs,
                    max_retries=max_retries,
                    timeout=timeout,
                    task_name=task_name,
                )

                # Update job result
                with self._jobs_lock:
                    if job_id in self._jobs:
                        self._jobs[job_id].status = JobStatus.FINISHED
                        self._jobs[job_id].result = result
                        self._jobs[job_id].ended_at = datetime.now(timezone.utc)

                logger.debug(f"Job {job_id} completed successfully")

            finally:
                # Always release semaphore
                if semaphore is not None:
                    semaphore.release()
                    logger.debug(f"Job {job_id} released semaphore ({task_name})")

        except TimeoutError as e:
            # Handle timeout specifically
            error_msg = f"Job timed out after {timeout} seconds"

            with self._jobs_lock:
                if job_id in self._jobs:
                    self._jobs[job_id].status = JobStatus.TIMEOUT
                    self._jobs[job_id].error = error_msg
                    self._jobs[job_id].ended_at = datetime.now(timezone.utc)

            logger.error(f"Job {job_id} timed out after {timeout}s")

        except Exception as e:
            # Capture failure
            error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"

            # Add resource metrics if monitoring enabled
            if self.enable_monitoring:
                metrics = self._capture_resource_metrics()
                if metrics:
                    error_msg += f"\n\nResource metrics at failure:\n{metrics}"

            with self._jobs_lock:
                if job_id in self._jobs:
                    self._jobs[job_id].status = JobStatus.FAILED
                    self._jobs[job_id].error = error_msg
                    self._jobs[job_id].ended_at = datetime.now(timezone.utc)

            logger.error(f"Job {job_id} failed: {e}")

        finally:
            with self._pending_lock:
                self._pending_count = max(0, self._pending_count - 1)

    def _execute_with_retry(
        self,
        job_id: str,
        func: Callable,
        args: tuple,
        kwargs: dict,
        max_retries: int,
        timeout: Optional[int],
        task_name: str,
    ) -> Any:
        """Execute function with retry logic and optional timeout.

        Args:
            job_id: Job identifier.
            func: Function to execute.
            args: Positional arguments.
            kwargs: Keyword arguments.
            max_retries: Max retry attempts.
            timeout: Max execution time in seconds (None for no limit).
            task_name: Task name for logging.

        Returns:
            Function result.

        Raises:
            TimeoutError if execution exceeds timeout.
            Exception if all retries exhausted.
        """
        attempt = 0
        last_error = None

        while attempt <= max_retries:
            try:
                # Execute with optional timeout
                if timeout is not None:
                    result = self._execute_with_timeout(func, args, kwargs, timeout)
                else:
                    # Execute with Flask app context if available
                    if self._app is not None:
                        with self._app.app_context():
                            result = func(*args, **kwargs)
                    else:
                        result = func(*args, **kwargs)
                return result

            except TimeoutError:
                # Don't retry timeouts - bubble up immediately
                raise

            except Exception as e:
                last_error = e
                attempt += 1

                if attempt <= max_retries:
                    # Exponential backoff: 2, 4, 8, 16... seconds, max 30
                    backoff = min(2**attempt, 30)
                    logger.warning(
                        f"Job {job_id} failed (attempt {attempt}/{max_retries + 1}), "
                        f"retrying in {backoff}s: {e}"
                    )
                    time.sleep(backoff)

        # All retries exhausted
        raise last_error  # type: ignore

    def _execute_with_timeout(
        self,
        func: Callable,
        args: tuple,
        kwargs: dict,
        timeout: int,
    ) -> Any:
        """Execute a function with a timeout using a separate thread.

        This is a cross-platform timeout implementation that works on
        Windows, macOS, and Linux.

        Args:
            func: Function to execute.
            args: Positional arguments.
            kwargs: Keyword arguments.
            timeout: Max execution time in seconds.

        Returns:
            Function result.

        Raises:
            TimeoutError if execution exceeds timeout.
            Exception if function raises an exception.
        """
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

        # Create a wrapper that handles Flask app context
        def wrapper():
            if self._app is not None:
                with self._app.app_context():
                    return func(*args, **kwargs)
            else:
                return func(*args, **kwargs)

        # Use a single-thread executor for timeout control
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="feather-timeout-") as executor:
            future = executor.submit(wrapper)
            try:
                return future.result(timeout=timeout)
            except FuturesTimeoutError:
                # Cancel the future (won't stop running thread, but marks it)
                future.cancel()
                raise TimeoutError(f"Job timed out after {timeout} seconds")

    def _capture_resource_metrics(self) -> str:
        """Capture current resource metrics for debugging.

        Returns:
            Formatted string with memory/CPU info, or empty string if unavailable.
        """
        try:
            from feather.jobs.monitoring import capture_resource_metrics

            metrics = capture_resource_metrics()
            if metrics:
                lines = [f"  {k}: {v}" for k, v in metrics.items()]
                return "\n".join(lines)
        except ImportError:
            pass
        return ""

    def get_job(self, job_id: str) -> Optional[JobResult]:
        """Get the status of a job.

        Args:
            job_id: Job identifier.

        Returns:
            JobResult or None if not found.
        """
        with self._jobs_lock:
            return self._jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued job.

        Note: Only cancels jobs that haven't started yet.
        Jobs already running cannot be canceled.

        Args:
            job_id: Job identifier.

        Returns:
            True if job was canceled, False otherwise.
        """
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job and job.status == JobStatus.QUEUED:
                job.status = JobStatus.CANCELED
                job.ended_at = datetime.now(timezone.utc)
                return True
        return False

    def get_queue_length(self, queue_name: str = "default") -> int:
        """Get the number of pending jobs.

        Args:
            queue_name: Ignored.

        Returns:
            Number of pending jobs.
        """
        with self._pending_lock:
            return self._pending_count

    def get_failed_jobs(self, queue_name: str = "default") -> list[JobResult]:
        """Get all failed jobs.

        Args:
            queue_name: Ignored.

        Returns:
            List of failed JobResults.
        """
        with self._jobs_lock:
            return [job for job in self._jobs.values() if job.status == JobStatus.FAILED]

    def clear_queue(self, queue_name: str = "default") -> int:
        """Clear job history.

        Note: Does not cancel running jobs.

        Args:
            queue_name: Ignored.

        Returns:
            Number of jobs cleared.
        """
        with self._jobs_lock:
            count = len(self._jobs)
            self._jobs.clear()
            return count

    def get_semaphore_status(self) -> Dict[str, dict]:
        """Get status of all semaphores for debugging.

        Returns:
            Dict mapping task name to semaphore info.
        """
        result = {}
        with self._semaphore_lock:
            for name, sem in self._semaphores.items():
                # Semaphore doesn't expose count directly, but we can try to acquire
                # This is a non-blocking check
                acquired = sem.acquire(blocking=False)
                if acquired:
                    sem.release()
                    result[name] = {"available": True}
                else:
                    result[name] = {"available": False, "note": "At capacity"}
        return result

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the thread pool.

        Args:
            wait: Wait for running jobs to complete.
        """
        self._executor.shutdown(wait=wait)
        logger.info(f"ThreadPoolQueue shutdown (wait={wait})")
