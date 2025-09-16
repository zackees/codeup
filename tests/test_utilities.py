import os
import sys
import tempfile
import unittest
from pathlib import Path


class UtilitiesTester(unittest.TestCase):
    """Test utility functions in codeup."""

    def setUp(self):
        """Set up test environment."""
        self.original_cwd = os.getcwd()

    def tearDown(self):
        """Clean up test environment."""
        pass

    def test_uv_project_detection(self):
        """Test UV project detection functionality."""
        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.main import is_uv_project

            # Test in a temporary directory without UV files
            with tempfile.TemporaryDirectory() as temp_dir:
                original_cwd = os.getcwd()
                os.chdir(temp_dir)

                try:
                    # Should not be a UV project
                    self.assertFalse(
                        is_uv_project(), "Empty directory should not be a UV project"
                    )

                    # Create pyproject.toml but not uv.lock
                    with open("pyproject.toml", "w") as f:
                        f.write("[project]\nname = 'test'\n")

                    self.assertFalse(
                        is_uv_project(),
                        "Directory with only pyproject.toml should not be a UV project",
                    )

                    # Create uv.lock
                    with open("uv.lock", "w") as f:
                        f.write("# UV lock file\n")

                    self.assertTrue(
                        is_uv_project(),
                        "Directory with both files should be a UV project",
                    )

                finally:
                    os.chdir(original_cwd)

        except ImportError as e:
            self.skipTest(f"Could not import main module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_exec_command_formatting(self):
        """Test command execution string formatting."""
        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.main import _to_exec_str

            # Test bash command on Windows
            if sys.platform == "win32":
                cmd = "echo hello"
                result = _to_exec_str(cmd, bash=True)
                # Should use the full path to Git Bash and wrap the command
                self.assertTrue(
                    result.endswith(' -c "echo hello"'),
                    "Should wrap bash commands on Windows with proper executable",
                )
                self.assertTrue(
                    "bash.exe" in result,
                    "Should use bash.exe on Windows",
                )

                result = _to_exec_str(cmd, bash=False)
                self.assertEqual(result, cmd, "Should not wrap non-bash commands")
            else:
                # On non-Windows platforms, should return command as-is
                cmd = "echo hello"
                result = _to_exec_str(cmd, bash=True)
                self.assertEqual(
                    result, cmd, "Should return command as-is on non-Windows"
                )

        except ImportError as e:
            self.skipTest(f"Could not import main module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_yes_no_question_handling(self):
        """Test yes/no question handling."""
        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.main import get_answer_yes_or_no

            # This function has special handling for non-interactive terminals
            # When stdin is not a tty, it uses the default value
            # Test default behavior with non-interactive stdin
            result = get_answer_yes_or_no("Test question?", default=True)
            self.assertTrue(
                result, "Should return True for default True in non-interactive mode"
            )

            result = get_answer_yes_or_no("Test question?", default=False)
            self.assertFalse(
                result, "Should return False for default False in non-interactive mode"
            )

            result = get_answer_yes_or_no("Test question?", default="y")
            self.assertTrue(
                result, "Should return True for default 'y' in non-interactive mode"
            )

            result = get_answer_yes_or_no("Test question?", default="n")
            self.assertFalse(
                result, "Should return False for default 'n' in non-interactive mode"
            )

        except ImportError as e:
            self.skipTest(f"Could not import main module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_logging_configuration(self):
        """Test logging configuration."""
        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            import logging

            from codeup.main import configure_logging

            # Test enabling file logging
            with tempfile.TemporaryDirectory() as temp_dir:
                original_cwd = os.getcwd()
                os.chdir(temp_dir)

                try:
                    configure_logging(enable_file_logging=True)

                    # Should not raise any exceptions
                    logger = logging.getLogger(__name__)
                    logger.info("Test log message")

                    # Test without file logging
                    configure_logging(enable_file_logging=False)
                    logger.info("Another test log message")

                finally:
                    os.chdir(original_cwd)

        except ImportError as e:
            self.skipTest(f"Could not import main module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_environment_checking(self):
        """Test environment checking functionality."""
        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            import subprocess

            from codeup.main import find_git_directory

            # Test git availability (should be available in test environment)
            result = subprocess.run(["git", "--version"], capture_output=True)
            self.assertEqual(
                result.returncode, 0, "Git should be available for testing"
            )

            # Test in a directory without git
            with tempfile.TemporaryDirectory() as temp_dir:
                original_cwd = os.getcwd()
                os.chdir(temp_dir)

                try:
                    git_dir = find_git_directory()
                    self.assertEqual(
                        git_dir,
                        "",
                        "Should return empty string when no git directory found",
                    )

                finally:
                    os.chdir(original_cwd)

        except ImportError as e:
            self.skipTest(f"Could not import main module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_encoding_handling(self):
        """Test UTF-8 encoding handling on Windows."""
        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            # Import should set up encoding properly
            import codeup.main  # noqa: F401

            # Test that PYTHONIOENCODING is set correctly
            if sys.platform == "win32":
                # On Windows, the module should set proper encoding
                self.assertEqual(
                    os.environ.get("PYTHONIOENCODING"),
                    "utf-8",
                    "PYTHONIOENCODING should be set to utf-8 on Windows",
                )

        except ImportError as e:
            self.skipTest(f"Could not import main module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)


if __name__ == "__main__":
    unittest.main()
