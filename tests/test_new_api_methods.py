"""Tests for new Codeup API methods: pre_check_git, lint, and test."""

import os
import subprocess
import tempfile
import unittest

from codeup import Codeup


class NewApiMethodsTester(unittest.TestCase):
    """Test new API methods for pre_check_git, lint, and test."""

    def test_result_dataclass_fields(self):
        """Test that result dataclasses have expected fields."""
        # Test PreCheckGitResult
        result = Codeup.PreCheckGitResult(
            success=True,
            error_message="",
            has_changes=False,
            untracked_files=[],
            staged_files=[],
            unstaged_files=[],
        )
        self.assertTrue(result.success)
        self.assertFalse(result.has_changes)
        self.assertEqual(result.untracked_files, [])

        # Test LintResult
        lint_result = Codeup.LintResult(
            success=True,
            exit_code=0,
            stdout="output",
            stderr="",
            stopped_early=False,
            error_message="",
        )
        self.assertTrue(lint_result.success)
        self.assertEqual(lint_result.exit_code, 0)
        self.assertFalse(lint_result.stopped_early)

        # Test TestResult
        test_result = Codeup.TestResult(
            success=True,
            exit_code=0,
            stdout="output",
            stderr="",
            stopped_early=False,
            error_message="",
        )
        self.assertTrue(test_result.success)
        self.assertEqual(test_result.exit_code, 0)
        self.assertFalse(test_result.stopped_early)

    def test_pre_check_git_no_changes(self):
        """Test pre_check_git in a clean git repository."""
        # Create a temporary directory with a git repo
        temp_dir = tempfile.mkdtemp()
        original_dir = os.getcwd()

        try:
            os.chdir(temp_dir)

            # Initialize git repo
            subprocess.run(["git", "init"], check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                check=True,
                capture_output=True,
                text=True,
            )

            # Check git status
            result = Codeup.pre_check_git(allow_interactive=False)

            self.assertTrue(result.success, f"Error: {result.error_message}")
            self.assertFalse(result.has_changes)
            self.assertEqual(result.untracked_files, [])
            self.assertEqual(result.staged_files, [])
            self.assertEqual(result.unstaged_files, [])

        finally:
            os.chdir(original_dir)
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pre_check_git_with_untracked_files(self):
        """Test pre_check_git with untracked files."""
        # Create a temporary directory with a git repo
        temp_dir = tempfile.mkdtemp()
        original_dir = os.getcwd()

        try:
            os.chdir(temp_dir)

            # Initialize git repo
            subprocess.run(["git", "init"], check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                check=True,
                capture_output=True,
                text=True,
            )

            # Create an untracked file
            with open("test_file.txt", "w") as f:
                f.write("test content")

            # Check git status
            result = Codeup.pre_check_git(allow_interactive=False)

            self.assertTrue(result.success, f"Error: {result.error_message}")
            self.assertTrue(result.has_changes)
            self.assertEqual(len(result.untracked_files), 1)
            self.assertIn("test_file.txt", result.untracked_files)

        finally:
            os.chdir(original_dir)
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_lint_script_not_found(self):
        """Test lint() when ./lint script doesn't exist."""
        # Create a temporary directory
        temp_dir = tempfile.mkdtemp()
        original_dir = os.getcwd()

        try:
            os.chdir(temp_dir)

            # Run lint (should fail since ./lint doesn't exist)
            result = Codeup.lint()

            self.assertFalse(result.success)
            self.assertEqual(result.exit_code, 1)
            self.assertIn("not found", result.error_message)
            self.assertFalse(result.stopped_early)

        finally:
            os.chdir(original_dir)
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_test_script_not_found(self):
        """Test test() when ./test script doesn't exist."""
        # Create a temporary directory
        temp_dir = tempfile.mkdtemp()
        original_dir = os.getcwd()

        try:
            os.chdir(temp_dir)

            # Run test (should fail since ./test doesn't exist)
            result = Codeup.test()

            self.assertFalse(result.success)
            self.assertEqual(result.exit_code, 1)
            self.assertIn("not found", result.error_message)
            self.assertFalse(result.stopped_early)

        finally:
            os.chdir(original_dir)
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_lint_with_successful_script(self):
        """Test lint() with a successful ./lint script."""
        # Create a temporary directory
        temp_dir = tempfile.mkdtemp()
        original_dir = os.getcwd()

        try:
            os.chdir(temp_dir)

            # Create a simple ./lint script that succeeds
            with open("lint", "w") as f:
                f.write("#!/bin/bash\n")
                f.write('echo "Linting passed"\n')
                f.write("exit 0\n")

            # Make it executable
            import stat

            os.chmod("lint", os.stat("lint").st_mode | stat.S_IEXEC)

            # Run lint
            result = Codeup.lint()

            self.assertTrue(result.success, f"Error: {result.error_message}")
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Linting passed", result.stdout)
            self.assertFalse(result.stopped_early)

        finally:
            os.chdir(original_dir)
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_test_with_successful_script(self):
        """Test test() with a successful ./test script."""
        # Create a temporary directory
        temp_dir = tempfile.mkdtemp()
        original_dir = os.getcwd()

        try:
            os.chdir(temp_dir)

            # Create a simple ./test script that succeeds
            with open("test", "w") as f:
                f.write("#!/bin/bash\n")
                f.write('echo "All tests passed"\n')
                f.write("exit 0\n")

            # Make it executable
            import stat

            os.chmod("test", os.stat("test").st_mode | stat.S_IEXEC)

            # Run test
            result = Codeup.test()

            self.assertTrue(result.success, f"Error: {result.error_message}")
            self.assertEqual(result.exit_code, 0)
            self.assertIn("All tests passed", result.stdout)
            self.assertFalse(result.stopped_early)

        finally:
            os.chdir(original_dir)
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_lint_with_callback_early_exit(self):
        """Test lint() with callback that triggers early exit."""
        # Create a temporary directory
        temp_dir = tempfile.mkdtemp()
        original_dir = os.getcwd()

        try:
            os.chdir(temp_dir)

            # Create a ./lint script that outputs multiple lines
            with open("lint", "w") as f:
                f.write("#!/bin/bash\n")
                f.write('echo "Line 1"\n')
                f.write('echo "Line 2 - ERROR"\n')
                f.write('echo "Line 3"\n')
                f.write("exit 0\n")

            # Make it executable
            import stat

            os.chmod("lint", os.stat("lint").st_mode | stat.S_IEXEC)

            # Callback that stops on "ERROR"
            def stop_on_error(line: str) -> bool:
                return "ERROR" not in line

            # Run lint with callback
            result = Codeup.lint(on_line=stop_on_error)

            # Should have stopped early
            self.assertTrue(result.stopped_early)
            self.assertFalse(result.success)  # Not successful due to early stop
            self.assertIn("Line 1", result.stdout)
            self.assertIn("ERROR", result.stdout)
            # Line 3 should NOT be in output since we stopped early
            self.assertNotIn("Line 3", result.stdout)

        finally:
            os.chdir(original_dir)
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_test_with_callback_continue(self):
        """Test test() with callback that always continues."""
        # Create a temporary directory
        temp_dir = tempfile.mkdtemp()
        original_dir = os.getcwd()

        try:
            os.chdir(temp_dir)

            # Create a ./test script that outputs multiple lines
            with open("test", "w") as f:
                f.write("#!/bin/bash\n")
                f.write('echo "Test 1 PASSED"\n')
                f.write('echo "Test 2 PASSED"\n')
                f.write('echo "Test 3 PASSED"\n')
                f.write("exit 0\n")

            # Make it executable
            import stat

            os.chmod("test", os.stat("test").st_mode | stat.S_IEXEC)

            # Track callback invocations
            callback_lines = []

            def track_lines(line: str) -> bool:
                callback_lines.append(line)
                return True  # Always continue

            # Run test with callback
            result = Codeup.test(on_line=track_lines)

            # Should have completed successfully
            self.assertTrue(result.success)
            self.assertFalse(result.stopped_early)
            self.assertEqual(result.exit_code, 0)

            # Callback should have been called for each line
            self.assertGreater(len(callback_lines), 0)
            self.assertTrue(any("PASSED" in line for line in callback_lines))

        finally:
            os.chdir(original_dir)
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
