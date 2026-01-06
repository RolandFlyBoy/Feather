"""Health check endpoint for load balancers and monitoring.

Provides a /health endpoint that returns the application's health status,
including optional database connectivity checks.
"""

from flask import Blueprint, jsonify, current_app
from datetime import datetime, timezone


health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health_check():
    """Health check endpoint for load balancers.

    Returns a JSON response with the application's health status.
    Load balancers can use this endpoint to determine if the
    application is ready to receive traffic.

    Returns:
        200 OK with health details if healthy
        503 Service Unavailable if unhealthy

    Response format::

        {
            "status": "healthy",
            "timestamp": "2024-01-15T10:30:00.000Z",
            "checks": {
                "database": "ok"
            }
        }
    """
    checks = {}
    healthy = True

    # Check database connectivity
    db_status = _check_database()
    checks["database"] = db_status
    # "ok" or "skipped" are healthy; only error states are unhealthy
    if db_status not in ("ok", "skipped"):
        healthy = False

    response = {
        "status": "healthy" if healthy else "unhealthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }

    status_code = 200 if healthy else 503
    return jsonify(response), status_code


@health_bp.route("/health/live")
def liveness_check():
    """Kubernetes liveness probe endpoint.

    Simple check that the application process is running.
    Does not check dependencies - use /health for that.

    Returns:
        200 OK always (if the app is responding)
    """
    return jsonify({"status": "alive"}), 200


@health_bp.route("/health/ready")
def readiness_check():
    """Kubernetes readiness probe endpoint.

    Checks if the application is ready to receive traffic.
    Same as /health but with Kubernetes-friendly naming.

    Returns:
        200 OK if ready, 503 if not ready
    """
    return health_check()


def _check_database() -> str:
    """Check database connectivity.

    Returns:
        'ok' if database is accessible
        'error: <message>' if database check fails
        'skipped' if no database configured
    """
    try:
        from feather.db import db

        # Check if we have a database URI configured
        db_uri = current_app.config.get("SQLALCHEMY_DATABASE_URI")
        if not db_uri:
            return "skipped"

        # Execute a simple query to verify connectivity
        db.session.execute(db.text("SELECT 1"))
        return "ok"

    except ImportError:
        return "skipped"
    except Exception as e:
        return f"error: {str(e)}"


def init_health(app):
    """Register the health check blueprint.

    Called automatically by Feather during app initialization.

    Args:
        app: Flask application instance.
    """
    app.register_blueprint(health_bp)
