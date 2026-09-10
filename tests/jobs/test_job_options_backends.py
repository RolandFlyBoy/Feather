"""@job retry/concurrency reach the backend (0.9.8).

Before 0.9.8 the decorator forwarded only ``job_timeout``, so
``@job(retry=3, concurrency=2)`` worked on the thread backend and was
silently ignored on RQ. retry is now honoured on RQ via ``rq.Retry``;
concurrency has no RQ equivalent and warns once per job at enqueue time.
"""

import warnings

import pytest

pytestmark = pytest.mark.jobs


class RecordingQueue:
    """Minimal JobQueue stand-in that records enqueue kwargs."""

    supports_concurrency = False

    def __init__(self):
        self.calls = []

    def enqueue(self, func, *args, **kwargs):
        from feather.jobs.base import JobResult, JobStatus

        self.calls.append((func, args, kwargs))
        return JobResult(job_id="recorded", status=JobStatus.QUEUED)

    def get_job(self, job_id):
        return None

    def cancel_job(self, job_id):
        return False


@pytest.fixture
def recording_queue():
    from feather.core.registry import reset_backends, set_backend

    queue = RecordingQueue()
    set_backend("queue", queue, app=None)
    yield queue
    reset_backends(None, "queue")


class TestDecoratorForwardsOptions:
    def test_retry_is_forwarded(self, recording_queue):
        from feather.jobs import job

        @job(retry=3)
        def with_retry():
            pass

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with_retry.enqueue()

        _func, _args, kwargs = recording_queue.calls[0]
        assert kwargs["retry"] == 3

    def test_timeout_is_still_forwarded(self, recording_queue):
        from feather.jobs import job

        @job(timeout=42)
        def with_timeout():
            pass

        with_timeout.enqueue()
        assert recording_queue.calls[0][2]["job_timeout"] == 42

    def test_concurrency_is_forwarded_when_supported(self, recording_queue):
        from feather.jobs import job

        recording_queue.supports_concurrency = True

        @job(concurrency=2)
        def with_concurrency():
            pass

        with_concurrency.enqueue()
        assert recording_queue.calls[0][2]["concurrency"] == 2

    def test_concurrency_warns_once_when_unsupported(self, recording_queue):
        from feather.jobs import job

        @job(concurrency=2)
        def unsupported_concurrency():
            pass

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            unsupported_concurrency.enqueue()
            unsupported_concurrency.enqueue()

        messages = [str(w.message) for w in caught if issubclass(w.category, RuntimeWarning)]
        assert len(messages) == 1, messages
        assert "concurrency" in messages[0]
        # And the option is not passed through to a backend that ignores it.
        assert "concurrency" not in recording_queue.calls[0][2]

    def test_unsupported_concurrency_does_not_fail_the_enqueue(self, recording_queue):
        from feather.jobs import job

        @job(concurrency=4)
        def still_runs():
            pass

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = still_runs.enqueue()
        assert result.job_id == "recorded"


class TestBackendCapabilityFlags:
    def test_thread_backend_supports_concurrency(self):
        from feather.jobs.thread import ThreadPoolQueue

        assert ThreadPoolQueue.supports_concurrency is True

    def test_sync_backend_supports_concurrency(self):
        """Sync runs one job at a time, so any limit is trivially satisfied."""
        from feather.jobs.sync import SyncQueue

        assert SyncQueue.supports_concurrency is True

    def test_rq_backend_does_not_support_concurrency(self):
        from feather.jobs.rq import RQQueue

        assert RQQueue.supports_concurrency is False

    def test_base_class_declares_the_flag(self):
        from feather.jobs.base import JobQueue

        assert hasattr(JobQueue, "supports_concurrency")


class TestRQRetry:
    """RQ honours retry through rq.Retry."""

    def test_enqueue_builds_an_rq_retry(self):
        pytest.importorskip("rq")
        from unittest.mock import MagicMock, patch

        from feather.jobs.rq import RQQueue

        with patch("redis.Redis.from_url"):
            queue = RQQueue(redis_url="redis://localhost:6379/0")

        fake_queue = MagicMock()
        fake_queue.enqueue.return_value = MagicMock(id="job-1")
        queue._queues["default"] = fake_queue

        queue.enqueue(len, [1, 2], retry=3)

        kwargs = fake_queue.enqueue.call_args.kwargs
        from rq import Retry

        assert isinstance(kwargs["retry"], Retry)
        assert kwargs["retry"].max == 3

    def test_concurrency_kwarg_is_dropped_not_passed_to_the_function(self):
        pytest.importorskip("rq")
        from unittest.mock import MagicMock, patch

        from feather.jobs.rq import RQQueue

        with patch("redis.Redis.from_url"):
            queue = RQQueue(redis_url="redis://localhost:6379/0")

        fake_queue = MagicMock()
        fake_queue.enqueue.return_value = MagicMock(id="job-2")
        queue._queues["default"] = fake_queue

        queue.enqueue(len, [1], concurrency=2)

        kwargs = fake_queue.enqueue.call_args.kwargs
        assert "concurrency" not in kwargs.get("kwargs", {})
