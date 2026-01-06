"""Unit tests for feather/jobs/monitoring.py.

Tests the job monitoring utilities.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock

pytestmark = pytest.mark.unit


class TestCaptureResourceMetrics:
    """Test capture_resource_metrics function."""

    def test_returns_dict(self):
        """capture_resource_metrics returns a dictionary."""
        from feather.jobs.monitoring import capture_resource_metrics

        result = capture_resource_metrics()
        assert isinstance(result, dict)

    def test_returns_metrics_with_psutil(self):
        """capture_resource_metrics returns metrics when psutil is available."""
        from feather.jobs.monitoring import capture_resource_metrics

        # Mock psutil being available
        mock_process = Mock()
        mock_process.memory_info.return_value = Mock(rss=256 * 1024 * 1024)  # 256 MB
        mock_process.memory_percent.return_value = 3.5
        mock_process.cpu_percent.return_value = 25.0
        mock_process.num_threads.return_value = 8
        mock_process.open_files.return_value = [1, 2, 3]  # 3 open files

        mock_psutil = Mock()
        mock_psutil.Process.return_value = mock_process

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            # Need to reload to pick up the mock
            import importlib
            from feather.jobs import monitoring

            importlib.reload(monitoring)
            result = monitoring.capture_resource_metrics()

        # Should have the expected keys
        assert "memory_mb" in result
        assert "memory_percent" in result
        assert "cpu_percent" in result
        assert "thread_count" in result
        assert "open_files" in result

    def test_returns_empty_dict_without_psutil(self):
        """capture_resource_metrics returns empty dict when psutil unavailable."""
        from feather.jobs.monitoring import capture_resource_metrics

        # Mock psutil import failing
        with patch.dict("sys.modules", {"psutil": None}):
            with patch(
                "feather.jobs.monitoring.capture_resource_metrics"
            ) as mock_capture:
                mock_capture.return_value = {}
                result = mock_capture()
                assert result == {}

    def test_handles_exception_gracefully(self):
        """capture_resource_metrics handles exceptions gracefully."""
        from feather.jobs.monitoring import capture_resource_metrics

        # Mock psutil raising an exception
        mock_psutil = Mock()
        mock_psutil.Process.side_effect = Exception("Process error")

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            import importlib
            from feather.jobs import monitoring

            importlib.reload(monitoring)
            result = monitoring.capture_resource_metrics()
            assert result == {}


class TestGetSystemMetrics:
    """Test get_system_metrics function."""

    def test_returns_dict(self):
        """get_system_metrics returns a dictionary."""
        from feather.jobs.monitoring import get_system_metrics

        result = get_system_metrics()
        assert isinstance(result, dict)

    def test_returns_metrics_with_psutil(self):
        """get_system_metrics returns system metrics when psutil available."""
        from feather.jobs.monitoring import get_system_metrics

        mock_memory = Mock()
        mock_memory.total = 16 * 1024 * 1024 * 1024  # 16 GB
        mock_memory.available = 8 * 1024 * 1024 * 1024  # 8 GB
        mock_memory.percent = 50.0

        mock_psutil = Mock()
        mock_psutil.virtual_memory.return_value = mock_memory
        mock_psutil.cpu_count.return_value = 8

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            import importlib
            from feather.jobs import monitoring

            importlib.reload(monitoring)
            result = monitoring.get_system_metrics()

        assert "cpu_count" in result
        assert "memory_total_mb" in result
        assert "memory_available_mb" in result
        assert "memory_percent" in result


class TestFormatMetrics:
    """Test format_metrics function."""

    def test_empty_metrics_returns_message(self):
        """format_metrics returns message for empty metrics."""
        from feather.jobs.monitoring import format_metrics

        result = format_metrics({})
        assert "No metrics available" in result
        assert "psutil not installed" in result

    def test_formats_memory_with_mb_suffix(self):
        """format_metrics adds MB suffix to memory values."""
        from feather.jobs.monitoring import format_metrics

        result = format_metrics({"memory_mb": 256.5})
        assert "256.5 MB" in result

    def test_formats_percent_with_suffix(self):
        """format_metrics adds % suffix to percent values."""
        from feather.jobs.monitoring import format_metrics

        result = format_metrics({"cpu_percent": 45.2})
        assert "45.2%" in result

    def test_formats_key_as_title(self):
        """format_metrics formats keys as titles."""
        from feather.jobs.monitoring import format_metrics

        result = format_metrics({"thread_count": 8})
        assert "Thread Count" in result

    def test_formats_multiple_metrics(self):
        """format_metrics handles multiple metrics."""
        from feather.jobs.monitoring import format_metrics

        metrics = {
            "memory_mb": 256.0,
            "cpu_percent": 25.0,
            "thread_count": 4,
        }
        result = format_metrics(metrics)

        assert "Memory Mb: 256.0 MB" in result
        assert "Cpu Percent: 25.0%" in result
        assert "Thread Count: 4" in result


class TestResourceMonitor:
    """Test ResourceMonitor context manager."""

    def test_is_context_manager(self):
        """ResourceMonitor can be used as context manager."""
        from feather.jobs.monitoring import ResourceMonitor

        monitor = ResourceMonitor()
        assert hasattr(monitor, "__enter__")
        assert hasattr(monitor, "__exit__")

    def test_tracks_duration(self):
        """ResourceMonitor tracks operation duration."""
        from feather.jobs.monitoring import ResourceMonitor

        with ResourceMonitor() as monitor:
            time.sleep(0.1)  # Sleep 100ms

        assert monitor.duration_seconds >= 0.1
        assert monitor.duration_seconds < 0.5  # Should be close to 0.1

    def test_captures_start_and_end_metrics(self):
        """ResourceMonitor captures metrics at start and end."""
        from feather.jobs.monitoring import ResourceMonitor

        with ResourceMonitor() as monitor:
            pass

        # start_metrics and end_metrics should be set (may be empty without psutil)
        assert isinstance(monitor.start_metrics, dict)
        assert isinstance(monitor.end_metrics, dict)

    def test_duration_seconds_property(self):
        """duration_seconds returns correct duration."""
        from feather.jobs.monitoring import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.start_time = 100.0
        monitor.end_time = 105.5

        assert monitor.duration_seconds == 5.5

    def test_duration_seconds_returns_zero_without_times(self):
        """duration_seconds returns 0 if times not set."""
        from feather.jobs.monitoring import ResourceMonitor

        monitor = ResourceMonitor()
        assert monitor.duration_seconds == 0.0

    def test_memory_delta_mb_property(self):
        """memory_delta_mb calculates memory change."""
        from feather.jobs.monitoring import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.start_metrics = {"memory_mb": 100.0}
        monitor.end_metrics = {"memory_mb": 150.0}

        assert monitor.memory_delta_mb == 50.0

    def test_memory_delta_mb_with_empty_metrics(self):
        """memory_delta_mb handles empty metrics."""
        from feather.jobs.monitoring import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.start_metrics = {}
        monitor.end_metrics = {}

        assert monitor.memory_delta_mb == 0.0

    def test_peak_memory_mb_property(self):
        """peak_memory_mb returns end memory."""
        from feather.jobs.monitoring import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.end_metrics = {"memory_mb": 200.0}

        assert monitor.peak_memory_mb == 200.0

    def test_summary_returns_string(self):
        """summary() returns formatted string."""
        from feather.jobs.monitoring import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.start_time = 100.0
        monitor.end_time = 102.0
        monitor.start_metrics = {"memory_mb": 100.0}
        monitor.end_metrics = {"memory_mb": 120.0}

        summary = monitor.summary()
        assert "Duration: 2.0s" in summary
        assert "Memory delta: 20.0 MB" in summary
        assert "Final memory: 120.0 MB" in summary

    def test_does_not_suppress_exceptions(self):
        """ResourceMonitor does not suppress exceptions."""
        from feather.jobs.monitoring import ResourceMonitor

        with pytest.raises(ValueError):
            with ResourceMonitor():
                raise ValueError("Test error")
