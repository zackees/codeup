"""
Tests for the running_process module.
"""

import unittest
from unittest.mock import MagicMock, patch

from codeup.running_process import (
    ProcessManager,
    run_command_with_streaming,
    run_command_with_timeout,
    stream_process_output,
)


class RunningProcessTester(unittest.TestCase):
    """Test cases for running_process module functionality."""

    def test_stream_process_output_success(self):
        """Test that stream_process_output handles successful processes."""
        # Create a mock process that succeeds
        mock_process = MagicMock()
        mock_process.poll.side_effect = [None, None, 0]  # Running, then finished
        mock_process.stdout.readline.side_effect = ["test output\n", ""]
        mock_process.stderr.readline.side_effect = ["", ""]
        mock_process.stdout.__iter__.return_value = []
        mock_process.stderr.__iter__.return_value = []
        mock_process.wait.return_value = 0

        exit_code = stream_process_output(mock_process)
        self.assertEqual(exit_code, 0)

    def test_stream_process_output_keyboard_interrupt(self):
        """Test that stream_process_output handles KeyboardInterrupt."""
        mock_process = MagicMock()
        mock_process.poll.side_effect = KeyboardInterrupt()

        exit_code = stream_process_output(mock_process)
        self.assertEqual(exit_code, 130)
        mock_process.terminate.assert_called_once()

    @patch("codeup.running_process.subprocess.Popen")
    def test_run_command_with_streaming_success(self, mock_popen):
        """Test successful command execution with streaming."""
        mock_process = MagicMock()
        mock_process.poll.side_effect = [None, 0]
        mock_process.stdout.readline.side_effect = ["output\n", ""]
        mock_process.stderr.readline.side_effect = [""]
        mock_process.stdout.__iter__.return_value = []
        mock_process.stderr.__iter__.return_value = []
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        exit_code = run_command_with_streaming(["echo", "test"])
        self.assertEqual(exit_code, 0)
        mock_popen.assert_called_once()

    @patch("codeup.running_process.subprocess.Popen")
    def test_run_command_with_streaming_file_not_found(self, mock_popen):
        """Test command not found error handling."""
        mock_popen.side_effect = FileNotFoundError("Command not found")

        exit_code = run_command_with_streaming(["nonexistent_command"])
        self.assertEqual(exit_code, 127)

    @patch("codeup.running_process.subprocess.Popen")
    def test_run_command_with_timeout_success(self, mock_popen):
        """Test successful command execution with timeout."""
        mock_process = MagicMock()
        mock_process.poll.side_effect = [None, 0]
        mock_process.stdout.readline.side_effect = ["output\n", ""]
        mock_process.stderr.readline.side_effect = [""]
        mock_process.stdout.__iter__.return_value = []
        mock_process.stderr.__iter__.return_value = []
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        # Test with a very short timeout but the process should complete quickly
        exit_code = run_command_with_timeout(["echo", "test"], timeout=10.0)
        self.assertEqual(exit_code, 0)

    def test_process_manager_context(self):
        """Test ProcessManager context manager functionality."""
        with patch("codeup.running_process.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            with ProcessManager(["echo", "test"]) as pm:
                self.assertIsNotNone(pm.process)
                self.assertTrue(pm.is_running())

            # Process should be terminated when exiting context
            mock_process.terminate.assert_called_once()

    def test_process_manager_run(self):
        """Test ProcessManager run method."""
        with patch("codeup.running_process.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            # For the context manager exit, ensure poll returns a value
            mock_process.poll.side_effect = [None, 0, 0]  # Added extra value for exit
            mock_process.stdout.readline.side_effect = ["output\n", ""]
            mock_process.stderr.readline.side_effect = [""]
            mock_process.stdout.__iter__.return_value = []
            mock_process.stderr.__iter__.return_value = []
            mock_process.wait.return_value = 0
            mock_popen.return_value = mock_process

            with ProcessManager(["echo", "test"]) as pm:
                exit_code = pm.run()
                self.assertEqual(exit_code, 0)
                self.assertEqual(pm.exit_code, 0)

    def test_process_manager_terminate_and_kill(self):
        """Test ProcessManager terminate and kill methods."""
        with patch("codeup.running_process.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = None  # Process is running
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
