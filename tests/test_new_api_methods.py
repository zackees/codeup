"""Tests for new Codeup API methods: pre_check_git, lint, and test."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_interactive_add_untracked_files_can_remove_paths(self):
        """Test interactive untracked file flow supports remove action."""
        temp_dir = tempfile.mkdtemp()
        original_dir = os.getcwd()
        src_path = str(Path(__file__).resolve().parents[1] / "src")

        try:
            os.chdir(temp_dir)
            sys.path.insert(0, src_path)
            for module_name in list(sys.modules):
                if module_name == "codeup" or module_name.startswith("codeup."):
                    del sys.modules[module_name]

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

            with open("delete_me.txt", "w") as f:
                f.write("temporary content")
            os.mkdir("keep_me")
            with open(os.path.join("keep_me", "note.txt"), "w") as f:
                f.write("keep")

            from codeup.git_utils import (
                get_untracked_files,
                interactive_add_untracked_files,
            )

            with patch(
                "codeup.utils.get_answer_with_choices",
                side_effect=["r", "n"],
            ):
                result = interactive_add_untracked_files(
                    is_tty=True,
                    pre_test_mode=False,
                    no_interactive=False,
                )

            self.assertTrue(result.success, f"Error: {result.error_message}")
            self.assertFalse(os.path.exists("delete_me.txt"))
            self.assertTrue(os.path.exists("keep_me"))
            self.assertEqual(result.files_added, [])
            self.assertEqual(result.files_skipped, ["keep_me/note.txt"])
            self.assertEqual(get_untracked_files(), ["keep_me/note.txt"])

        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)
            os.chdir(original_dir)
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_interactive_add_untracked_files_batches_staging_after_prompts(self):
        """Test accepted untracked files are staged once after prompting completes."""
        from codeup.git_utils import interactive_add_untracked_files

        with (
            patch(
                "codeup.git_utils.get_untracked_files",
                return_value=["alpha.txt", "beta.txt", "gamma.txt"],
            ),
            patch(
                "codeup.utils.get_answer_with_choices",
                side_effect=["y", "n", "y"],
            ),
            patch("codeup.git_utils.git_add_files", return_value=0) as mock_git_add,
        ):
            result = interactive_add_untracked_files(
                is_tty=True,
                pre_test_mode=False,
                no_interactive=False,
            )

        self.assertTrue(result.success, f"Error: {result.error_message}")
        self.assertEqual(result.files_added, ["alpha.txt", "gamma.txt"])
        self.assertEqual(result.files_skipped, ["beta.txt"])
        mock_git_add.assert_called_once_with(["alpha.txt", "gamma.txt"])

    def test_interactive_add_untracked_files_ctrl_c_skips_staging(self):
        """Test Ctrl-C during prompting does not stage previously accepted files."""
        from codeup.git_utils import interactive_add_untracked_files

        with (
            patch(
                "codeup.git_utils.get_untracked_files",
                return_value=["alpha.txt", "beta.txt"],
            ),
            patch(
                "codeup.utils.get_answer_with_choices",
                side_effect=["y", KeyboardInterrupt()],
            ),
            patch("codeup.git_utils.git_add_files") as mock_git_add,
            patch("codeup.git_utils.interrupt_main"),
        ):
            with self.assertRaises(KeyboardInterrupt):
                interactive_add_untracked_files(
                    is_tty=True,
                    pre_test_mode=False,
                    no_interactive=False,
                )

        mock_git_add.assert_not_called()

    def test_remove_untracked_path_refuses_tracked_files(self):
        """Test tracked files are not removed by the untracked-path helper."""
        temp_dir = tempfile.mkdtemp()
        original_dir = os.getcwd()
        src_path = str(Path(__file__).resolve().parents[1] / "src")

        try:
            os.chdir(temp_dir)
            sys.path.insert(0, src_path)
            for module_name in list(sys.modules):
                if module_name == "codeup" or module_name.startswith("codeup."):
                    del sys.modules[module_name]

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

            with open("tracked.txt", "w") as f:
                f.write("tracked content")
            subprocess.run(
                ["git", "add", "tracked.txt"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "test: add tracked file"],
                check=True,
                capture_output=True,
                text=True,
            )

            from codeup.git_utils import remove_untracked_path

            self.assertFalse(remove_untracked_path("tracked.txt"))
            self.assertTrue(os.path.exists("tracked.txt"))

        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)
            os.chdir(original_dir)
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_remove_untracked_path_refuses_paths_outside_repo(self):
        """Test untracked-path removal refuses paths outside the repository root."""
        temp_dir = tempfile.mkdtemp()
        outside_dir = tempfile.mkdtemp()
        original_dir = os.getcwd()
        src_path = str(Path(__file__).resolve().parents[1] / "src")

        try:
            os.chdir(temp_dir)
            sys.path.insert(0, src_path)
            for module_name in list(sys.modules):
                if module_name == "codeup" or module_name.startswith("codeup."):
                    del sys.modules[module_name]

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

            outside_file = Path(outside_dir) / "outside.txt"
            outside_file.write_text("outside", encoding="utf-8")

            from codeup.git_utils import remove_untracked_path

            self.assertFalse(remove_untracked_path(str(outside_file)))
            self.assertTrue(outside_file.exists())

        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)
            os.chdir(original_dir)
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)
            shutil.rmtree(outside_dir, ignore_errors=True)

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
