"""Regression tests for 0.9.6 job backend fixes.

Covers:
- @job(...).enqueue() on the sync and thread backends (framework kwargs must
  not leak into the user function).
- Thread backend timeout not blocking on the running job.
- Cancellation of delayed/queued jobs.
- enqueue_at() with timezone-aware datetimes.
"""

import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

import feather.jobs as jobs_module
from feather.jobs import job
from feather.jobs.base import JobStatus
from feather.jobs.sync import SyncQueue
from feather.jobs.thread import ThreadPoolQueue

pytestmark = pytest.mark.jobs


@contextmanager
def use_queue(queue):
    """Force feather.jobs.get_queue() to return the given queue."""
    previous = jobs_module._queue_instance
    jobs_module._queue_instance = queue
    try:
        yield queue
    finally:
        jobs_module._queue_instance = previous


def _wait_for(predicate, timeout=2.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


# =============================================================================
# @job decorator + enqueue() on each backend
# =============================================================================


class TestJobDecoratorEnqueue:
    """The @job decorator must work with the default (sync) backend."""

    def test_sync_backend_accepts_framework_kwargs(self):
        """f.enqueue(3) must not pass job_timeout/delay into the function."""

        @job(timeout=5)
        def double(value):
            return value * 2

        with use_queue(SyncQueue()):
            result = double.enqueue(3)

        assert result.status == JobStatus.FINISHED, result.error
        assert result.result == 6

    def test_sync_backend_accepts_keyword_arguments(self):
        """User keyword arguments still reach the function."""

        @job
        def greet(name="world"):
            return f"hello {name}"

        with use_queue(SyncQueue()):
            result = greet.enqueue(name="feather")

        assert result.status == JobStatus.FINISHED, result.error
        assert result.result == "hello feather"

    def test_sync_queue_ignores_framework_kwargs_directly(self):
        """SyncQueue.enqueue swallows framework kwargs it does not use."""

        def noop():
            return "ok"

        queue = SyncQueue()
        result = queue.enqueue(noop, job_timeout=10, retry=2, concurrency=1)

        assert result.status == JobStatus.FINISHED, result.error
        assert result.result == "ok"

    def test_thread_backend_accepts_framework_kwargs(self):
        """The thread backend strips framework kwargs too."""

        @job(timeout=5)
        def triple(value):
            return value * 3

        queue = ThreadPoolQueue(max_workers=2)
        try:
            with use_queue(queue):
                result = triple.enqueue(3)
                assert _wait_for(
                    lambda: queue.get_job(result.job_id).status == JobStatus.FINISHED
                ), queue.get_job(result.job_id).error
                assert queue.get_job(result.job_id).result == 9
        finally:
            queue.shutdown(wait=False)


# =============================================================================
# Timeout handling
# =============================================================================


class TestThreadTimeout:
    def test_timeout_marks_job_without_waiting_for_it(self):
        """A timed-out job is marked TIMEOUT promptly, not after it finishes."""
        queue = ThreadPoolQueue(max_workers=2)
        try:
            def slow_job():
                time.sleep(5)
                return "too late"

            start = time.time()
            result = queue.enqueue(slow_job, timeout=0.2)

            assert _wait_for(
                lambda: queue.get_job(result.job_id).status == JobStatus.TIMEOUT,
                timeout=1.5,
            ), queue.get_job(result.job_id).status
            assert time.time() - start < 1.5
        finally:
            queue.shutdown(wait=False)

    def test_timeout_does_not_block_the_worker_slot(self):
        """After a timeout the pool worker is released for the next job."""
        queue = ThreadPoolQueue(max_workers=1)
        try:
            def slow_job():
                time.sleep(5)

            def quick_job():
                return "done"

            queue.enqueue(slow_job, timeout=0.2)
            follow_up = queue.enqueue(quick_job)

            assert _wait_for(
                lambda: queue.get_job(follow_up.job_id).status == JobStatus.FINISHED,
                timeout=1.5,
            ), queue.get_job(follow_up.job_id).status
        finally:
            queue.shutdown(wait=False)


# =============================================================================
# Cancellation
# =============================================================================


class TestCancellation:
    def test_delayed_job_can_be_canceled(self):
        """A delayed job stays cancelable and never executes once canceled."""
        queue = ThreadPoolQueue(max_workers=2)
        try:
            executed = threading.Event()

            def delayed_job():
                executed.set()

            result = queue.enqueue(delayed_job, delay=0.4)
            assert queue.cancel_job(result.job_id) is True

            time.sleep(0.8)
            assert not executed.is_set()
            assert queue.get_job(result.job_id).status == JobStatus.CANCELED
        finally:
            queue.shutdown(wait=False)

    def test_job_waiting_on_semaphore_stays_queued_and_cancelable(self):
        """A job waiting for a concurrency slot is still QUEUED."""
        queue = ThreadPoolQueue(max_workers=4)
        try:
            release = threading.Event()
            ran_second = threading.Event()

            def blocking_job(first):
                if first:
                    release.wait(timeout=2)
                else:
                    ran_second.set()

            queue.register_task(blocking_job, concurrency=1)

            first = queue.enqueue(blocking_job, True)
            assert _wait_for(
                lambda: queue.get_job(first.job_id).status == JobStatus.STARTED
            )

            second = queue.enqueue(blocking_job, False)
            time.sleep(0.1)
            assert queue.get_job(second.job_id).status == JobStatus.QUEUED
            assert queue.cancel_job(second.job_id) is True

            release.set()
            time.sleep(0.3)
            assert not ran_second.is_set()
            assert queue.get_job(second.job_id).status == JobStatus.CANCELED
        finally:
            queue.shutdown(wait=False)


# =============================================================================
# enqueue_at with timezone-aware datetimes
# =============================================================================


class TestEnqueueAt:
    def test_enqueue_at_accepts_aware_datetime(self):
        """A timezone-aware scheduled time must not raise."""
        queue = ThreadPoolQueue(max_workers=2)
        try:
            ran = threading.Event()

            def scheduled_job():
                ran.set()

            when = datetime.now(timezone.utc) + timedelta(seconds=0.2)
            result = queue.enqueue_at(scheduled_job, when)

            assert result.job_id
            assert _wait_for(ran.is_set, timeout=1.5)
        finally:
            queue.shutdown(wait=False)

    def test_enqueue_at_accepts_naive_datetime(self):
        """Naive datetimes keep working (backwards compatible)."""
        queue = ThreadPoolQueue(max_workers=2)
        try:
            ran = threading.Event()

            def scheduled_job():
                ran.set()

            when = datetime.now() + timedelta(seconds=0.2)
            queue.enqueue_at(scheduled_job, when)

            assert _wait_for(ran.is_set, timeout=1.5)
        finally:
            queue.shutdown(wait=False)

    def test_enqueue_at_in_the_past_runs_immediately(self):
        """A past scheduled time clamps the delay to zero."""
        queue = ThreadPoolQueue(max_workers=2)
        try:
            ran = threading.Event()

            def scheduled_job():
                ran.set()

            queue.enqueue_at(scheduled_job, datetime.now(timezone.utc) - timedelta(hours=1))
            assert _wait_for(ran.is_set, timeout=1.5)
        finally:
            queue.shutdown(wait=False)
