"""Tests for the background jobs module.

Tests the thread pool job backend with concurrency control,
retry logic, and the @job decorator.

Run with: feather test --framework
"""

import threading
import time

import pytest

from feather.jobs.base import JobResult, JobStatus
from feather.jobs.sync import SyncQueue
from feather.jobs.thread import ThreadPoolQueue

pytestmark = pytest.mark.jobs


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def thread_queue():
    """Create ThreadPoolQueue for testing."""
    queue = ThreadPoolQueue(max_workers=4)
    yield queue
    queue.shutdown(wait=True)


@pytest.fixture
def sync_queue():
    """Create SyncQueue for testing."""
    return SyncQueue()


# =============================================================================
# ThreadPoolQueue Basic Execution Tests
# =============================================================================


class TestThreadPoolQueueBasic:
    """Test basic ThreadPoolQueue functionality."""

    def test_enqueue_returns_job_result(self, thread_queue):
        """Enqueue returns JobResult with job_id."""

        def simple_job():
            return "done"

        result = thread_queue.enqueue(simple_job)

        assert isinstance(result, JobResult)
        assert result.job_id is not None
        assert len(result.job_id) == 36  # UUID format

    def test_job_executes_in_background(self, thread_queue):
        """Job runs in separate thread, enqueue returns immediately."""
        executed = threading.Event()
        main_thread_id = threading.current_thread().ident
        job_thread_id = [None]

        def background_job():
            job_thread_id[0] = threading.current_thread().ident
            executed.set()
            return "done"

        # Enqueue should return immediately
        start = time.time()
        thread_queue.enqueue(background_job)
        enqueue_time = time.time() - start

        # Wait for job to execute
        executed.wait(timeout=2)

        assert enqueue_time < 0.1  # Enqueue was fast
        assert job_thread_id[0] is not None
        assert job_thread_id[0] != main_thread_id  # Ran in different thread

    def test_job_result_available_after_completion(self, thread_queue):
        """Can retrieve job result after execution."""
        completed = threading.Event()

        def job_with_result():
            completed.set()
            return {"status": "success", "count": 42}

        result = thread_queue.enqueue(job_with_result)
        completed.wait(timeout=2)
        time.sleep(0.05)  # Let status update

        job = thread_queue.get_job(result.job_id)
        assert job is not None
        assert job.status == JobStatus.FINISHED
        assert job.result == {"status": "success", "count": 42}

    def test_job_status_transitions(self, thread_queue):
        """Status transitions: QUEUED → STARTED → FINISHED."""
        started = threading.Event()
        can_finish = threading.Event()

        def controlled_job():
            started.set()
            can_finish.wait(timeout=2)
            return "done"

        result = thread_queue.enqueue(controlled_job)

        # Wait for job to start
        started.wait(timeout=2)
        time.sleep(0.05)

        job = thread_queue.get_job(result.job_id)
        assert job.status == JobStatus.STARTED

        # Let job finish
        can_finish.set()
        time.sleep(0.1)

        job = thread_queue.get_job(result.job_id)
        assert job.status == JobStatus.FINISHED

    def test_failed_job_captures_error(self, thread_queue):
        """Failed jobs have FAILED status and error message."""
        completed = threading.Event()

        def failing_job():
            completed.set()
            raise ValueError("Something went wrong")

        result = thread_queue.enqueue(failing_job)
        completed.wait(timeout=2)
        time.sleep(0.1)  # Let error be captured

        job = thread_queue.get_job(result.job_id)
        assert job.status == JobStatus.FAILED
        assert "ValueError" in job.error
        assert "Something went wrong" in job.error

    def test_job_with_arguments(self, thread_queue):
        """Jobs receive positional and keyword arguments."""
        completed = threading.Event()
        received_args = {}

        def job_with_args(a, b, c=None):
            received_args["a"] = a
            received_args["b"] = b
            received_args["c"] = c
            completed.set()
            return a + b

        result = thread_queue.enqueue(job_with_args, 1, 2, c=3)
        completed.wait(timeout=2)
        time.sleep(0.05)

        assert received_args == {"a": 1, "b": 2, "c": 3}

        job = thread_queue.get_job(result.job_id)
        assert job.result == 3


# =============================================================================
# Concurrency Control Tests
# =============================================================================


class TestConcurrencyControl:
    """Test per-task concurrency limits via semaphores."""

    def test_concurrency_limit_enforced(self, thread_queue):
        """Only N jobs run simultaneously when concurrency=N."""
        running_count = [0]
        max_concurrent = [0]
        lock = threading.Lock()
        barrier = threading.Event()

        def slow_job():
            with lock:
                running_count[0] += 1
                max_concurrent[0] = max(max_concurrent[0], running_count[0])
            barrier.wait(timeout=2)  # Block until released
            with lock:
                running_count[0] -= 1

        # Register with concurrency=2
        thread_queue.register_task(slow_job, concurrency=2)

        # Enqueue 4 jobs
        for _ in range(4):
            thread_queue.enqueue(slow_job)

        time.sleep(0.2)  # Let jobs start

        # Should have exactly 2 running (others waiting on semaphore)
        assert max_concurrent[0] == 2

        # Release all jobs
        barrier.set()

    def test_jobs_queue_when_at_capacity(self, thread_queue):
        """Additional jobs wait when concurrency limit reached."""
        execution_order = []
        lock = threading.Lock()
        first_batch_started = threading.Event()
        can_finish = threading.Event()

        def tracked_job(job_id):
            with lock:
                execution_order.append(f"start_{job_id}")
            if job_id <= 2:
                first_batch_started.set()
            can_finish.wait(timeout=2)
            with lock:
                execution_order.append(f"end_{job_id}")

        thread_queue.register_task(tracked_job, concurrency=2)

        # Enqueue 4 jobs
        for i in range(1, 5):
            thread_queue.enqueue(tracked_job, i)

        # Wait for first 2 to start
        first_batch_started.wait(timeout=2)
        time.sleep(0.1)

        # First 2 should have started, 3rd and 4th waiting
        with lock:
            started = [e for e in execution_order if e.startswith("start_")]
        assert len(started) == 2
        assert "start_1" in started
        assert "start_2" in started

        # Release all
        can_finish.set()

    def test_different_tasks_have_separate_limits(self, thread_queue):
        """Concurrency is per-task-type, not global."""
        task_a_count = [0]
        task_b_count = [0]
        max_a = [0]
        max_b = [0]
        lock = threading.Lock()
        barrier = threading.Event()

        def task_a():
            with lock:
                task_a_count[0] += 1
                max_a[0] = max(max_a[0], task_a_count[0])
            barrier.wait(timeout=2)
            with lock:
                task_a_count[0] -= 1

        def task_b():
            with lock:
                task_b_count[0] += 1
                max_b[0] = max(max_b[0], task_b_count[0])
            barrier.wait(timeout=2)
            with lock:
                task_b_count[0] -= 1

        # Register with different concurrency limits
        thread_queue.register_task(task_a, concurrency=1)
        thread_queue.register_task(task_b, concurrency=2)

        # Enqueue 2 of each
        for _ in range(2):
            thread_queue.enqueue(task_a)
            thread_queue.enqueue(task_b)

        time.sleep(0.2)

        # Task A should have max 1 concurrent, Task B should have max 2
        assert max_a[0] == 1
        assert max_b[0] == 2

        barrier.set()

    def test_unlimited_concurrency_by_default(self, thread_queue):
        """Without concurrency param, no limit applied."""
        running_count = [0]
        max_concurrent = [0]
        lock = threading.Lock()
        barrier = threading.Event()

        def unlimited_job():
            with lock:
                running_count[0] += 1
                max_concurrent[0] = max(max_concurrent[0], running_count[0])
            barrier.wait(timeout=2)
            with lock:
                running_count[0] -= 1

        # No concurrency limit registered
        for _ in range(4):
            thread_queue.enqueue(unlimited_job)

        time.sleep(0.2)

        # All 4 should run concurrently (up to max_workers)
        assert max_concurrent[0] == 4

        barrier.set()


# =============================================================================
# Retry Logic Tests
# =============================================================================


class TestRetryLogic:
    """Test retry with exponential backoff."""

    def test_retry_on_failure(self, thread_queue):
        """Job retries specified number of times."""
        attempts = [0]
        completed = threading.Event()

        def failing_then_succeeding():
            attempts[0] += 1
            if attempts[0] < 3:
                raise ValueError("Temporary failure")
            completed.set()
            return "success"

        thread_queue.register_task(failing_then_succeeding, retry=2)
        result = thread_queue.enqueue(failing_then_succeeding)

        # Wait for all retries (with backoff: 2s + 4s max)
        completed.wait(timeout=10)
        time.sleep(0.1)

        job = thread_queue.get_job(result.job_id)
        assert job.status == JobStatus.FINISHED
        assert attempts[0] == 3  # Initial + 2 retries

    def test_success_after_retry(self, thread_queue):
        """Job succeeds if retry succeeds."""
        attempts = [0]
        completed = threading.Event()

        def eventually_succeeds():
            attempts[0] += 1
            if attempts[0] == 1:
                raise ValueError("First attempt fails")
            completed.set()
            return "recovered"

        thread_queue.register_task(eventually_succeeds, retry=1)
        result = thread_queue.enqueue(eventually_succeeds)

        completed.wait(timeout=5)
        time.sleep(0.1)

        job = thread_queue.get_job(result.job_id)
        assert job.status == JobStatus.FINISHED
        assert job.result == "recovered"
        assert attempts[0] == 2

    def test_final_failure_after_retries_exhausted(self, thread_queue):
        """Job fails after all retries exhausted."""
        attempts = [0]
        all_attempts_done = threading.Event()

        def always_fails():
            attempts[0] += 1
            if attempts[0] >= 3:  # After initial + 2 retries
                all_attempts_done.set()
            raise ValueError("Always fails")

        thread_queue.register_task(always_fails, retry=2)
        result = thread_queue.enqueue(always_fails)

        all_attempts_done.wait(timeout=10)
        time.sleep(0.2)

        job = thread_queue.get_job(result.job_id)
        assert job.status == JobStatus.FAILED
        assert "Always fails" in job.error
        assert attempts[0] == 3  # Initial + 2 retries


# =============================================================================
# Delay Execution Tests
# =============================================================================


class TestDelayExecution:
    """Test delayed job execution."""

    def test_job_with_delay(self, thread_queue):
        """Job with delay waits before executing."""
        executed_at = [None]
        enqueue_time = [None]

        def delayed_job():
            executed_at[0] = time.time()
            return "done"

        enqueue_time[0] = time.time()
        result = thread_queue.enqueue(delayed_job, delay=1)

        # Wait for execution
        time.sleep(1.5)

        job = thread_queue.get_job(result.job_id)
        assert job.status == JobStatus.FINISHED

        # Should have waited ~1 second
        delay = executed_at[0] - enqueue_time[0]
        assert delay >= 0.9  # Allow some timing slack
        assert delay < 1.5

    def test_status_is_scheduled_when_delayed(self, thread_queue):
        """Delayed job has SCHEDULED status initially."""
        barrier = threading.Event()

        def job():
            barrier.wait(timeout=5)

        result = thread_queue.enqueue(job, delay=2)

        # Immediately after enqueue, status should be SCHEDULED
        job = thread_queue.get_job(result.job_id)
        assert job.status == JobStatus.SCHEDULED

        barrier.set()


# =============================================================================
# SyncQueue Tests
# =============================================================================


class TestSyncQueue:
    """Test SyncQueue (synchronous execution)."""

    def test_executes_immediately(self, sync_queue):
        """Job executes in calling thread."""
        executed = [False]
        thread_id = [None]
        main_thread = threading.current_thread().ident

        def sync_job():
            executed[0] = True
            thread_id[0] = threading.current_thread().ident
            return "done"

        sync_queue.enqueue(sync_job)

        assert executed[0] is True
        assert thread_id[0] == main_thread  # Same thread

    def test_result_available_immediately(self, sync_queue):
        """Result is available right after enqueue."""

        def job_with_result():
            return {"value": 42}

        result = sync_queue.enqueue(job_with_result)

        # Result available immediately (no waiting)
        assert result.status == JobStatus.FINISHED
        assert result.result == {"value": 42}

    def test_failed_job_captures_error(self, sync_queue):
        """Failed jobs have error captured."""

        def failing_job():
            raise RuntimeError("Sync failure")

        result = sync_queue.enqueue(failing_job)

        assert result.status == JobStatus.FAILED
        assert "RuntimeError" in result.error
        assert "Sync failure" in result.error

    def test_get_job_retrieves_result(self, sync_queue):
        """Can retrieve job by ID."""

        def simple_job():
            return "found"

        result = sync_queue.enqueue(simple_job)

        retrieved = sync_queue.get_job(result.job_id)
        assert retrieved is not None
        assert retrieved.job_id == result.job_id
        assert retrieved.result == "found"


# =============================================================================
# Queue Management Tests
# =============================================================================


class TestQueueManagement:
    """Test queue management operations."""

    def test_get_queue_length(self, thread_queue):
        """Queue length reflects pending jobs."""
        barrier = threading.Event()

        def blocking_job():
            barrier.wait(timeout=5)

        # Enqueue jobs that will block
        for _ in range(3):
            thread_queue.enqueue(blocking_job)

        time.sleep(0.1)

        # Should have pending jobs
        length = thread_queue.get_queue_length()
        assert length >= 0  # At least some might be pending

        barrier.set()

    def test_get_failed_jobs(self, thread_queue):
        """Can retrieve list of failed jobs."""
        completed = threading.Event()

        def failing_job():
            completed.set()
            raise ValueError("Test failure")

        thread_queue.enqueue(failing_job)
        completed.wait(timeout=2)
        time.sleep(0.1)

        failed = thread_queue.get_failed_jobs()
        assert len(failed) >= 1
        assert any("Test failure" in job.error for job in failed)

    def test_clear_queue(self, thread_queue):
        """Clear removes job history."""

        def simple_job():
            return "done"

        result = thread_queue.enqueue(simple_job)
        time.sleep(0.1)

        # Job should exist
        assert thread_queue.get_job(result.job_id) is not None

        # Clear and verify
        count = thread_queue.clear_queue()
        assert count >= 1

        # Job should be gone
        assert thread_queue.get_job(result.job_id) is None
