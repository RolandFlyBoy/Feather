"""CLI commands for job queue management."""

import click
from datetime import datetime, timezone


@click.group()
def jobs():
    """Manage background jobs."""
    pass


@jobs.command("list")
@click.option("--status", type=click.Choice(["queued", "started", "failed", "timeout", "all"]), default="all",
              help="Filter by status")
@click.option("--stuck", is_flag=True, help="Show only jobs running longer than threshold")
@click.option("--stuck-minutes", default=30, help="Minutes before a job is considered stuck (default: 30)")
def list_jobs(status, stuck, stuck_minutes):
    """List jobs in the queue.

    Examples:

        feather jobs list
        feather jobs list --status failed
        feather jobs list --stuck --stuck-minutes 60
    """
    from feather.jobs import get_queue
    from feather.jobs.base import JobStatus

    queue = get_queue()

    # Check if this is a thread pool queue with job tracking
    if not hasattr(queue, '_jobs'):
        click.echo("Job listing only supported for thread backend (JOB_BACKEND=thread)")
        return

    jobs_dict = queue._jobs

    if not jobs_dict:
        click.echo("No jobs found")
        return

    # Filter jobs
    filtered_jobs = []
    for job_id, job in jobs_dict.items():
        # Status filter
        if status != "all" and job.status.value != status:
            continue

        # Stuck filter
        if stuck:
            if job.status != JobStatus.STARTED:
                continue
            if job.started_at:
                running_time = (datetime.now(timezone.utc) - job.started_at).total_seconds() / 60
                if running_time < stuck_minutes:
                    continue
            else:
                continue

        filtered_jobs.append(job)

    if not filtered_jobs:
        if stuck:
            click.echo(f"No stuck jobs (running > {stuck_minutes} minutes)")
        else:
            click.echo(f"No jobs with status '{status}'")
        return

    # Display jobs
    click.echo(f"{'ID':<36} {'Status':<12} {'Duration':<12}")
    click.echo("-" * 60)

    for job in filtered_jobs:
        duration = ""
        if job.started_at:
            end_time = job.ended_at or datetime.now(timezone.utc)
            delta = end_time - job.started_at
            seconds = delta.total_seconds()
            if seconds < 60:
                duration = f"{seconds:.1f}s"
            elif seconds < 3600:
                duration = f"{seconds/60:.1f}m"
            else:
                duration = f"{seconds/3600:.1f}h"

        click.echo(f"{job.job_id:<36} {job.status.value:<12} {duration:<12}")


@jobs.command("info")
@click.argument("job_id")
def job_info(job_id):
    """Show detailed info for a job.

    Example:

        feather jobs info abc123-def456
    """
    from feather.jobs import get_queue

    queue = get_queue()
    job = queue.get_job(job_id)

    if not job:
        click.echo(f"Job {job_id} not found")
        return

    click.echo(f"Job ID:    {job.job_id}")
    click.echo(f"Status:    {job.status.value}")
    click.echo(f"Enqueued:  {job.enqueued_at}")
    click.echo(f"Started:   {job.started_at or 'N/A'}")
    click.echo(f"Ended:     {job.ended_at or 'N/A'}")

    if job.result is not None:
        click.echo(f"Result:    {job.result}")

    if job.error:
        click.echo(f"\nError:")
        click.echo(job.error)


@jobs.command("failed")
def failed_jobs():
    """List failed and timed-out jobs.

    Example:

        feather jobs failed
    """
    from feather.jobs import get_queue
    from feather.jobs.base import JobStatus

    queue = get_queue()

    # Get failed jobs
    failed = queue.get_failed_jobs()

    # Also get timed-out jobs if using thread backend
    timed_out = []
    if hasattr(queue, '_jobs'):
        timed_out = [job for job in queue._jobs.values() if job.status == JobStatus.TIMEOUT]

    all_failed = failed + timed_out

    if not all_failed:
        click.echo("No failed or timed-out jobs")
        return

    click.echo(f"{'ID':<36} {'Status':<12} {'Error':<40}")
    click.echo("-" * 90)

    for job in all_failed:
        error_preview = ""
        if job.error:
            # First line of error, truncated
            first_line = job.error.split('\n')[0]
            error_preview = first_line[:40] + "..." if len(first_line) > 40 else first_line

        click.echo(f"{job.job_id:<36} {job.status.value:<12} {error_preview:<40}")


@jobs.command("retry")
@click.argument("job_id")
def retry_job(job_id):
    """Re-queue a failed job.

    Example:

        feather jobs retry abc123-def456
    """
    from feather.jobs import get_queue

    queue = get_queue()
    result = queue.retry_job(job_id)

    if result:
        click.echo(f"Retried job {job_id} -> new job {result.job_id}")
    else:
        click.echo(f"Could not retry job {job_id} (not found or not failed)")


@jobs.command("clear")
@click.confirmation_option(prompt="Are you sure you want to clear all job history?")
def clear_jobs():
    """Clear all job history.

    Note: This does not cancel running jobs, only clears the history.

    Example:

        feather jobs clear
    """
    from feather.jobs import get_queue

    queue = get_queue()
    count = queue.clear_queue()
    click.echo(f"Cleared {count} jobs from history")


@jobs.command("status")
def queue_status():
    """Show overall queue status.

    Example:

        feather jobs status
    """
    from feather.jobs import get_queue
    from feather.jobs.base import JobStatus

    queue = get_queue()

    # Queue type
    queue_type = type(queue).__name__
    click.echo(f"Backend: {queue_type}")

    # Queue length
    pending = queue.get_queue_length()
    click.echo(f"Pending:  {pending}")

    # Job counts by status (thread backend only)
    if hasattr(queue, '_jobs'):
        status_counts = {}
        for job in queue._jobs.values():
            status_counts[job.status.value] = status_counts.get(job.status.value, 0) + 1

        click.echo(f"\nJob counts:")
        for status_name, count in sorted(status_counts.items()):
            click.echo(f"  {status_name}: {count}")

    # Semaphore status (thread backend only)
    if hasattr(queue, 'get_semaphore_status'):
        sem_status = queue.get_semaphore_status()
        if sem_status:
            click.echo(f"\nConcurrency limits:")
            for task_name, info in sem_status.items():
                available = "available" if info.get("available") else "at capacity"
                click.echo(f"  {task_name}: {available}")
