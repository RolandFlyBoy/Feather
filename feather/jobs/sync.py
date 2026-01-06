"""
Synchronous Job Queue
=====================

Synchronous job execution for development and testing.

Jobs are executed immediately in the current thread, making it easy
to debug and test job logic without setting up Redis or workers.

Usage
-----
::

    from feather.jobs.sync import SyncQueue

    queue = SyncQueue()
    result = queue.enqueue(my_function, arg1, arg2)
    # Job is already executed, result is available
    print(result.result)

Note:
    For production with true background execution, use RQQueue.
"""

import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from feather.jobs.base import JobQueue, JobResult, JobStatus


class SyncQueue(JobQueue):
    """Synchronous job queue for development.

    Executes jobs immediately in the calling thread.
    Useful for development and testing where you want to see
    job results immediately and debug easily.

    Args:
        capture_exceptions: If True, capture exceptions and store in result.
            If False, let exceptions propagate (default: True).

    Example::

        queue = SyncQueue()

        @job
        def process_data(data):
            return {'processed': len(data)}

        result = queue.enqueue(process_data, [1, 2, 3])
        print(result.status)  # JobStatus.FINISHED
        print(result.result)  # {'processed': 3}
    """

    def __init__(self, capture_exceptions: bool = True):
        self._capture_exceptions = capture_exceptions
        self._jobs: dict[str, JobResult] = {}

    def enqueue(
        self,
        func: Callable,
        *args,
        queue_name: str = "default",
        delay: Optional[int] = None,
        **kwargs,
    ) -> JobResult:
        """Execute a job immediately (synchronously).

        Args:
            func: Function to execute.
            *args: Positional arguments for the function.
            queue_name: Ignored in sync mode.
            delay: Ignored in sync mode (job runs immediately).
            **kwargs: Keyword arguments for the function.

        Returns:
            JobResult with execution result or error.
        """
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        result = JobResult(
            job_id=job_id,
            status=JobStatus.STARTED,
            enqueued_at=now,
            started_at=now,
        )

        try:
            # Execute immediately
            return_value = func(*args, **kwargs)

            result.status = JobStatus.FINISHED
            result.result = return_value
            result.ended_at = datetime.now(timezone.utc)

        except Exception as e:
            result.status = JobStatus.FAILED
            result.error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            result.ended_at = datetime.now(timezone.utc)

            if not self._capture_exceptions:
                self._jobs[job_id] = result
                raise

        self._jobs[job_id] = result
        return result

    def get_job(self, job_id: str) -> Optional[JobResult]:
        """Get the status of a job.

        Args:
            job_id: Job identifier.

        Returns:
            JobResult or None if not found.
        """
        return self._jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job (no-op in sync mode since jobs execute immediately).

        Args:
            job_id: Job identifier.

        Returns:
            False (jobs can't be canceled in sync mode).
        """
        return False

    def get_queue_length(self, queue_name: str = "default") -> int:
        """Get queue length (always 0 in sync mode).

        Args:
            queue_name: Ignored.

        Returns:
            0 (jobs execute immediately).
        """
        return 0

    def get_failed_jobs(self, queue_name: str = "default") -> list[JobResult]:
        """Get all failed jobs.

        Args:
            queue_name: Ignored.

        Returns:
            List of failed JobResults.
        """
        return [
            job for job in self._jobs.values()
            if job.status == JobStatus.FAILED
        ]

    def clear_queue(self, queue_name: str = "default") -> int:
        """Clear job history.

        Args:
            queue_name: Ignored.

        Returns:
            Number of jobs cleared.
        """
        count = len(self._jobs)
        self._jobs.clear()
        return count
