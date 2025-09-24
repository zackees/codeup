import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class CodeupTester(unittest.TestCase):
    def setUp(self):
        """Set up a temporary git repository for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Initialize git repo
        subprocess.run(["git", "init"], check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            check=True,
            capture_output=True,
        )

        # Create a test file
        with open("test_file.txt", "w") as f:
            f.write("Hello World")

        # Initial commit
        subprocess.run(["git", "add", "test_file.txt"], check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], check=True, capture_output=True
        )

    def tearDown(self):
        """Clean up the temporary directory."""
        os.chdir(self.original_cwd)
        import shutil
        import stat

        def handle_remove_readonly(func, path, exc):
            """Handle read-only files on Windows."""
            if os.path.exists(path):
                os.chmod(path, stat.S_IWRITE)
                func(path)

        shutil.rmtree(self.test_dir, onerror=handle_remove_readonly)

    def test_just_ai_commit_flag(self):
        """Test that --just-ai-commit flag works correctly."""
        # Make a change to the file
        with open("test_file.txt", "w") as f:
            f.write("Hello World - Modified")

        # Test the codeup module by importing it from the source directory
        import sys

        sys.path.insert(0, str(Path(self.original_cwd) / "src"))

        try:
            from codeup.main import main as codeup_main

            # Mock sys.argv for the test
            original_argv = sys.argv
            sys.argv = ["codeup", "--just-ai-commit"]

            # Mock stdin to be non-interactive to trigger fallback behavior
            import io

            original_stdin = sys.stdin
            sys.stdin = io.StringIO("")

            # Mock API key functions to return None (disable AI)
            from unittest.mock import patch

            with (
                patch("codeup.config.get_openai_api_key", return_value=None),
                patch("codeup.config.get_anthropic_api_key", return_value=None),
            ):
                try:
                    result = codeup_main()
                    # Check that the command succeeded
                    self.assertEqual(
                        result, 0, "codeup --just-ai-commit should return 0"
                    )

                    # Verify that changes were committed
                    status_result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        capture_output=True,
                        text=True,
                        check=True,
                    )

                    # Should be no uncommitted changes
                    self.assertEqual(
                        status_result.stdout.strip(),
                        "",
                        "Working directory should be clean after commit",
                    )

                    # Verify the commit was created
                    log_result = subprocess.run(
                        ["git", "log", "--oneline", "-1"],
                        capture_output=True,
                        text=True,
                        check=True,
                    )

                    # Should contain automated commit message (since no AI keys)
                    self.assertIn("chore: automated commit", log_result.stdout)

                finally:
                    # Restore original stdin and argv
                    sys.stdin = original_stdin
                    sys.argv = original_argv

        except ImportError as e:
            self.skipTest(f"Could not import codeup module: {e}")
        finally:
            # Remove the added path
            if str(Path(self.original_cwd) / "src") in sys.path:
                sys.path.remove(str(Path(self.original_cwd) / "src"))

    def test_dry_run_functionality(self):
        """Test dry-run mode with various flag combinations."""
        # Create dummy lint and test scripts
        lint_script = Path("lint")
        test_script = Path("test")
        lint_script.write_text("#!/bin/bash\necho 'Linting...'")
        test_script.write_text("#!/bin/bash\necho 'Testing...'")
        lint_script.chmod(0o755)
        test_script.chmod(0o755)

        # Test the codeup module by importing it from the source directory
        import sys

        sys.path.insert(0, str(Path(self.original_cwd) / "src"))

        try:
            from codeup.main import _main_worker

            # Test case 1: --dry-run (should run both lint and test)
            with (
                patch("sys.argv", ["codeup", "--dry-run"]),
                patch(
                    "codeup.main.run_command_with_streaming_and_capture"
                ) as mock_run_cmd,
                patch("os.path.exists") as mock_exists,
                patch(
                    "codeup.main.check_environment", return_value=Path(self.test_dir)
                ),
                patch("os.chdir"),
            ):
                mock_exists.side_effect = lambda path: path in ["./lint", "./test"]
                mock_run_cmd.return_value = (
                    0,
                    "success",
                    "",
                )  # (return_code, stdout, stderr)

                result = _main_worker()

                self.assertEqual(result, 0, "Dry-run should return 0 on success")
                self.assertEqual(
                    mock_run_cmd.call_count, 2, "Should call lint and test commands"
                )

                # Verify lint command was called
                lint_call = mock_run_cmd.call_args_list[0]
                self.assertTrue(
                    any("lint" in str(arg) for arg in lint_call[0][0]),
                    "First call should be lint",
                )

                # Verify test command was called
                test_call = mock_run_cmd.call_args_list[1]
                self.assertTrue(
                    any("test" in str(arg) for arg in test_call[0][0]),
                    "Second call should be test",
                )

            # Test case 2: --dry-run --lint (should run only lint)
            with (
                patch("sys.argv", ["codeup", "--dry-run", "--lint"]),
                patch(
                    "codeup.main.run_command_with_streaming_and_capture"
                ) as mock_run_cmd,
                patch("os.path.exists") as mock_exists,
                patch(
                    "codeup.main.check_environment", return_value=Path(self.test_dir)
                ),
                patch("os.chdir"),
            ):
                mock_exists.side_effect = lambda path: path in ["./lint", "./test"]
                mock_run_cmd.return_value = (0, "success", "")

                result = _main_worker()

                self.assertEqual(result, 0, "Dry-run --lint should return 0 on success")
                self.assertEqual(
                    mock_run_cmd.call_count, 1, "Should call only lint command"
                )

                # Verify only lint command was called
                lint_call = mock_run_cmd.call_args_list[0]
                self.assertTrue(
                    any("lint" in str(arg) for arg in lint_call[0][0]),
                    "Only call should be lint",
                )

            # Test case 3: --dry-run --test (should run only test)
            with (
                patch("sys.argv", ["codeup", "--dry-run", "--test"]),
                patch(
                    "codeup.main.run_command_with_streaming_and_capture"
                ) as mock_run_cmd,
                patch("os.path.exists") as mock_exists,
                patch(
                    "codeup.main.check_environment", return_value=Path(self.test_dir)
                ),
                patch("os.chdir"),
            ):
                mock_exists.side_effect = lambda path: path in ["./lint", "./test"]
                mock_run_cmd.return_value = (0, "success", "")

                result = _main_worker()

                self.assertEqual(result, 0, "Dry-run --test should return 0 on success")
                self.assertEqual(
                    mock_run_cmd.call_count, 1, "Should call only test command"
                )

                # Verify only test command was called
                test_call = mock_run_cmd.call_args_list[0]
                self.assertTrue(
                    any("test" in str(arg) for arg in test_call[0][0]),
                    "Only call should be test",
                )

            # Test case 4: --dry-run --no-lint (should run only test)
            with (
                patch("sys.argv", ["codeup", "--dry-run", "--no-lint"]),
                patch(
                    "codeup.main.run_command_with_streaming_and_capture"
                ) as mock_run_cmd,
                patch("os.path.exists") as mock_exists,
                patch(
                    "codeup.main.check_environment", return_value=Path(self.test_dir)
                ),
                patch("os.chdir"),
            ):
                mock_exists.side_effect = lambda path: path in ["./lint", "./test"]
                mock_run_cmd.return_value = (0, "success", "")

                result = _main_worker()

                self.assertEqual(
                    result, 0, "Dry-run --no-lint should return 0 on success"
                )
                self.assertEqual(
                    mock_run_cmd.call_count, 1, "Should call only test command"
                )

                # Verify only test command was called
                test_call = mock_run_cmd.call_args_list[0]
                self.assertTrue(
                    any("test" in str(arg) for arg in test_call[0][0]),
                    "Only call should be test",
                )

            # Test case 5: --dry-run --no-test (should run only lint)
            with (
                patch("sys.argv", ["codeup", "--dry-run", "--no-test"]),
                patch(
                    "codeup.main.run_command_with_streaming_and_capture"
                ) as mock_run_cmd,
                patch("os.path.exists") as mock_exists,
                patch(
                    "codeup.main.check_environment", return_value=Path(self.test_dir)
                ),
                patch("os.chdir"),
            ):
                mock_exists.side_effect = lambda path: path in ["./lint", "./test"]
                mock_run_cmd.return_value = (0, "success", "")

                result = _main_worker()

                self.assertEqual(
                    result, 0, "Dry-run --no-test should return 0 on success"
                )
                self.assertEqual(
                    mock_run_cmd.call_count, 1, "Should call only lint command"
                )

                # Verify only lint command was called
                lint_call = mock_run_cmd.call_args_list[0]
                self.assertTrue(
                    any("lint" in str(arg) for arg in lint_call[0][0]),
                    "Only call should be lint",
                )

            # Test case 6: --dry-run --lint --test (should run both)
            with (
                patch("sys.argv", ["codeup", "--dry-run", "--lint", "--test"]),
                patch(
                    "codeup.main.run_command_with_streaming_and_capture"
                ) as mock_run_cmd,
                patch("os.path.exists") as mock_exists,
                patch(
                    "codeup.main.check_environment", return_value=Path(self.test_dir)
                ),
                patch("os.chdir"),
            ):
                mock_exists.side_effect = lambda path: path in ["./lint", "./test"]
                mock_run_cmd.return_value = (0, "success", "")

                result = _main_worker()

                self.assertEqual(
                    result, 0, "Dry-run --lint --test should return 0 on success"
                )
                self.assertEqual(
                    mock_run_cmd.call_count,
                    2,
                    "Should call both lint and test commands",
                )

            # Test case 7: --dry-run with lint failure
            with (
                patch("sys.argv", ["codeup", "--dry-run"]),
                patch(
                    "codeup.main.run_command_with_streaming_and_capture"
                ) as mock_run_cmd,
                patch("os.path.exists") as mock_exists,
                patch(
                    "codeup.main.check_environment", return_value=Path(self.test_dir)
                ),
                patch("os.chdir"),
            ):
                mock_exists.side_effect = lambda path: path in ["./lint", "./test"]
                # Mock lint failure, test should not be called
                mock_run_cmd.return_value = (1, "lint failed", "error")

                result = _main_worker()

                self.assertEqual(result, 1, "Dry-run should return 1 on lint failure")
                self.assertEqual(
                    mock_run_cmd.call_count, 1, "Should stop after lint failure"
                )

            # Test case 8: --dry-run --no-lint --no-test (should run nothing)
            with (
                patch("sys.argv", ["codeup", "--dry-run", "--no-lint", "--no-test"]),
                patch(
                    "codeup.main.run_command_with_streaming_and_capture"
                ) as mock_run_cmd,
                patch("os.path.exists") as mock_exists,
                patch(
                    "codeup.main.check_environment", return_value=Path(self.test_dir)
                ),
                patch("os.chdir"),
            ):
                mock_exists.side_effect = lambda path: path in ["./lint", "./test"]
                mock_run_cmd.return_value = (0, "success", "")

                result = _main_worker()

                self.assertEqual(
                    result, 0, "Dry-run with both disabled should return 0"
                )
                self.assertEqual(
                    mock_run_cmd.call_count, 0, "Should not call any commands"
                )

        except ImportError as e:
            self.skipTest(f"Could not import codeup module: {e}")
        finally:
            # Remove the added path
            if str(Path(self.original_cwd) / "src") in sys.path:
                sys.path.remove(str(Path(self.original_cwd) / "src"))

            # Clean up scripts
            if lint_script.exists():
                lint_script.unlink()
            if test_script.exists():
                test_script.unlink()


if __name__ == "__main__":
    unittest.main()
