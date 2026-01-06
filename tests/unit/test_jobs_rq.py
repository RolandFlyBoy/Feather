"""Unit tests for feather/jobs/rq.py.

Tests the Redis Queue (RQ) job backend.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

pytestmark = pytest.mark.unit


class TestRqStatusToJobStatus:
    """Test _rq_status_to_job_status function."""

    def test_queued_status(self):
        """Converts 'queued' to JobStatus.QUEUED."""
        from feather.jobs.rq import _rq_status_to_job_status
        from feather.jobs.base import JobStatus

        assert _rq_status_to_job_status("queued") == JobStatus.QUEUED

    def test_started_status(self):
        """Converts 'started' to JobStatus.STARTED."""
        from feather.jobs.rq import _rq_status_to_job_status
        from feather.jobs.base import JobStatus

        assert _rq_status_to_job_status("started") == JobStatus.STARTED

    def test_finished_status(self):
        """Converts 'finished' to JobStatus.FINISHED."""
        from feather.jobs.rq import _rq_status_to_job_status
        from feather.jobs.base import JobStatus

        assert _rq_status_to_job_status("finished") == JobStatus.FINISHED

    def test_failed_status(self):
        """Converts 'failed' to JobStatus.FAILED."""
        from feather.jobs.rq import _rq_status_to_job_status
        from feather.jobs.base import JobStatus

        assert _rq_status_to_job_status("failed") == JobStatus.FAILED

    def test_deferred_status(self):
        """Converts 'deferred' to JobStatus.DEFERRED."""
        from feather.jobs.rq import _rq_status_to_job_status
        from feather.jobs.base import JobStatus

        assert _rq_status_to_job_status("deferred") == JobStatus.DEFERRED

    def test_scheduled_status(self):
        """Converts 'scheduled' to JobStatus.SCHEDULED."""
        from feather.jobs.rq import _rq_status_to_job_status
        from feather.jobs.base import JobStatus

        assert _rq_status_to_job_status("scheduled") == JobStatus.SCHEDULED

    def test_canceled_status(self):
        """Converts 'canceled' to JobStatus.CANCELED."""
        from feather.jobs.rq import _rq_status_to_job_status
        from feather.jobs.base import JobStatus

        assert _rq_status_to_job_status("canceled") == JobStatus.CANCELED

    def test_stopped_status(self):
        """Converts 'stopped' to JobStatus.CANCELED."""
        from feather.jobs.rq import _rq_status_to_job_status
        from feather.jobs.base import JobStatus

        assert _rq_status_to_job_status("stopped") == JobStatus.CANCELED

    def test_unknown_status_defaults_to_queued(self):
        """Unknown status defaults to JobStatus.QUEUED."""
        from feather.jobs.rq import _rq_status_to_job_status
        from feather.jobs.base import JobStatus

        assert _rq_status_to_job_status("unknown_status") == JobStatus.QUEUED


class TestRQQueueClass:
    """Test RQQueue class structure and interface."""

    def test_inherits_from_job_queue(self):
        """RQQueue inherits from JobQueue."""
        from feather.jobs.rq import RQQueue
        from feather.jobs.base import JobQueue

        assert issubclass(RQQueue, JobQueue)

    def test_has_enqueue_method(self):
        """RQQueue has enqueue method."""
        from feather.jobs.rq import RQQueue

        assert hasattr(RQQueue, "enqueue")
        assert callable(getattr(RQQueue, "enqueue"))

    def test_has_get_job_method(self):
        """RQQueue has get_job method."""
        from feather.jobs.rq import RQQueue

        assert hasattr(RQQueue, "get_job")
        assert callable(getattr(RQQueue, "get_job"))

    def test_has_cancel_job_method(self):
        """RQQueue has cancel_job method."""
        from feather.jobs.rq import RQQueue

        assert hasattr(RQQueue, "cancel_job")
        assert callable(getattr(RQQueue, "cancel_job"))

    def test_has_get_queue_length_method(self):
        """RQQueue has get_queue_length method."""
        from feather.jobs.rq import RQQueue

        assert hasattr(RQQueue, "get_queue_length")
        assert callable(getattr(RQQueue, "get_queue_length"))

    def test_has_get_failed_jobs_method(self):
        """RQQueue has get_failed_jobs method."""
        from feather.jobs.rq import RQQueue

        assert hasattr(RQQueue, "get_failed_jobs")
        assert callable(getattr(RQQueue, "get_failed_jobs"))

    def test_has_retry_job_method(self):
        """RQQueue has retry_job method."""
        from feather.jobs.rq import RQQueue

        assert hasattr(RQQueue, "retry_job")
        assert callable(getattr(RQQueue, "retry_job"))

    def test_has_clear_queue_method(self):
        """RQQueue has clear_queue method."""
        from feather.jobs.rq import RQQueue

        assert hasattr(RQQueue, "clear_queue")
        assert callable(getattr(RQQueue, "clear_queue"))

    def test_has_redis_property(self):
        """RQQueue has redis property."""
        from feather.jobs.rq import RQQueue

        # Check that redis is defined as a property
        assert "redis" in dir(RQQueue)


class TestJobStatusEnum:
    """Test JobStatus enum values used by RQ backend."""

    def test_all_rq_statuses_mapped(self):
        """All RQ status strings have mappings."""
        from feather.jobs.rq import _rq_status_to_job_status
        from feather.jobs.base import JobStatus

        rq_statuses = [
            "queued",
            "started",
            "finished",
            "failed",
            "deferred",
            "scheduled",
            "canceled",
            "stopped",
        ]

        for status in rq_statuses:
            result = _rq_status_to_job_status(status)
            assert isinstance(result, JobStatus)


class TestJobResult:
    """Test JobResult used by RQ backend."""

    def test_job_result_is_finished_for_completed_statuses(self):
        """JobResult.is_finished returns True for completed statuses."""
        from feather.jobs.base import JobResult, JobStatus

        # FINISHED status
        result = JobResult(job_id="1", status=JobStatus.FINISHED)
        assert result.is_finished() is True

        # FAILED status
        result = JobResult(job_id="2", status=JobStatus.FAILED)
        assert result.is_finished() is True

        # CANCELED status
        result = JobResult(job_id="3", status=JobStatus.CANCELED)
        assert result.is_finished() is True

    def test_job_result_is_finished_false_for_pending(self):
        """JobResult.is_finished returns False for pending statuses."""
        from feather.jobs.base import JobResult, JobStatus

        result = JobResult(job_id="1", status=JobStatus.QUEUED)
        assert result.is_finished() is False

        result = JobResult(job_id="2", status=JobStatus.STARTED)
        assert result.is_finished() is False

    def test_job_result_is_successful(self):
        """JobResult.is_successful returns True only for FINISHED."""
        from feather.jobs.base import JobResult, JobStatus

        result = JobResult(job_id="1", status=JobStatus.FINISHED)
        assert result.is_successful() is True

        result = JobResult(job_id="2", status=JobStatus.FAILED)
        assert result.is_successful() is False

    def test_job_result_stores_error(self):
        """JobResult can store error information."""
        from feather.jobs.base import JobResult, JobStatus

        result = JobResult(
            job_id="1", status=JobStatus.FAILED, error="Connection timeout"
        )
        assert result.error == "Connection timeout"

    def test_job_result_stores_result(self):
        """JobResult can store return value."""
        from feather.jobs.base import JobResult, JobStatus

        result = JobResult(
            job_id="1", status=JobStatus.FINISHED, result={"data": "value"}
        )
        assert result.result == {"data": "value"}


class TestRQQueueWithMockedRedis:
    """Test RQQueue behavior with mocked Redis/RQ.

    These tests mock at the redis and rq module level since
    imports happen inside the RQQueue __init__ method.
    """

    def test_init_requires_rq_package(self):
        """RQQueue init raises ImportError if rq not installed."""
        import sys

        # Save original modules
        redis_mod = sys.modules.get("redis")
        rq_mod = sys.modules.get("rq")

        try:
            # Remove redis/rq from modules to simulate not installed
            sys.modules["redis"] = None
            sys.modules["rq"] = None

            # Clear the cached import in feather.jobs.rq
            if "feather.jobs.rq" in sys.modules:
                del sys.modules["feather.jobs.rq"]

            with pytest.raises(ImportError) as exc_info:
                from feather.jobs.rq import RQQueue

                RQQueue()

            assert "rq" in str(exc_info.value).lower()

        finally:
            # Restore modules
            if redis_mod is not None:
                sys.modules["redis"] = redis_mod
            elif "redis" in sys.modules:
                del sys.modules["redis"]

            if rq_mod is not None:
                sys.modules["rq"] = rq_mod
            elif "rq" in sys.modules:
                del sys.modules["rq"]

    def test_default_values(self):
        """RQQueue has expected default parameter values."""
        import inspect
        from feather.jobs.rq import RQQueue

        sig = inspect.signature(RQQueue.__init__)
        params = sig.parameters

        assert params["redis_url"].default == "redis://localhost:6379/0"
        assert params["default_queue"].default == "default"
        assert params["default_timeout"].default == 300
