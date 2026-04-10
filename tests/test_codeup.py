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
                patch(
                    "codeup.aicommit._generate_ai_commit_message_clud",
                    return_value=None,
                ),
            ):
                try:
                    result = codeup_main()
                    # With new behavior: when both AI providers fail and terminal is not a PTY,
                    # the command should fail with exit code 1 and ask user to commit manually
                    self.assertEqual(
                        result,
                        1,
                        "codeup --just-ai-commit should return 1 when both AI providers fail in non-PTY",
                    )

                    # Verify that changes were NOT committed (staged but not committed)
                    status_result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        capture_output=True,
                        text=True,
                        check=True,
                    )

                    # Should still have staged changes (not committed)
                    self.assertNotEqual(
                        status_result.stdout.strip(),
                        "",
                        "Changes should be staged but not committed when AI fails in non-PTY",
                    )

                    # Verify no new commit was created (since AI failed in non-PTY)
                    # The initial commit should still be the latest
                    log_result = subprocess.run(
                        ["git", "log", "--oneline", "-1"],
                        capture_output=True,
                        text=True,
                        check=True,
                    )

                    # Should contain the initial commit message, not an automated one
                    self.assertIn("Initial commit", log_result.stdout)

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
                patch("codeup.main._run_command_streaming") as mock_run_cmd,
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
                patch("codeup.main._run_command_streaming") as mock_run_cmd,
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
                patch("codeup.main._run_command_streaming") as mock_run_cmd,
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
                patch("codeup.main._run_command_streaming") as mock_run_cmd,
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
                patch("codeup.main._run_command_streaming") as mock_run_cmd,
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
                patch("codeup.main._run_command_streaming") as mock_run_cmd,
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
                patch("codeup.main._run_command_streaming") as mock_run_cmd,
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
                patch("codeup.main._run_command_streaming") as mock_run_cmd,
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

    def test_skipped_untracked_files_are_not_staged_by_main_workflow(self):
        """Test skipped untracked files stay untracked instead of being blanket-added."""
        with open("test_file.txt", "w") as f:
            f.write("Hello World - Modified")
        with open("keep_untracked.txt", "w") as f:
            f.write("Keep me out of the commit")

        import sys

        sys.path.insert(0, str(Path(self.original_cwd) / "src"))

        try:
            from codeup.main import _main_worker

            with (
                patch(
                    "sys.argv",
                    ["codeup", "--no-push", "--no-lint", "--no-test"],
                ),
                patch("codeup.utils.get_answer_with_choices", return_value="n"),
                patch(
                    "codeup.main.ai_commit_or_prompt_for_commit_message"
                ) as mock_commit,
                patch("sys.stdin.isatty", return_value=True),
            ):
                result = _main_worker()

            self.assertEqual(result, 0)
            mock_commit.assert_called_once()

            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True,
            )
            status_lines = status_result.stdout.splitlines()

            self.assertIn("M  test_file.txt", status_lines)
            self.assertIn("?? keep_untracked.txt", status_lines)
            self.assertNotIn("A  keep_untracked.txt", status_lines)

        except ImportError as e:
            self.skipTest(f"Could not import codeup module: {e}")
        finally:
            if str(Path(self.original_cwd) / "src") in sys.path:
                sys.path.remove(str(Path(self.original_cwd) / "src"))

    def test_main_worker_stages_only_tracked_files_with_mocks(self):
        """Test the main workflow stages only tracked files before committing."""
        import sys

        sys.path.insert(0, str(Path(self.original_cwd) / "src"))

        try:
            from codeup.main import _main_worker

            with (
                patch(
                    "sys.argv",
                    ["codeup", "--no-push", "--no-lint", "--no-test"],
                ),
                patch(
                    "codeup.main.check_environment",
                    return_value=Path(self.test_dir),
                ),
                patch("os.chdir"),
                patch("codeup.main.get_staged_files", return_value=[]),
                patch("codeup.main.get_unstaged_files", return_value=["test_file.txt"]),
                patch(
                    "codeup.main.get_untracked_files",
                    return_value=["keep_untracked.txt"],
                ),
                patch("codeup.main.has_unpushed_commits", return_value=False),
                patch(
                    "codeup.main.interactive_add_untracked_files"
                ) as mock_interactive_add,
                patch("codeup.main.has_modified_tracked_files", return_value=True),
                patch(
                    "codeup.main.git_add_files", return_value=0
                ) as mock_git_add_files,
                patch(
                    "codeup.main.ai_commit_or_prompt_for_commit_message"
                ) as mock_commit,
                patch("sys.stdin.isatty", return_value=True),
            ):
                mock_interactive_add.return_value.success = True
                mock_interactive_add.return_value.error_message = ""
                mock_interactive_add.return_value.files_added = []
                mock_interactive_add.return_value.files_skipped = ["keep_untracked.txt"]

                result = _main_worker()

            self.assertEqual(result, 0)
            mock_git_add_files.assert_called_once_with(["test_file.txt"])
            mock_commit.assert_called_once()

        except ImportError as e:
            self.skipTest(f"Could not import codeup module: {e}")
        finally:
            if str(Path(self.original_cwd) / "src") in sys.path:
                sys.path.remove(str(Path(self.original_cwd) / "src"))

    def test_main_worker_skips_commit_when_only_untracked_files_added_with_mocks(self):
        """Test the main workflow does not commit when there are only new files."""
        import sys

        sys.path.insert(0, str(Path(self.original_cwd) / "src"))

        try:
            from codeup.main import _main_worker

            with (
                patch(
                    "sys.argv",
                    ["codeup", "--no-push", "--no-lint", "--no-test"],
                ),
                patch(
                    "codeup.main.check_environment",
                    return_value=Path(self.test_dir),
                ),
                patch("os.chdir"),
                patch("codeup.main.get_staged_files", return_value=[]),
                patch("codeup.main.get_unstaged_files", return_value=[]),
                patch("codeup.main.get_untracked_files", return_value=["new_file.txt"]),
                patch("codeup.main.has_unpushed_commits", return_value=False),
                patch(
                    "codeup.main.interactive_add_untracked_files"
                ) as mock_interactive_add,
                patch("codeup.main.has_modified_tracked_files", return_value=False),
                patch(
                    "codeup.main.git_add_files", return_value=0
                ) as mock_git_add_files,
                patch(
                    "codeup.main.ai_commit_or_prompt_for_commit_message"
                ) as mock_commit,
                patch("sys.stdin.isatty", return_value=True),
            ):
                mock_interactive_add.return_value.success = True
                mock_interactive_add.return_value.error_message = ""
                mock_interactive_add.return_value.files_added = ["new_file.txt"]
                mock_interactive_add.return_value.files_skipped = []

                result = _main_worker()

            self.assertEqual(result, 0)
            mock_git_add_files.assert_called_once_with([])
            mock_commit.assert_not_called()

        except ImportError as e:
            self.skipTest(f"Could not import codeup module: {e}")
        finally:
            if str(Path(self.original_cwd) / "src") in sys.path:
                sys.path.remove(str(Path(self.original_cwd) / "src"))

    def test_main_worker_aborts_when_lint_adds_unexpected_file(self):
        """Test lint validation aborts on newly added untracked files."""
        import sys

        sys.path.insert(0, str(Path(self.original_cwd) / "src"))

        try:
            from codeup.main import _main_worker

            with (
                patch(
                    "sys.argv",
                    ["codeup", "--no-push", "--no-test"],
                ),
                patch(
                    "codeup.main.check_environment",
                    return_value=Path(self.test_dir),
                ),
                patch("os.chdir"),
                patch(
                    "codeup.main.os.path.exists",
                    side_effect=lambda path: path == "./lint",
                ),
                patch("codeup.main.get_staged_files", side_effect=[[], [], []]),
                patch(
                    "codeup.main.get_unstaged_files",
                    side_effect=[
                        ["test_file.txt"],
                        ["test_file.txt"],
                        ["test_file.txt"],
                    ],
                ),
                patch(
                    "codeup.main.get_untracked_files",
                    side_effect=[[], [], ["generated.txt"]],
                ),
                patch("codeup.main.get_git_diff_cached", side_effect=["", ""]),
                patch(
                    "codeup.main.get_git_diff",
                    side_effect=["tracked-diff", "tracked-diff"],
                ),
                patch("codeup.main.has_unpushed_commits", return_value=False),
                patch("codeup.main.has_modified_tracked_files", return_value=True),
                patch("codeup.main._run_command_streaming", return_value=(0, "", "")),
                patch(
                    "codeup.main.git_add_files", return_value=0
                ) as mock_git_add_files,
                patch(
                    "codeup.main.ai_commit_or_prompt_for_commit_message"
                ) as mock_commit,
                patch("codeup.main.error") as mock_error,
            ):
                result = _main_worker()

            self.assertEqual(result, 1)
            mock_git_add_files.assert_not_called()
            mock_commit.assert_not_called()
            self.assertTrue(
                any(
                    "MAJOR ERROR: Repository files changed during lint." in call.args[0]
                    for call in mock_error.call_args_list
                )
            )
            self.assertTrue(
                any(
                    "New untracked files appeared after lint: generated.txt"
                    in call.args[0]
                    for call in mock_error.call_args_list
                )
            )

        except ImportError as e:
            self.skipTest(f"Could not import codeup module: {e}")
        finally:
            if str(Path(self.original_cwd) / "src") in sys.path:
                sys.path.remove(str(Path(self.original_cwd) / "src"))

    def test_main_worker_allows_lint_to_change_tracked_diff(self):
        """Test lint may change tracked files before commit when tests are skipped."""
        import sys

        sys.path.insert(0, str(Path(self.original_cwd) / "src"))

        try:
            from codeup.main import _main_worker

            with (
                patch(
                    "sys.argv",
                    ["codeup", "--no-push", "--no-test"],
                ),
                patch(
                    "codeup.main.check_environment",
                    return_value=Path(self.test_dir),
                ),
                patch("os.chdir"),
                patch(
                    "codeup.main.os.path.exists",
                    side_effect=lambda path: path == "./lint",
                ),
                patch("codeup.main.get_staged_files", side_effect=[[], [], []]),
                patch(
                    "codeup.main.get_unstaged_files",
                    side_effect=[
                        ["test_file.txt"],
                        ["test_file.txt"],
                        ["test_file.txt"],
                    ],
                ),
                patch("codeup.main.get_untracked_files", side_effect=[[], [], []]),
                patch("codeup.main.get_git_diff_cached", side_effect=["", ""]),
                patch(
                    "codeup.main.get_git_diff",
                    side_effect=["tracked-diff-before", "tracked-diff-after"],
                ),
                patch("codeup.main.has_unpushed_commits", return_value=False),
                patch("codeup.main.has_modified_tracked_files", return_value=True),
                patch("codeup.main._run_command_streaming", return_value=(0, "", "")),
                patch(
                    "codeup.main.git_add_files", return_value=0
                ) as mock_git_add_files,
                patch(
                    "codeup.main.ai_commit_or_prompt_for_commit_message"
                ) as mock_commit,
                patch("codeup.main.error") as mock_error,
            ):
                result = _main_worker()

            self.assertEqual(result, 0)
            mock_git_add_files.assert_called_once_with(["test_file.txt"])
            mock_commit.assert_called_once()
            mock_error.assert_not_called()

        except ImportError as e:
            self.skipTest(f"Could not import codeup module: {e}")
        finally:
            if str(Path(self.original_cwd) / "src") in sys.path:
                sys.path.remove(str(Path(self.original_cwd) / "src"))

    def test_main_worker_aborts_when_test_changes_tracked_diff(self):
        """Test test validation aborts if files change after the post-lint snapshot."""
        import sys

        sys.path.insert(0, str(Path(self.original_cwd) / "src"))

        try:
            from codeup.main import _main_worker

            with (
                patch(
                    "sys.argv",
                    ["codeup", "--no-push"],
                ),
                patch(
                    "codeup.main.check_environment",
                    return_value=Path(self.test_dir),
                ),
                patch("os.chdir"),
                patch(
                    "codeup.main.os.path.exists",
                    side_effect=lambda path: path in {"./lint", "./test"},
                ),
                patch("codeup.main.get_staged_files", side_effect=[[], [], [], []]),
                patch(
                    "codeup.main.get_unstaged_files",
                    side_effect=[
                        ["test_file.txt"],
                        ["test_file.txt"],
                        ["test_file.txt"],
                        ["test_file.txt"],
                    ],
                ),
                patch("codeup.main.get_untracked_files", side_effect=[[], [], [], []]),
                patch("codeup.main.get_git_diff_cached", side_effect=["", "", ""]),
                patch(
                    "codeup.main.get_git_diff",
                    side_effect=[
                        "tracked-diff-before-lint",
                        "tracked-diff-after-lint",
                        "tracked-diff-after-test",
                    ],
                ),
                patch("codeup.main.has_unpushed_commits", return_value=False),
                patch("codeup.main.has_modified_tracked_files", return_value=True),
                patch(
                    "codeup.main._run_command_streaming",
                    side_effect=[(0, "", ""), (0, "", "")],
                ),
                patch(
                    "codeup.main.git_add_files", return_value=0
                ) as mock_git_add_files,
                patch(
                    "codeup.main.ai_commit_or_prompt_for_commit_message"
                ) as mock_commit,
                patch("codeup.main.error") as mock_error,
            ):
                result = _main_worker()

            self.assertEqual(result, 1)
            mock_git_add_files.assert_not_called()
            mock_commit.assert_not_called()
            self.assertTrue(
                any(
                    "MAJOR ERROR: Repository files changed during test." in call.args[0]
                    for call in mock_error.call_args_list
                )
            )
            self.assertTrue(
                any(
                    "The unstaged tracked diff changed during test." in call.args[0]
                    for call in mock_error.call_args_list
                )
            )

        except ImportError as e:
            self.skipTest(f"Could not import codeup module: {e}")
        finally:
            if str(Path(self.original_cwd) / "src") in sys.path:
                sys.path.remove(str(Path(self.original_cwd) / "src"))


if __name__ == "__main__":
    unittest.main()
