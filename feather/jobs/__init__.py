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
Limit concurrent executions to prevent resource exhaustion (thread backend;
RQ warns once and ignores it, since it has no per-task limit)::

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

    # Start a worker (Flask app context provided automatically)
    feather worker

    # Process specific queues in priority order
    feather worker high default low

    # Delayed jobs and scheduled jobs work automatically
    # (scheduler is enabled by default)
"""

import warnings
from functools import wraps
from typing import Any, Callable, Optional

from feather.core.config import as_bool, get_setting
from feather.core.registry import get_backend, set_backend
from feather.jobs.base import JobQueue, JobResult, JobStatus
from feather.jobs.scheduler import schedule, scheduled, get_scheduled_jobs, setup_scheduler

#: Registry key for the per-app queue.
_QUEUE_KEY = "queue"


def _build_queue(app) -> JobQueue:
    """Create the queue backend this app's configuration asks for.

    Configuration comes from :func:`feather.core.config.get_setting`: the
    app config first, the environment when the app has no value (or when
    there is no app at all). Defaults are unchanged from 0.9.7.
    """
    backend = get_setting("JOB_BACKEND", "sync")
    redis_url = get_setting("REDIS_URL", None)
    max_workers = get_setting("JOB_MAX_WORKERS", 4, cast=int)
    enable_monitoring = get_setting("JOB_ENABLE_MONITORING", False, cast=as_bool)
    # `or "pickle"`, not a plain default: a config.py that reads
    # JOB_SERIALIZER straight from the environment leaves the key present
    # but None, and falling back to pickle there would put the queue and
    # `feather worker` on different serializers.
    serializer = get_setting("JOB_SERIALIZER", None) or "pickle"

    if backend == "rq":
        from feather.jobs.rq import RQQueue

        return RQQueue(redis_url=redis_url or "redis://localhost:6379/0", serializer=serializer)

    if backend == "thread":
        from feather.jobs.thread import ThreadPoolQueue

        queue = ThreadPoolQueue(
            max_workers=max_workers,
            enable_monitoring=enable_monitoring,
        )
        if app is not None:
            queue.set_app(app)
        return queue

    from feather.jobs.sync import SyncQueue

    return SyncQueue()


def get_queue() -> JobQueue:
    """Get the configured job queue backend for the current app.

    The queue is created once per Flask app and stored in
    ``app.extensions["feather"]``, so two apps in one process never share a
    queue. Outside an app context (a script, ``feather worker``, a
    module-level ``@job``) it resolves to the process-level default queue.

    Returns:
        JobQueue instance.

    Configuration:
        JOB_BACKEND: 'sync' (default), 'thread', or 'rq'
        JOB_SERIALIZER: 'pickle' (default) or 'json' (rq backend; safer)
        JOB_MAX_WORKERS: Thread pool size (for thread backend)
        JOB_ENABLE_MONITORING: Enable psutil resource tracking (thread backend)
        REDIS_URL: Redis connection URL (for rq backend)

    Example::

        from feather.jobs import get_queue

        queue = get_queue()
        result = queue.enqueue(process_data, data)
        print(result.job_id)
    """
    return get_backend(_QUEUE_KEY, _build_queue)


def init_jobs(app) -> JobQueue:
    """Initialize the job queue for a Flask app.

    Optional: the queue is created lazily on first use. Calling this stores
    the queue on ``app.extensions["feather"]["queue"]`` up front, which is
    useful when the app is configured after import.

    Args:
        app: Flask application instance.

    Returns:
        JobQueue instance for this app.
    """
    with app.app_context():
        queue = _build_queue(app)
    return set_backend(_QUEUE_KEY, queue, app=app)


def _backend_options(queue: JobQueue, decorated: Callable) -> dict[str, Any]:
    """Translate @job options into kwargs this backend understands.

    ``retry`` goes to every backend: the thread backend retries in process,
    the RQ backend turns it into ``rq.Retry``. ``concurrency`` only reaches
    backends that advertise ``supports_concurrency``; RQ has no per-task
    concurrency limit (it is a worker-count setting), so rather than
    silently dropping the option - which is what 0.9.7 did - the job warns
    once and runs unthrottled.

    Args:
        queue: The backend the job is about to be enqueued on.
        decorated: The wrapper the @job decorator produced, carrying the
            declared ``retry``/``concurrency`` and the once-only warning flag.

    Returns:
        Extra kwargs for ``queue.enqueue()``.
    """
    options: dict[str, Any] = {}

    retry = getattr(decorated, "retry", 0)
    if retry:
        options["retry"] = retry

    concurrency = getattr(decorated, "concurrency", None)
    if concurrency is not None:
        if getattr(queue, "supports_concurrency", False):
            options["concurrency"] = concurrency
        elif not getattr(decorated, "_concurrency_warning_emitted", False):
            decorated._concurrency_warning_emitted = True
            warnings.warn(
                f"@job(concurrency={concurrency}) on "
                f"{getattr(decorated, '__name__', 'job')} is not supported by the "
                f"{type(queue).__name__} backend and is ignored; it has no "
                "per-task concurrency limit. Limit the number of workers "
                "instead, or use JOB_BACKEND=thread.",
                RuntimeWarning,
                stacklevel=3,
            )

    return options


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
        concurrency: Max concurrent executions. None means unlimited.
            Honoured by the thread backend (a semaphore per task). RQ has no
            per-task concurrency limit, so on that backend the option is
            ignored and the first enqueue warns (RuntimeWarning) instead of
            failing - cap the number of workers there instead.
        retry: Number of retries on failure. The thread backend retries in
            process with exponential backoff; the RQ backend passes it to
            ``rq.Retry`` so the worker re-queues the job. Before 0.9.8 this
            was silently dropped on RQ.
        timeout: Max execution time in seconds. The thread backend marks the
            job TIMEOUT; RQ passes it as ``job_timeout``.

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
            options = _backend_options(queue, wrapper)
            return queue.enqueue(
                f,
                *args,
                queue_name=queue_name,
                delay=delay,
                job_timeout=timeout,
                **options,
                **kwargs,
            )

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


def __getattr__(name):
    """Deprecation shim for the 0.9.7 module-level queue singleton.

    ``feather.jobs._queue_instance`` was the process-wide queue. It is now
    per app (``app.extensions["feather"]["queue"]``); reading the old name
    returns the current app's queue and warns. Assigning to it no longer
    has any effect - use
    ``feather.core.registry.set_backend("queue", queue)`` (or
    ``reset_backends(None, "queue")``) instead.
    """
    if name == "_queue_instance":
        warnings.warn(
            "feather.jobs._queue_instance was replaced by the per-app registry in "
            "0.9.8. Use feather.jobs.get_queue(), or "
            "feather.core.registry.set_backend('queue', queue) to override it. "
            "Assigning to _queue_instance no longer has any effect.",
            DeprecationWarning,
            stacklevel=2,
        )
        return get_queue()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
