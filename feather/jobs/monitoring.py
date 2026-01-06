"""
Job Monitoring Utilities
========================

Optional resource monitoring for job execution.

Provides memory and CPU tracking for debugging job failures,
especially useful for resource-intensive tasks like ML inference.

Requirements
------------
Install psutil for full functionality::

    pip install psutil

Without psutil, monitoring functions return empty data gracefully.

Usage
-----
::

    from feather.jobs.monitoring import capture_resource_metrics

    # Before heavy operation
    before = capture_resource_metrics()

    # Do heavy work...

    # After (or on failure)
    after = capture_resource_metrics()
    print(f"Memory usage: {after.get('memory_mb', 'N/A')} MB")
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def capture_resource_metrics() -> Dict[str, Any]:
    """Capture current process resource metrics.

    Returns memory usage, CPU percentage, and thread count
    for the current process. Useful for crash analysis.

    Returns:
        Dict with resource metrics, or empty dict if psutil unavailable.

    Example::

        metrics = capture_resource_metrics()
        # {
        #     'memory_mb': 256.5,
        #     'memory_percent': 3.2,
        #     'cpu_percent': 45.0,
        #     'thread_count': 8,
        #     'open_files': 24
        # }
    """
    try:
        import psutil

        process = psutil.Process()

        # Get memory info
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / (1024 * 1024)
        memory_percent = process.memory_percent()

        # Get CPU (may need a short interval for accuracy)
        cpu_percent = process.cpu_percent(interval=0.1)

        # Get thread and file counts
        thread_count = process.num_threads()

        try:
            open_files = len(process.open_files())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            open_files = -1

        return {
            "memory_mb": round(memory_mb, 2),
            "memory_percent": round(memory_percent, 2),
            "cpu_percent": round(cpu_percent, 2),
            "thread_count": thread_count,
            "open_files": open_files,
        }

    except ImportError:
        logger.debug("psutil not installed, resource monitoring unavailable")
        return {}
    except Exception as e:
        logger.warning(f"Failed to capture resource metrics: {e}")
        return {}


def get_system_metrics() -> Dict[str, Any]:
    """Get system-wide resource metrics.

    Returns:
        Dict with system metrics, or empty dict if unavailable.

    Example::

        system = get_system_metrics()
        # {
        #     'cpu_count': 8,
        #     'memory_total_mb': 16384,
        #     'memory_available_mb': 8192,
        #     'memory_percent': 50.0
        # }
    """
    try:
        import psutil

        memory = psutil.virtual_memory()

        return {
            "cpu_count": psutil.cpu_count(),
            "memory_total_mb": round(memory.total / (1024 * 1024), 2),
            "memory_available_mb": round(memory.available / (1024 * 1024), 2),
            "memory_percent": round(memory.percent, 2),
        }

    except ImportError:
        return {}
    except Exception as e:
        logger.warning(f"Failed to capture system metrics: {e}")
        return {}


def format_metrics(metrics: Dict[str, Any]) -> str:
    """Format metrics dict as human-readable string.

    Args:
        metrics: Dict from capture_resource_metrics or get_system_metrics.

    Returns:
        Formatted multi-line string.
    """
    if not metrics:
        return "No metrics available (psutil not installed)"

    lines = []
    for key, value in metrics.items():
        # Format key nicely
        label = key.replace("_", " ").title()

        # Format value with units
        if "mb" in key.lower():
            lines.append(f"{label}: {value} MB")
        elif "percent" in key.lower():
            lines.append(f"{label}: {value}%")
        else:
            lines.append(f"{label}: {value}")

    return "\n".join(lines)


class ResourceMonitor:
    """Context manager for monitoring resource usage during an operation.

    Example::

        with ResourceMonitor() as monitor:
            # Heavy operation
            process_video(video_id)

        print(f"Peak memory: {monitor.peak_memory_mb} MB")
        print(f"Duration: {monitor.duration_seconds}s")
    """

    def __init__(self):
        self.start_metrics: Dict[str, Any] = {}
        self.end_metrics: Dict[str, Any] = {}
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def __enter__(self) -> "ResourceMonitor":
        import time

        self.start_time = time.time()
        self.start_metrics = capture_resource_metrics()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import time

        self.end_time = time.time()
        self.end_metrics = capture_resource_metrics()
        return False  # Don't suppress exceptions

    @property
    def duration_seconds(self) -> float:
        """Duration of the monitored operation in seconds."""
        if self.start_time and self.end_time:
            return round(self.end_time - self.start_time, 2)
        return 0.0

    @property
    def memory_delta_mb(self) -> float:
        """Change in memory usage during operation (MB)."""
        start = self.start_metrics.get("memory_mb", 0)
        end = self.end_metrics.get("memory_mb", 0)
        return round(end - start, 2)

    @property
    def peak_memory_mb(self) -> float:
        """Peak memory observed (approximated as end memory)."""
        return self.end_metrics.get("memory_mb", 0)

    def summary(self) -> str:
        """Get a summary of the monitored operation."""
        return (
            f"Duration: {self.duration_seconds}s, "
            f"Memory delta: {self.memory_delta_mb} MB, "
            f"Final memory: {self.peak_memory_mb} MB"
        )
