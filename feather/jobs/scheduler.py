"""
Job Scheduler
=============

Schedule recurring jobs using cron-like syntax.

The scheduler runs jobs at specified intervals or times, similar to cron.
Uses RQ-Scheduler for production deployments with Redis.

Configuration
-------------
Set in environment variables or config.py::

    JOB_BACKEND=rq
    REDIS_URL=redis://localhost:6379/0

Running the Scheduler
---------------------
::

    # Install rq-scheduler
    pip install rq-scheduler

    # Start the scheduler process
    rqscheduler --url redis://localhost:6379/0

Usage
-----
::

    from feather.jobs import schedule, scheduled

    # Schedule using decorator
    @scheduled(cron='0 9 * * *')  # Every day at 9 AM
    def daily_report():
        generate_report()

    # Or schedule programmatically
    schedule(
        send_digest,
        cron='0 */6 * * *',  # Every 6 hours
        args=['daily'],
    )

    # Schedule with interval
    schedule(
        cleanup_temp_files,
        interval=3600,  # Every hour
    )

Cron Syntax
-----------
::

    ┌───────────── minute (0 - 59)
    │ ┌───────────── hour (0 - 23)
    │ │ ┌───────────── day of month (1 - 31)
    │ │ │ ┌───────────── month (1 - 12)
    │ │ │ │ ┌───────────── day of week (0 - 6) (Sunday = 0)
    │ │ │ │ │
    * * * * *

Examples:
- '0 9 * * *' - Every day at 9:00 AM
- '*/15 * * * *' - Every 15 minutes
- '0 0 * * 0' - Every Sunday at midnight
- '0 0 1 * *' - First day of every month at midnight
"""

from datetime import datetime, timezone
from typing import Any, Callable, Optional


# Registry of scheduled jobs for setup
_scheduled_jobs: list[dict] = []


def schedule(
    func: Callable,
    cron: Optional[str] = None,
    interval: Optional[int] = None,
    args: Optional[tuple] = None,
    kwargs: Optional[dict] = None,
    queue_name: str = "default",
    description: Optional[str] = None,
) -> str:
    """Schedule a recurring job.

    Args:
        func: Function to execute.
        cron: Cron expression (e.g., '0 9 * * *' for 9 AM daily).
        interval: Interval in seconds between runs.
        args: Positional arguments for the function.
        kwargs: Keyword arguments for the function.
        queue_name: Queue to run the job on (default: 'default').
        description: Human-readable description of the job.

    Returns:
        Job identifier/name.

    Raises:
        ValueError: If neither cron nor interval is provided.

    Example::

        # Run every day at 9 AM
        schedule(daily_report, cron='0 9 * * *')

        # Run every hour
        schedule(hourly_cleanup, interval=3600)

        # Run with arguments
        schedule(
            send_digest,
            cron='0 8 * * 1',  # Monday 8 AM
            args=['weekly'],
            kwargs={'include_stats': True},
        )
    """
    if not cron and not interval:
        raise ValueError("Either 'cron' or 'interval' must be provided")

    job_name = f"{func.__module__}.{func.__name__}"

    job_config = {
        "name": job_name,
        "func": func,
        "cron": cron,
        "interval": interval,
        "args": args or (),
        "kwargs": kwargs or {},
        "queue_name": queue_name,
        "description": description or func.__doc__ or job_name,
    }

    _scheduled_jobs.append(job_config)

    return job_name


def scheduled(
    cron: Optional[str] = None,
    interval: Optional[int] = None,
    queue_name: str = "default",
    description: Optional[str] = None,
) -> Callable:
    """Decorator to schedule a function as a recurring job.

    Args:
        cron: Cron expression (e.g., '0 9 * * *' for 9 AM daily).
        interval: Interval in seconds between runs.
        queue_name: Queue to run the job on.
        description: Human-readable description.

    Returns:
        Decorator function.

    Example::

        @scheduled(cron='0 9 * * *')  # Every day at 9 AM
        def daily_report():
            '''Generate daily analytics report'''
            generate_report()

        @scheduled(interval=3600)  # Every hour
        def hourly_cleanup():
            '''Clean up temporary files'''
            cleanup_temp_files()
    """

    def decorator(func: Callable) -> Callable:
        schedule(
            func,
            cron=cron,
            interval=interval,
            queue_name=queue_name,
            description=description,
        )
        return func

    return decorator


def get_scheduled_jobs() -> list[dict]:
    """Get all registered scheduled jobs.

    Returns:
        List of job configurations.
    """
    return _scheduled_jobs.copy()


def clear_scheduled_jobs() -> None:
    """Clear all registered scheduled jobs.

    Useful for testing.
    """
    _scheduled_jobs.clear()


def setup_scheduler(redis_url: str = "redis://localhost:6379/0") -> Any:
    """Set up rq-scheduler with registered jobs.

    Call this after all @scheduled decorators have been processed
    (typically at app startup).

    Args:
        redis_url: Redis connection URL.

    Returns:
        Scheduler instance.

    Example::

        # In app.py or wsgi.py
        from feather.jobs.scheduler import setup_scheduler

        # Import modules with @scheduled decorators
        import jobs.daily
        import jobs.hourly

        # Set up the scheduler
        scheduler = setup_scheduler()

    Note:
        You still need to run `rqscheduler` as a separate process.
    """
    try:
        from redis import Redis
        from rq_scheduler import Scheduler
    except ImportError:
        raise ImportError(
            "Scheduler requires 'rq-scheduler' package. "
            "Install it with: pip install rq-scheduler"
        )

    redis_conn = Redis.from_url(redis_url)
    scheduler = Scheduler(connection=redis_conn)

    # Cancel existing scheduled jobs with our names
    for job in scheduler.get_jobs():
        if hasattr(job, "meta") and job.meta.get("feather_scheduled"):
            scheduler.cancel(job)

    # Register all scheduled jobs
    for job_config in _scheduled_jobs:
        if job_config["cron"]:
            scheduler.cron(
                job_config["cron"],
                func=job_config["func"],
                args=job_config["args"],
                kwargs=job_config["kwargs"],
                queue_name=job_config["queue_name"],
                meta={"feather_scheduled": True, "name": job_config["name"]},
            )
        elif job_config["interval"]:
            scheduler.schedule(
                scheduled_time=datetime.now(timezone.utc),
                func=job_config["func"],
                args=job_config["args"],
                kwargs=job_config["kwargs"],
                interval=job_config["interval"],
                queue_name=job_config["queue_name"],
                meta={"feather_scheduled": True, "name": job_config["name"]},
            )

    return scheduler


def list_jobs() -> list[dict]:
    """List all scheduled jobs with their configurations.

    Returns a list of job info dictionaries for display.

    Returns:
        List of job info dicts with name, schedule, description.
    """
    jobs = []
    for job_config in _scheduled_jobs:
        schedule_str = job_config["cron"] or f"every {job_config['interval']}s"
        jobs.append({
            "name": job_config["name"],
            "schedule": schedule_str,
            "queue": job_config["queue_name"],
            "description": job_config["description"],
        })
    return jobs
