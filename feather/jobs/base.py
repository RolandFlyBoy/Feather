"""
Job Queue Base Class
====================

Abstract base class for job queue backends.

Feather supports multiple job queue backends:
- SyncQueue: Synchronous execution for development (default)
- RQQueue: Redis Queue for production background jobs

Configuration
-------------
Set in environment variables or config.py::

    JOB_BACKEND=sync  # or 'rq'
    REDIS_URL=redis://localhost:6379/0  # for RQ

Usage
-----
::

    from feather.jobs import get_queue, job

    # Define a job
    @job
    def send_email(to, subject, body):
        # Send email...
        pass

    # Enqueue the job
    send_email.enqueue('user@example.com', 'Hello', 'World')

    # Or use the queue directly
    queue = get_queue()
    queue.enqueue(send_email, 'user@example.com', 'Hello', 'World')
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional


class JobStatus(Enum):
    """Job execution status."""

    QUEUED = "queued"
    STARTED = "started"
    FINISHED = "finished"
    FAILED = "failed"
    DEFERRED = "deferred"
    SCHEDULED = "scheduled"
    CANCELED = "canceled"
    TIMEOUT = "timeout"


@dataclass
class JobResult:
    """Result of a job execution.

    Attributes:
        job_id: Unique job identifier.
        status: Current job status.
        result: Return value from the job (if finished).
        error: Error message (if failed).
        enqueued_at: When the job was enqueued.
        started_at: When the job started executing.
        ended_at: When the job finished or failed.
    """

    job_id: str
    status: JobStatus
    result: Any = None
    error: Optional[str] = None
    enqueued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    def is_finished(self) -> bool:
        """Check if job has completed (success or failure)."""
        return self.status in (JobStatus.FINISHED, JobStatus.FAILED, JobStatus.CANCELED, JobStatus.TIMEOUT)

    def is_successful(self) -> bool:
        """Check if job completed successfully."""
        return self.status == JobStatus.FINISHED


class JobQueue(ABC):
    """Abstract base class for job queue backends.

    All job queue backends must implement these methods to provide
    a consistent job queueing interface.

    Example::

        class MyQueue(JobQueue):
            def enqueue(self, func, *args, **kwargs):
                # Add job to queue
                pass

            def get_job(self, job_id):
                # Get job status
                pass

            def cancel_job(self, job_id):
                # Cancel a job
                pass
    """

    @abstractmethod
    def enqueue(
        self,
        func: Callable,
        *args,
        queue_name: str = "default",
        delay: Optional[int] = None,
        **kwargs,
    ) -> JobResult:
        """Add a job to the queue.

        Args:
            func: Function to execute.
            *args: Positional arguments for the function.
            queue_name: Name of the queue (default: 'default').
            delay: Delay execution by N seconds (optional).
            **kwargs: Keyword arguments for the function.

        Returns:
            JobResult with job_id and initial status.
        """
        pass

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[JobResult]:
        """Get the status of a job.

        Args:
            job_id: Job identifier.

        Returns:
            JobResult or None if not found.
        """
        pass

    @abstractmethod
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued job.

        Args:
            job_id: Job identifier.

        Returns:
            True if job was canceled, False if not found or already started.
        """
        pass

    def enqueue_at(
        self,
        func: Callable,
        scheduled_time: datetime,
        *args,
        queue_name: str = "default",
        **kwargs,
    ) -> JobResult:
        """Schedule a job to run at a specific time.

        Args:
            func: Function to execute.
            scheduled_time: When to run the job.
            *args: Positional arguments for the function.
            queue_name: Name of the queue.
            **kwargs: Keyword arguments for the function.

        Returns:
            JobResult with job_id and SCHEDULED status.
        """
        # Default implementation using delay
        delay = int((scheduled_time - datetime.now()).total_seconds())
        if delay < 0:
            delay = 0
        return self.enqueue(func, *args, queue_name=queue_name, delay=delay, **kwargs)

    def enqueue_in(
        self,
        func: Callable,
        delay_seconds: int,
        *args,
        queue_name: str = "default",
        **kwargs,
    ) -> JobResult:
        """Schedule a job to run after a delay.

        Args:
            func: Function to execute.
            delay_seconds: Seconds to wait before executing.
            *args: Positional arguments for the function.
            queue_name: Name of the queue.
            **kwargs: Keyword arguments for the function.

        Returns:
            JobResult with job_id and SCHEDULED status.
        """
        return self.enqueue(func, *args, queue_name=queue_name, delay=delay_seconds, **kwargs)

    def get_queue_length(self, queue_name: str = "default") -> int:
        """Get the number of jobs in a queue.

        Args:
            queue_name: Name of the queue.

        Returns:
            Number of pending jobs.
        """
        return 0  # Override in subclasses

    def get_failed_jobs(self, queue_name: str = "default") -> list[JobResult]:
        """Get failed jobs from a queue.

        Args:
            queue_name: Name of the queue.

        Returns:
            List of failed JobResults.
        """
        return []  # Override in subclasses

    def retry_job(self, job_id: str) -> Optional[JobResult]:
        """Retry a failed job.

        Args:
            job_id: Job identifier.

        Returns:
            New JobResult if retried, None if not found.
        """
        return None  # Override in subclasses

    def clear_queue(self, queue_name: str = "default") -> int:
        """Clear all jobs from a queue.

        Args:
            queue_name: Name of the queue.

        Returns:
            Number of jobs cleared.
        """
        return 0  # Override in subclasses
