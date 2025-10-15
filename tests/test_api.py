"""Tests for the CodeUp API module."""

import os
import tempfile
import unittest


class ApiTester(unittest.TestCase):
    """Test public API functionality."""

    def setUp(self):
        """Set up test environment."""
        self.original_cwd = os.getcwd()

    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.original_cwd)

    def test_import_api_module(self):
        """Test that API module can be imported."""
        try:
            from codeup.api import LintTestResult, lint_test

            # Check that we can import the classes and functions
            self.assertIsNotNone(LintTestResult)
            self.assertIsNotNone(lint_test)
        except ImportError as e:
            self.fail(f"Could not import API module: {e}")

    def test_import_from_main_package(self):
        """Test that API exports are available from main package."""
        try:
            from codeup import LintTestResult, lint_test

            # Check that we can import from main package
            self.assertIsNotNone(LintTestResult)
            self.assertIsNotNone(lint_test)
        except ImportError as e:
            self.fail(f"Could not import from codeup package: {e}")

    def test_lint_test_result_dataclass(self):
        """Test LintTestResult dataclass structure."""
        try:
            from codeup.api import LintTestResult

            # Create a result instance
            result = LintTestResult(
                success=True,
                exit_code=0,
                lint_passed=True,
                test_passed=True,
                stdout="Test output",
                stderr="",
                error_message=None,
            )

            # Check all fields exist and have correct values
            self.assertTrue(result.success)
            self.assertEqual(result.exit_code, 0)
            self.assertTrue(result.lint_passed)
            self.assertTrue(result.test_passed)
            self.assertEqual(result.stdout, "Test output")
            self.assertEqual(result.stderr, "")
            self.assertIsNone(result.error_message)

            # Test that it's frozen (immutable)
            with self.assertRaises((AttributeError, TypeError)):
                result.success = False  # type: ignore

        except ImportError as e:
            self.skipTest(f"Could not import API module: {e}")

    def test_lint_test_result_failure(self):
        """Test LintTestResult for failure cases."""
        try:
            from codeup.api import LintTestResult

            # Create a failure result
            result = LintTestResult(
                success=False,
                exit_code=1,
                lint_passed=False,
                test_passed=None,
                stdout="",
                stderr="Lint error",
                error_message="Linting failed",
            )

            # Check failure state
            self.assertFalse(result.success)
            self.assertEqual(result.exit_code, 1)
            self.assertFalse(result.lint_passed)
            self.assertIsNone(result.test_passed)
            self.assertEqual(result.error_message, "Linting failed")

        except ImportError as e:
            self.skipTest(f"Could not import API module: {e}")

    def test_api_function_signature(self):
        """Test that lint_test has correct signature."""
        try:
            import inspect

            from codeup.api import lint_test

            # Get function signature
            sig = inspect.signature(lint_test)

            # Check that parameters exist
            self.assertIn("verbose", sig.parameters)
            self.assertIn("log_level", sig.parameters)
            self.assertIn("capture_output", sig.parameters)

            # Check default values
            self.assertFalse(sig.parameters["verbose"].default)
            self.assertIsNone(sig.parameters["log_level"].default)
            self.assertTrue(sig.parameters["capture_output"].default)

        except ImportError as e:
            self.skipTest(f"Could not import API module: {e}")

    def test_lint_test_in_non_git_dir(self):
        """Test API function behavior in non-git directory."""
        try:
            import shutil
            import stat

            from codeup.api import lint_test

            # Create a temporary non-git directory
            temp_dir = tempfile.mkdtemp()

            try:
                os.chdir(temp_dir)

                # Should fail since it's not a git repo
                result = lint_test(capture_output=True)

                # Should not succeed in non-git directory
                self.assertFalse(result.success)
                self.assertNotEqual(result.exit_code, 0)
                self.assertIsNotNone(result.error_message)
            finally:
                # Change back before cleanup
                os.chdir(self.original_cwd)

                # Windows-compatible cleanup
                def handle_remove_readonly(func, path, exc):
                    """Handle read-only files on Windows."""
                    if os.path.exists(path):
                        os.chmod(path, stat.S_IWRITE)
                        func(path)

                shutil.rmtree(temp_dir, onerror=handle_remove_readonly)

        except ImportError as e:
            self.skipTest(f"Could not import API module: {e}")

    def test_api_docstrings(self):
        """Test that API functions have proper documentation."""
        try:
            from codeup.api import LintTestResult, lint_test

            # Check that functions have docstrings
            self.assertIsNotNone(lint_test.__doc__, "lint_test should have a docstring")
            self.assertIsNotNone(
                LintTestResult.__doc__, "LintTestResult should have a docstring"
            )

            # Check that docstrings contain useful information
            func_doc = lint_test.__doc__
            self.assertIsNotNone(func_doc, "lint_test docstring should not be None")
            assert func_doc is not None  # Type narrowing for pyright
            self.assertIn(
                "Args:",
                func_doc,
                "Docstring should document arguments",
            )
            self.assertIn(
                "Returns:",
                func_doc,
                "Docstring should document return value",
            )

        except ImportError as e:
            self.skipTest(f"Could not import API module: {e}")

    def test_lint_test_in_empty_git_dir_without_scripts(self):
        """Test lint-test returns 0 in empty git dir without lint/test scripts."""
        try:
            import shutil
            import stat
            import subprocess

            from codeup.api import lint_test

            # Create a temporary directory
            temp_dir = tempfile.mkdtemp()

            try:
                os.chdir(temp_dir)

                # Initialize as a git repository
                subprocess.run(
                    ["git", "init"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
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

                # Run lint-test in this empty directory (no ./lint or ./test scripts)
                result = lint_test(capture_output=True)

                # Should succeed with exit code 0 since there are no scripts to run
                self.assertTrue(
                    result.success,
                    f"lint_test should succeed in empty git dir. Error: {result.error_message}",
                )
                self.assertEqual(
                    result.exit_code,
                    0,
                    f"Exit code should be 0, got {result.exit_code}",
                )

                # Both should be None since the scripts don't exist
                self.assertIsNone(
                    result.lint_passed,
                    "lint_passed should be None when ./lint doesn't exist",
                )
                self.assertIsNone(
                    result.test_passed,
                    "test_passed should be None when ./test doesn't exist",
                )

                # Verify output contains dry-run completion message
                combined_output = result.stdout + result.stderr
                self.assertIn(
                    "Dry-run completed successfully",
                    combined_output,
                    "Output should contain dry-run completion message",
                )

            finally:
                # Change back before cleanup
                os.chdir(self.original_cwd)

                # Windows-compatible cleanup
                def handle_remove_readonly(func, path, exc):
                    """Handle read-only files on Windows."""
                    if os.path.exists(path):
                        os.chmod(path, stat.S_IWRITE)
                        func(path)

                shutil.rmtree(temp_dir, onerror=handle_remove_readonly)

        except ImportError as e:
            self.skipTest(f"Could not import API module: {e}")


if __name__ == "__main__":
    unittest.main()
