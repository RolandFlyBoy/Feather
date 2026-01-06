"""
Background Jobs Module
======================

Provides background job processing for Feather applications.

Supported Backends:
- SyncQueue: Synchronous execution for development (default)
- ThreadPoolQueue: Background threads with concurrency control (no Redis)
- RQQueue: Redis Queue for production background jobs

Configuration
-------------
Set in environment variables or config.py::

    # Use sync queue (default, for development)
    JOB_BACKEND=sync

    # Use thread pool (background execution without Redis)
    JOB_BACKEND=thread
    JOB_MAX_WORKERS=4              # Thread pool size
    JOB_ENABLE_MONITORING=true     # Enable psutil resource tracking

    # Use Redis Queue (for production with persistence)
    JOB_BACKEND=rq
    REDIS_URL=redis://localhost:6379/0

Quick Start
-----------
::

    from feather.jobs import job, get_queue

    # Define a job with the decorator
    @job
    def send_email(to, subject, body):
        # Send email...
        pass

    # Define a job with concurrency control
    @job(concurrency=2)  # Max 2 concurrent executions
    def transcribe_video(video_id):
        # Heavy processing...
        pass

    # Define a job with retry
    @job(concurrency=1, retry=2)  # Singleton with 2 retries
    def process_payment(order_id):
        # Critical task...
        pass

    # Enqueue the job (runs in background)
    result = transcribe_video.enqueue(video_id)

    # Check job status
    status = transcribe_video.get_status(result.job_id)
    if status.is_finished():
        print('Done!')

Job Decorator
-------------
The @job decorator adds an enqueue() method to your functions::

    @job
    def process_order(order_id):
        order = Order.query.get(order_id)
        # Process order...

    # Enqueue to run in background
    process_order.enqueue(order_id=123)

    # Enqueue with delay (run in 60 seconds)
    process_order.enqueue(order_id=123, delay=60)

    # Enqueue to specific queue
    process_order.enqueue(order_id=123, queue_name='orders')

Concurrency Control
-------------------
Limit concurrent executions to prevent resource exhaustion::

    @job(concurrency=2)  # Max 2 at once
    def transcribe_audio(file_path):
        # Whisper transcription - memory intensive
        pass

    # All these enqueue immediately, but only 2 run at a time
    for file in files:
        transcribe_audio.enqueue(file)

Direct Queue Access
-------------------
::

    from feather.jobs import get_queue

    queue = get_queue()
    result = queue.enqueue(my_function, arg1, arg2)
    print(result.job_id)

    # Check status later
    status = queue.get_job(result.job_id)

Scheduled Jobs
--------------
For recurring jobs, use the scheduler::

    from feather.jobs import scheduled

    @scheduled(cron='0 9 * * *')  # Every day at 9 AM
    def daily_report():
        generate_report()

    @scheduled(interval=3600)  # Every hour
    def hourly_cleanup():
        cleanup_temp_files()

Running Workers (Production)
----------------------------
::

    # Install RQ
    pip install rq

    # Start a worker
    rq worker --url redis://localhost:6379/0

    # For scheduled jobs, also run the scheduler
    pip install rq-scheduler
    rqscheduler --url redis://localhost:6379/0
"""

import os
from functools import wraps
from typing import Callable, Optional

from feather.jobs.base import JobQueue, JobResult, JobStatus
from feather.jobs.scheduler import schedule, scheduled, get_scheduled_jobs, setup_scheduler

# Singleton queue instance
_queue_instance: Optional[JobQueue] = None


def get_queue() -> JobQueue:
    """Get the configured job queue backend.

    Creates a singleton queue instance based on configuration.
    Uses JOB_BACKEND environment variable or config.

    Returns:
        JobQueue instance.

    Configuration:
        JOB_BACKEND: 'sync' (default), 'thread', or 'rq'
        JOB_MAX_WORKERS: Thread pool size (for thread backend)
        JOB_ENABLE_MONITORING: Enable psutil resource tracking (for thread backend)
        REDIS_URL: Redis connection URL (for rq backend)

    Example::

        from feather.jobs import get_queue

        queue = get_queue()
        result = queue.enqueue(process_data, data)
        print(result.job_id)
    """
    global _queue_instance

    if _queue_instance is not None:
        return _queue_instance

    # Get configuration
    try:
        from flask import current_app

        backend = current_app.config.get("JOB_BACKEND", os.environ.get("JOB_BACKEND", "sync"))
        redis_url = current_app.config.get("REDIS_URL", os.environ.get("REDIS_URL"))
        max_workers = current_app.config.get(
            "JOB_MAX_WORKERS", int(os.environ.get("JOB_MAX_WORKERS", "4"))
        )
        enable_monitoring = current_app.config.get(
            "JOB_ENABLE_MONITORING",
            os.environ.get("JOB_ENABLE_MONITORING", "").lower() in ("true", "1", "yes"),
        )
        app = current_app._get_current_object()
    except RuntimeError:
        # No Flask app context
        backend = os.environ.get("JOB_BACKEND", "sync")
        redis_url = os.environ.get("REDIS_URL")
        max_workers = int(os.environ.get("JOB_MAX_WORKERS", "4"))
        enable_monitoring = os.environ.get("JOB_ENABLE_MONITORING", "").lower() in ("true", "1", "yes")
        app = None

    # Create backend
    if backend == "rq":
        from feather.jobs.rq import RQQueue

        if not redis_url:
            redis_url = "redis://localhost:6379/0"
        _queue_instance = RQQueue(redis_url=redis_url)

    elif backend == "thread":
        from feather.jobs.thread import ThreadPoolQueue

        _queue_instance = ThreadPoolQueue(
            max_workers=max_workers,
            enable_monitoring=enable_monitoring,
        )
        if app is not None:
            _queue_instance.set_app(app)

    else:
        from feather.jobs.sync import SyncQueue

        _queue_instance = SyncQueue()

    return _queue_instance


def init_jobs(app) -> JobQueue:
    """Initialize job queue with Flask app.

    Optionally called to set up queue with app configuration.
    The queue is also lazily initialized on first use.

    Args:
        app: Flask application instance.

    Returns:
        JobQueue instance.
    """
    global _queue_instance

    # Reset instance to pick up new config
    _queue_instance = None

    # Get queue within app context
    with app.app_context():
        return get_queue()


def job(
    func: Callable = None,
    *,
    queue_name: str = "default",
    concurrency: Optional[int] = None,
    retry: int = 0,
    timeout: Optional[int] = None,
) -> Callable:
    """Decorator to make a function enqueuable as a background job.

    Adds .enqueue() and .get_status() methods to the function.

    Args:
        func: Function to decorate.
        queue_name: Default queue name for this job.
        concurrency: Max concurrent executions (thread backend only).
            None means unlimited. Use for resource-intensive tasks.
        retry: Number of retries on failure (thread backend only).
            Uses exponential backoff between retries.
        timeout: Max execution time in seconds (thread backend only).
            Job is marked as TIMEOUT if it exceeds this limit.

    Returns:
        Decorated function with enqueue capability.

    Example::

        @job
        def send_email(to, subject, body):
            # Send email...
            pass

        @job(concurrency=2)  # Max 2 concurrent executions
        def transcribe_video(video_id):
            # Heavy Whisper processing
            pass

        @job(concurrency=1, retry=2)  # Singleton with retries
        def process_payment(order_id):
            # Critical task
            pass

        @job(timeout=900)  # 15 minute timeout
        def long_running_job():
            # Process that shouldn't run forever
            pass

        # Call directly (synchronous)
        send_email('user@example.com', 'Hello', 'World')

        # Or enqueue for background processing
        result = send_email.enqueue('user@example.com', 'Hello', 'World')
        print(result.job_id)

        # Check status
        status = send_email.get_status(result.job_id)
        if status.is_finished():
            print('Done!')

        # Enqueue with options
        send_email.enqueue(
            'user@example.com', 'Hello', 'World',
            delay=60,  # Run in 60 seconds
            queue_name='emails',  # Use specific queue
        )
    """

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Direct call - execute synchronously
            return f(*args, **kwargs)

        def enqueue(
            *args,
            queue_name: str = queue_name,
            delay: Optional[int] = None,
            **kwargs,
        ) -> JobResult:
            """Enqueue this function as a background job.

            Args:
                *args: Positional arguments for the function.
                queue_name: Queue to run on (default: decorator's queue_name).
                delay: Delay in seconds before running.
                **kwargs: Keyword arguments for the function.

            Returns:
                JobResult with job_id.
            """
            queue = get_queue()
            return queue.enqueue(f, *args, queue_name=queue_name, delay=delay, **kwargs)

        def get_status(job_id: str) -> Optional[JobResult]:
            """Get the status of a job by ID.

            Args:
                job_id: Job identifier from enqueue result.

            Returns:
                JobResult or None if not found.
            """
            queue = get_queue()
            return queue.get_job(job_id)

        # Attach methods and metadata to the wrapper
        wrapper.enqueue = enqueue
        wrapper.get_status = get_status
        wrapper.queue_name = queue_name
        wrapper.concurrency = concurrency
        wrapper.retry = retry
        wrapper.timeout = timeout

        # Register task metadata with thread pool queue if applicable
        # This is done lazily when the queue is first accessed
        wrapper._original_func = f
        wrapper._registered = False

        def _ensure_registered():
            if not wrapper._registered:
                queue = get_queue()
                if hasattr(queue, "register_task"):
                    queue.register_task(f, concurrency=concurrency, retry=retry, timeout=timeout)
                wrapper._registered = True

        # Patch enqueue to ensure registration
        original_enqueue = enqueue

        def registered_enqueue(*args, **kwargs):
            _ensure_registered()
            return original_enqueue(*args, **kwargs)

        wrapper.enqueue = registered_enqueue

        return wrapper

    # Support both @job and @job() syntax
    if func is not None:
        return decorator(func)
    return decorator


__all__ = [
    # Factory
    "get_queue",
    "init_jobs",
    # Base classes
    "JobQueue",
    "JobResult",
    "JobStatus",
    # Decorator
    "job",
    # Scheduler
    "schedule",
    "scheduled",
    "get_scheduled_jobs",
    "setup_scheduler",
]
