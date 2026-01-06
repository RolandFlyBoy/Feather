"""Feather middleware components.

This module provides middleware for request tracking and logging.
"""

import uuid
import logging
import json
from datetime import datetime, timezone
from functools import wraps
from typing import Optional

from flask import Flask, g, request, has_request_context


# Request ID header name (standard)
REQUEST_ID_HEADER = "X-Request-ID"


def get_request_id() -> Optional[str]:
    """Get the current request ID.

    Returns the request ID for the current request, or None if not in
    a request context.

    Example::

        from feather.core.middleware import get_request_id

        @api.get('/users')
        def list_users():
            logger.info(f"Request {get_request_id()}: listing users")
            # ...
    """
    if has_request_context():
        return getattr(g, "request_id", None)
    return None


def init_request_id(app: Flask):
    """Initialize request ID middleware.

    Generates or extracts a unique ID for each request, making it available
    via ``g.request_id`` and adding it to response headers.

    Request IDs help with:
    - Tracing requests through logs
    - Debugging distributed systems
    - Correlating frontend errors with backend logs

    The request ID is:
    - Extracted from incoming X-Request-ID header (if present)
    - Otherwise, a new UUID is generated

    Args:
        app: Flask application instance.

    Example:
        In your routes, access the request ID::

            from flask import g

            @api.get('/users')
            def list_users():
                print(f"Request ID: {g.request_id}")
                # ...
    """

    @app.before_request
    def set_request_id():
        """Set request ID from header or generate a new one."""
        # Use existing request ID if provided, otherwise generate
        request_id = request.headers.get(REQUEST_ID_HEADER)
        if not request_id:
            request_id = str(uuid.uuid4())
        g.request_id = request_id
        g.request_start_time = datetime.now(timezone.utc)

    @app.after_request
    def add_request_id_header(response):
        """Add request ID to response headers."""
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers[REQUEST_ID_HEADER] = request_id
        return response


class RequestIdFilter(logging.Filter):
    """Logging filter that adds request_id to log records.

    Use this filter to automatically include the request ID in all log
    messages when using structured logging.

    Example::

        handler = logging.StreamHandler()
        handler.addFilter(RequestIdFilter())
        logger.addHandler(handler)
    """

    def filter(self, record):
        record.request_id = get_request_id() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """JSON log formatter for structured logging.

    Outputs logs as JSON objects, ideal for log aggregation services
    like Google Cloud Logging, Datadog, or ELK stack.

    Output format::

        {
            "timestamp": "2024-01-15T10:30:00.000Z",
            "level": "INFO",
            "message": "User logged in",
            "request_id": "abc-123",
            "logger": "myapp.auth",
            "extra": {...}
        }

    Example::

        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Add request ID if available
        request_id = getattr(record, "request_id", None) or get_request_id()
        if request_id:
            log_data["request_id"] = request_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields (anything not in standard LogRecord)
        standard_attrs = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "pathname", "process", "processName", "relativeCreated",
            "stack_info", "exc_info", "exc_text", "thread", "threadName",
            "request_id", "message", "asctime",
        }
        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in standard_attrs and not k.startswith("_")
        }
        if extras:
            log_data["extra"] = extras

        return json.dumps(log_data)


def setup_logging(
    app: Flask,
    json_format: bool = False,
    level: int = logging.INFO,
):
    """Configure application logging.

    Sets up logging with optional JSON formatting for production use.
    Automatically includes request IDs in all log messages.

    In debug mode (FLASK_DEBUG=1), also writes logs to logs/app.log for
    easy tailing in a separate terminal.

    Args:
        app: Flask application instance.
        json_format: If True, output logs as JSON (recommended for production).
        level: Logging level (default: INFO).

    Example::

        from feather.core.middleware import setup_logging

        app = Feather(__name__)
        setup_logging(app, json_format=True)

    Configuration:
        Can also be configured via environment variables:
        - LOG_LEVEL: DEBUG, INFO, WARNING, ERROR, CRITICAL
        - LOG_FORMAT: 'json' for JSON output, anything else for text
    """
    import os
    from pathlib import Path

    # Allow environment override
    env_level = os.environ.get("LOG_LEVEL", "").upper()
    if env_level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        level = getattr(logging, env_level)

    env_format = os.environ.get("LOG_FORMAT", "")
    if env_format.lower() == "json":
        json_format = True

    # Get the root logger and app logger
    root_logger = logging.getLogger()
    app_logger = app.logger

    # Set levels
    root_logger.setLevel(level)
    app_logger.setLevel(level)

    # Create console handler
    handler = logging.StreamHandler()
    handler.setLevel(level)

    # Add request ID filter
    handler.addFilter(RequestIdFilter())

    # Set formatter
    text_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s"
    )
    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(text_formatter)

    # Clear existing handlers and add ours
    root_logger.handlers = []
    root_logger.addHandler(handler)

    # In debug mode, also write to file for easy tailing
    if os.environ.get("FLASK_DEBUG") == "1":
        logs_dir = Path(app.root_path) / "logs"
        logs_dir.mkdir(exist_ok=True)
        log_file = logs_dir / "app.log"

        file_handler = logging.FileHandler(str(log_file))
        file_handler.setLevel(logging.DEBUG)  # Capture everything in file
        file_handler.addFilter(RequestIdFilter())
        file_handler.setFormatter(text_formatter)
        root_logger.addHandler(file_handler)

        # Log that file logging is enabled
        app_logger.info(f"File logging enabled: {log_file}")

    # Reduce noise from some verbose loggers
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
