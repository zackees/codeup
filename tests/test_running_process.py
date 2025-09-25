"""
Tests for the running_process module.
"""

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from codeup.running_process_adapter import (
    ProcessManager,
    _update_activity_time,
    run_command_with_streaming,
    run_command_with_streaming_and_capture,
    run_command_with_timeout,
    set_activity_tracker,
)


class RunningProcessTester(unittest.TestCase):
    """Test cases for running_process module functionality."""

    @patch("codeup.running_process_adapter.RunningProcess")
    def test_run_command_with_streaming_success(self, mock_popen):
        """Test successful command execution with streaming."""
        mock_process = MagicMock()
        mock_process.returncode = 0  # Set as actual integer, not MagicMock
        mock_process.line_iter.return_value = iter(["output"])
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process

        exit_code = run_command_with_streaming(["echo", "test"])
        self.assertEqual(exit_code, 0)
        mock_popen.assert_called_once()

    @patch("codeup.running_process_adapter.RunningProcess")
    def test_run_command_with_streaming_file_not_found(self, mock_popen):
        """Test command not found error handling."""
        mock_popen.side_effect = FileNotFoundError("Command not found")

        exit_code = run_command_with_streaming(["nonexistent_command"])
        self.assertEqual(exit_code, 127)

    @patch("codeup.running_process_adapter.RunningProcess")
    def test_run_command_with_timeout_success(self, mock_popen):
        """Test successful command execution with timeout."""
        mock_process = MagicMock()
        mock_process.returncode = 0  # Set as actual integer, not MagicMock
        mock_process.line_iter.return_value = iter(["output"])
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process

        # Test with a very short timeout but the process should complete quickly
        exit_code = run_command_with_timeout(["echo", "test"], timeout=10)
        self.assertEqual(exit_code, 0)

    def test_process_manager_context(self):
        """Test ProcessManager context manager functionality."""
        with patch("codeup.running_process_adapter.RunningProcess") as mock_popen:
            mock_process = MagicMock()
            mock_process.finished = False  # Set as actual boolean, not MagicMock
            mock_popen.return_value = mock_process

            with ProcessManager(["echo", "test"]) as pm:
                self.assertIsNotNone(pm.process)
                self.assertTrue(pm.is_running())

            # Process should be terminated when exiting context
            mock_process.terminate.assert_called_once()

    def test_process_manager_run(self):
        """Test ProcessManager run method."""
        with patch("codeup.running_process_adapter.RunningProcess") as mock_popen:
            mock_process = MagicMock()
            mock_process.finished = False  # Set as actual boolean
            mock_process.returncode = 0  # Set as actual integer
            mock_process.wait.return_value = None
            mock_popen.return_value = mock_process

            with ProcessManager(["echo", "test"]) as pm:
                exit_code = pm.run()
                self.assertEqual(exit_code, 0)
                self.assertEqual(pm.exit_code, 0)

    def test_process_manager_terminate_and_kill(self):
        """Test ProcessManager terminate and kill methods."""
        with patch("codeup.running_process_adapter.RunningProcess") as mock_popen:
            mock_process = MagicMock()
            mock_process.finished = False  # Set as actual boolean
            mock_popen.return_value = mock_process

            pm = ProcessManager(["echo", "test"])
            pm.__enter__()

            # Test terminate
            pm.terminate()
            mock_process.terminate.assert_called_once()

            # Test kill
            pm.kill()
            mock_process.kill.assert_called_once()

            pm.__exit__(None, None, None)


class TestTimeoutBehavior(unittest.TestCase):
    """Test cases for timeout behavior with activity tracking."""

    def setUp(self):
        """Set up test fixtures."""
        self.original_tracker = None
        # Reset any existing activity tracker
        set_activity_tracker(None)

    def tearDown(self):
        """Clean up after tests."""
        # Restore original tracker if any
        set_activity_tracker(self.original_tracker)

    def test_activity_tracker_setup(self):
        """Test that activity tracker can be set and functions properly."""
        # Create a mock activity tracker
        activity_time = [time.time()]

        # Set the activity tracker
        set_activity_tracker(activity_time)

        # Record initial time
        initial_time = activity_time[0]

        # Wait a small amount to ensure time difference
        time.sleep(0.01)

        # Update activity time
        _update_activity_time()

        # Verify time was updated
        self.assertGreater(activity_time[0], initial_time)

    def test_activity_tracker_none_handling(self):
        """Test that update_activity_time handles None tracker gracefully."""
        # Set tracker to None
        set_activity_tracker(None)

        # This should not raise an exception
        try:
            _update_activity_time()
        except Exception as e:
            self.fail(
                f"_update_activity_time raised an exception with None tracker: {e}"
            )

    @patch("codeup.running_process_adapter.RunningProcess")
    def test_streaming_updates_activity(self, mock_popen):
        """Test that streaming output updates activity tracker."""
        # Set up activity tracker
        activity_time = [time.time() - 10]  # Set to 10 seconds ago
        set_activity_tracker(activity_time)
        initial_time = activity_time[0]

        # Mock the process
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.line_iter.return_value = iter(["line1", "line2", "line3"])
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process

        # Run the command
        exit_code = run_command_with_streaming(["echo", "test"])

        # Verify activity time was updated
        self.assertGreater(activity_time[0], initial_time)
        self.assertEqual(exit_code, 0)

    @patch("codeup.running_process_adapter.RunningProcess")
    def test_streaming_and_capture_updates_activity(self, mock_popen):
        """Test that streaming and capture updates activity tracker."""
        # Set up activity tracker
        activity_time = [time.time() - 10]  # Set to 10 seconds ago
        set_activity_tracker(activity_time)
        initial_time = activity_time[0]

        # Mock the process
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.line_iter.return_value = iter(["output line 1", "output line 2"])
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process

        # Run the command with capture
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["echo", "test"], capture_output=True, quiet=True
        )

        # Verify activity time was updated
        self.assertGreater(activity_time[0], initial_time)
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "output line 1\noutput line 2")

    def test_timeout_logic_simulation(self):
        """Test the timeout logic similar to main.py implementation."""
        # Simulate the timeout handler logic
        last_activity_time = [time.time()]

        # Simulate the timeout check (like in main.py)
        def simulate_timeout_check():
            current_time = time.time()
            time_since_last_activity = current_time - last_activity_time[0]
            return time_since_last_activity >= 300  # 5 minutes

        # Initially should not timeout (just created)
        self.assertFalse(simulate_timeout_check())

        # Set activity time to 6 minutes ago
        last_activity_time[0] = time.time() - 360  # 6 minutes ago

        # Now should trigger timeout
        self.assertTrue(simulate_timeout_check())

        # Reset activity (simulate receiving output)
        last_activity_time[0] = time.time()

        # Should not timeout again
        self.assertFalse(simulate_timeout_check())

    @patch("codeup.running_process_adapter.RunningProcess")
    def test_no_output_no_activity_update(self, mock_popen):
        """Test that processes with no output don't update activity."""
        # Set up activity tracker
        activity_time = [time.time() - 10]  # Set to 10 seconds ago
        set_activity_tracker(activity_time)
        initial_time = activity_time[0]

        # Mock process with no output
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.line_iter.return_value = iter([])  # No output lines
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process

        # Run the command
        exit_code = run_command_with_streaming(["echo", ""])

        # Verify activity time was NOT updated (no output lines)
        self.assertEqual(activity_time[0], initial_time)
        self.assertEqual(exit_code, 0)

    @patch("codeup.running_process_adapter.RunningProcess")
    def test_exception_during_streaming_preserves_behavior(self, mock_popen):
        """Test that exceptions during streaming don't break activity tracking."""
        # Set up activity tracker
        activity_time = [time.time() - 10]
        set_activity_tracker(activity_time)
        initial_time = activity_time[0]

        # Mock process that throws exception during line iteration
        mock_process = MagicMock()
        mock_process.returncode = 0

        # Create an iterator that yields some lines then raises an exception
        def problematic_iter():
            yield "line1"
            yield "line2"
            raise RuntimeError("Simulated streaming error")

        mock_process.line_iter.return_value = problematic_iter()
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process

        # Run the command - should not crash
        exit_code = run_command_with_streaming(["echo", "test"])

        # Verify activity time was updated (from the lines before exception)
        self.assertGreater(activity_time[0], initial_time)
        self.assertEqual(exit_code, 0)

    def test_concurrent_activity_updates(self):
        """Test that concurrent activity updates work correctly."""
        activity_time = [time.time() - 100]  # Start 100 seconds ago
        set_activity_tracker(activity_time)

        # Function to simulate multiple threads updating activity
        def update_activity():
            for _ in range(5):
                _update_activity_time()
                time.sleep(0.01)  # Small delay

        # Start multiple threads
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=update_activity)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify activity time was updated (should be recent)
        time_diff = time.time() - activity_time[0]
        self.assertLess(time_diff, 1.0)  # Should be within 1 second


if __name__ == "__main__":
    unittest.main()
