"""feather worker - Start an RQ worker with Flask app context."""

import os
import sys
from pathlib import Path

import click


def _get_app():
    """Import and return the Flask app from the current directory."""
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())

    try:
        from app import app
        return app
    except ImportError as e:
        raise click.ClickException(
            f"Could not import app: {e}\n"
            "Make sure you're in a Feather project directory with app.py"
        )


@click.command()
@click.argument("queues", nargs=-1)
@click.option("--burst", is_flag=True, help="Run in burst mode (exit when queue is empty)")
@click.option(
    "--simple/--fork", "simple", default=None,
    help="Worker class: SimpleWorker runs jobs in-process (no fork); "
         "the forking Worker isolates each job in a child. "
         "Default: simple on macOS, fork elsewhere.",
)
@click.option(
    "--simple-worker", "force_simple", is_flag=True,
    help="Deprecated alias for --simple.",
)
@click.option("--no-scheduler", is_flag=True, help="Disable built-in scheduler (delayed jobs won't execute)")
@click.option("--name", default=None, help="Worker name")
@click.option(
    "--log-level", default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    help="Logging level",
)
def worker(queues, burst, simple, force_simple, no_scheduler, name, log_level):
    """Start an RQ worker to process background jobs.

    Automatically provides Flask app context so jobs can access
    the database, config, and other Flask features.

    \b
    Examples:
      feather worker                    Process 'default' queue
      feather worker high default low   Process specific queues (priority order)
      feather worker --burst            Exit when queue is empty
      feather worker --simple            Force SimpleWorker (no fork)
      feather worker --fork              Force the forking Worker (containers)
    """
    # Verify we're in a Feather project
    if not Path("app.py").exists():
        raise click.ClickException(
            "Not in a Feather project directory. "
            "Run this from your project root (where app.py is)."
        )

    # Import RQ (fail early with helpful message)
    try:
        from redis import Redis
        from rq import Queue
    except ImportError:
        raise click.ClickException(
            "RQ not installed. Install it with: pip install rq"
        )

    # Load the Flask app
    app = _get_app()

    # Get Redis URL from app config
    with app.app_context():
        redis_url = app.config.get("REDIS_URL") or os.environ.get("REDIS_URL")
        from feather.jobs.rq import resolve_serializer

        # `or` rather than dict.get's default: a config.py that does
        # JOB_SERIALIZER = os.environ.get("JOB_SERIALIZER") leaves the key
        # present but None, which would have silently fallen back to pickle
        # while the queue side used json - and then nothing runs.
        serializer_name = (
            app.config.get("JOB_SERIALIZER")
            or os.environ.get("JOB_SERIALIZER")
            or "pickle"
        )
        serializer = resolve_serializer(serializer_name)
        if not redis_url:
            redis_url = "redis://localhost:6379/0"
            click.echo(click.style(
                "Warning: REDIS_URL not configured, using localhost default",
                fg="yellow",
            ))

    # Choose the worker class. macOS fork() is not safe with the Obj-C
    # runtime, so SimpleWorker is the default there; in a Linux container
    # forking is right, because a job that leaks or segfaults dies with its
    # child instead of taking the worker down.
    explicit = simple if simple is not None else (True if force_simple else None)
    use_simple = explicit if explicit is not None else (sys.platform == "darwin")

    if use_simple:
        from rq import SimpleWorker as WorkerClass
        worker_type = "SimpleWorker"
    else:
        from rq import Worker as WorkerClass
        worker_type = "Worker"

    if explicit is None and use_simple:
        click.echo(click.style(
            "Note: Using SimpleWorker on macOS (fork() is not safe with Obj-C "
            "runtime). Pass --fork to override.",
            fg="yellow",
        ))
    elif explicit is False and sys.platform == "darwin":
        click.echo(click.style(
            "Warning: --fork on macOS; fork() is not safe with the Obj-C runtime "
            "and jobs may crash.",
            fg="yellow",
        ))

    # Set up queues
    queue_names = queues or ("default",)
    conn = Redis.from_url(redis_url)
    rq_queues = [Queue(q, connection=conn, serializer=serializer) for q in queue_names]

    # Scheduler enabled by default (required for delayed jobs)
    enable_scheduler = not no_scheduler

    # Display startup info
    click.echo(click.style("Starting Feather worker...", fg="cyan", bold=True))
    click.echo(f"  Worker type: {worker_type}")
    click.echo(f"  Queues:      {', '.join(queue_names)}")
    click.echo(f"  Redis:       {redis_url}")
    click.echo(f"  Scheduler:   {'enabled' if enable_scheduler else 'disabled'}")
    click.echo(f"  Serializer:  {serializer.__name__}")
    if name:
        click.echo(f"  Name:        {name}")
    click.echo()

    # Start worker inside Flask app context
    with app.app_context():
        w = WorkerClass(
            rq_queues,
            connection=conn,
            name=name,
            log_job_description=True,
            serializer=serializer,
        )

        import logging
        logging.basicConfig(level=getattr(logging, log_level))

        try:
            w.work(
                burst=burst,
                with_scheduler=enable_scheduler,
                logging_level=log_level,
            )
        except KeyboardInterrupt:
            click.echo("\nWorker stopped.")
