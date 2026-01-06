"""
Redis Queue (RQ) Backend
========================

Production job queue using Redis Queue (RQ).

RQ provides reliable background job processing with:
- Persistent job storage in Redis
- Multiple workers with concurrency control
- Job retries and failure handling
- Scheduled/delayed jobs
- Job dependencies

Configuration
-------------
Set in environment variables or config.py::

    JOB_BACKEND=rq
    REDIS_URL=redis://localhost:6379/0

Running Workers
---------------
Start a worker to process jobs::

    # Install RQ
    pip install rq

    # Start worker (processes all queues)
    rq worker --url redis://localhost:6379/0

    # Or specific queues
    rq worker high default low --url redis://localhost:6379/0

Usage
-----
::

    from feather.jobs import job, get_queue

    @job
    def send_email(to, subject, body):
        # Send email...
        pass

    # Enqueue job
    send_email.enqueue('user@example.com', 'Hello', 'World')

    # Enqueue with delay
    send_email.enqueue('user@example.com', 'Hello', 'World', delay=60)

    # Enqueue to specific queue
    send_email.enqueue('user@example.com', 'Hello', 'World', queue_name='emails')

Note:
    Requires the `rq` package: pip install rq
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional

from feather.jobs.base import JobQueue, JobResult, JobStatus


def _rq_status_to_job_status(rq_status: str) -> JobStatus:
    """Convert RQ job status to JobStatus."""
    status_map = {
        "queued": JobStatus.QUEUED,
        "started": JobStatus.STARTED,
        "finished": JobStatus.FINISHED,
        "failed": JobStatus.FAILED,
        "deferred": JobStatus.DEFERRED,
        "scheduled": JobStatus.SCHEDULED,
        "canceled": JobStatus.CANCELED,
        "stopped": JobStatus.CANCELED,
    }
    return status_map.get(rq_status, JobStatus.QUEUED)


class RQQueue(JobQueue):
    """Redis Queue (RQ) job queue backend.

    Uses RQ for reliable background job processing with Redis.

    Args:
        redis_url: Redis connection URL (default: redis://localhost:6379/0).
        default_queue: Default queue name (default: 'default').
        default_timeout: Default job timeout in seconds (default: 300).

    Example::

        queue = RQQueue(redis_url='redis://localhost:6379/0')

        result = queue.enqueue(process_order, order_id=123)
        print(result.job_id)

        # Check status later
        status = queue.get_job(result.job_id)
        if status.is_finished():
            print(status.result)
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        default_queue: str = "default",
        default_timeout: int = 300,
    ):
        try:
            from redis import Redis
            from rq import Queue
        except ImportError:
            raise ImportError(
                "RQ queue requires the 'rq' package. "
                "Install it with: pip install rq"
            )

        self._redis = Redis.from_url(redis_url)
        self._default_queue = default_queue
        self._default_timeout = default_timeout
        self._queues: dict[str, Queue] = {}

        # Pre-create default queue
        self._queues[default_queue] = Queue(
            name=default_queue,
            connection=self._redis,
            default_timeout=default_timeout,
        )

    def _get_queue(self, name: str):
        """Get or create a queue by name."""
        from rq import Queue

        if name not in self._queues:
            self._queues[name] = Queue(
                name=name,
                connection=self._redis,
                default_timeout=self._default_timeout,
            )
        return self._queues[name]

    def enqueue(
        self,
        func: Callable,
        *args,
        queue_name: str = "default",
        delay: Optional[int] = None,
        job_timeout: Optional[int] = None,
        retry: Optional[int] = None,
        **kwargs,
    ) -> JobResult:
        """Add a job to the queue.

        Args:
            func: Function to execute.
            *args: Positional arguments for the function.
            queue_name: Name of the queue (default: 'default').
            delay: Delay execution by N seconds (optional).
            job_timeout: Timeout for this job in seconds (optional).
            retry: Number of retry attempts on failure (optional).
            **kwargs: Keyword arguments for the function.

        Returns:
            JobResult with job_id and initial status.
        """
        from rq import Retry

        queue = self._get_queue(queue_name)

        # Build enqueue kwargs
        enqueue_kwargs = {
            "args": args,
            "kwargs": kwargs,
        }

        if job_timeout:
            enqueue_kwargs["job_timeout"] = job_timeout

        if retry:
            enqueue_kwargs["retry"] = Retry(max=retry)

        # Enqueue with or without delay
        if delay and delay > 0:
            job = queue.enqueue_in(
                timedelta(seconds=delay),
                func,
                **enqueue_kwargs,
            )
            status = JobStatus.SCHEDULED
        else:
            job = queue.enqueue(func, **enqueue_kwargs)
            status = JobStatus.QUEUED

        return JobResult(
            job_id=job.id,
            status=status,
            enqueued_at=datetime.now(timezone.utc),
        )

    def get_job(self, job_id: str) -> Optional[JobResult]:
        """Get the status of a job.

        Args:
            job_id: Job identifier.

        Returns:
            JobResult or None if not found.
        """
        from rq.job import Job

        try:
            job = Job.fetch(job_id, connection=self._redis)
        except Exception:
            return None

        result = JobResult(
            job_id=job.id,
            status=_rq_status_to_job_status(job.get_status()),
            enqueued_at=job.enqueued_at,
            started_at=job.started_at,
            ended_at=job.ended_at,
        )

        if result.status == JobStatus.FINISHED:
            result.result = job.result

        if result.status == JobStatus.FAILED:
            result.error = job.exc_info

        return result

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued job.

        Args:
            job_id: Job identifier.

        Returns:
            True if job was canceled, False if not found or already started.
        """
        from rq.job import Job

        try:
            job = Job.fetch(job_id, connection=self._redis)
            if job.get_status() in ("queued", "scheduled", "deferred"):
                job.cancel()
                return True
            return False
        except Exception:
            return False

    def get_queue_length(self, queue_name: str = "default") -> int:
        """Get the number of jobs in a queue.

        Args:
            queue_name: Name of the queue.

        Returns:
            Number of pending jobs.
        """
        queue = self._get_queue(queue_name)
        return len(queue)

    def get_failed_jobs(self, queue_name: str = "default") -> list[JobResult]:
        """Get failed jobs from a queue.

        Args:
            queue_name: Name of the queue.

        Returns:
            List of failed JobResults.
        """
        from rq.registry import FailedJobRegistry

        queue = self._get_queue(queue_name)
        registry = FailedJobRegistry(queue=queue)

        results = []
        for job_id in registry.get_job_ids():
            job_result = self.get_job(job_id)
            if job_result:
                results.append(job_result)

        return results

    def retry_job(self, job_id: str) -> Optional[JobResult]:
        """Retry a failed job.

        Args:
            job_id: Job identifier.

        Returns:
            New JobResult if retried, None if not found.
        """
        from rq.job import Job

        try:
            job = Job.fetch(job_id, connection=self._redis)
            if job.get_status() == "failed":
                job.requeue()
                return JobResult(
                    job_id=job.id,
                    status=JobStatus.QUEUED,
                    enqueued_at=datetime.now(timezone.utc),
                )
            return None
        except Exception:
            return None

    def clear_queue(self, queue_name: str = "default") -> int:
        """Clear all jobs from a queue.

        Args:
            queue_name: Name of the queue.

        Returns:
            Number of jobs cleared.
        """
        queue = self._get_queue(queue_name)
        count = len(queue)
        queue.empty()
        return count

    @property
    def redis(self):
        """Access the underlying Redis connection for advanced operations."""
        return self._redis
