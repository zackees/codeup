"""
Tests for the running_process module.
"""

import unittest
from unittest.mock import MagicMock, patch

from codeup.running_process_adapter import (
    ProcessManager,
    run_command_with_streaming,
    run_command_with_timeout,
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


if __name__ == "__main__":
    unittest.main()
