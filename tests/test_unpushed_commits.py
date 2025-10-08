import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class UnpushedCommitsTest(unittest.TestCase):
    """Test unpushed commits detection and related workflow."""

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

        # Create initial commit
        with open("initial.txt", "w") as f:
            f.write("Initial content")
        subprocess.run(["git", "add", "initial.txt"], check=True, capture_output=True)
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

    def test_has_unpushed_commits_no_upstream(self):
        """Test has_unpushed_commits returns False when no upstream is set."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.git_utils import has_unpushed_commits

            # No upstream set - should return False
            result = has_unpushed_commits()
            self.assertFalse(result, "Should return False when no upstream is set")

        except ImportError as e:
            self.skipTest(f"Could not import required modules: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_has_unpushed_commits_with_upstream(self):
        """Test has_unpushed_commits with a tracked upstream branch."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.git_utils import has_unpushed_commits

            # Create a bare repo to act as remote
            remote_dir = tempfile.mkdtemp()
            subprocess.run(
                ["git", "init", "--bare"],
                cwd=remote_dir,
                check=True,
                capture_output=True,
            )

            # Add remote and push
            subprocess.run(
                ["git", "remote", "add", "origin", remote_dir],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "push", "-u", "origin", "main"],
                check=True,
                capture_output=True,
            )

            # Initially should have no unpushed commits
            result = has_unpushed_commits()
            self.assertFalse(result, "Should return False when all commits are pushed")

            # Create a new commit
            with open("new_file.txt", "w") as f:
                f.write("New content")
            subprocess.run(
                ["git", "add", "new_file.txt"], check=True, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-m", "New commit"], check=True, capture_output=True
            )

            # Now should have unpushed commits
            result = has_unpushed_commits()
            self.assertTrue(
                result, "Should return True when there are unpushed commits"
            )

            # Cleanup remote dir
            import shutil
            import stat

            def handle_remove_readonly(func, path, exc):
                if os.path.exists(path):
                    os.chmod(path, stat.S_IWRITE)
                    func(path)

            shutil.rmtree(remote_dir, onerror=handle_remove_readonly)

        except ImportError as e:
            self.skipTest(f"Could not import required modules: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_has_unpushed_commits_invalid_output(self):
        """Test has_unpushed_commits handles invalid git output gracefully."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.git_utils import has_unpushed_commits

            # Mock the run_command function to return invalid output
            with patch(
                "codeup.git_utils.run_command_with_streaming_and_capture"
            ) as mock_run:
                # First call is get_upstream_branch - return a valid upstream
                # Second call is the rev-list count - return invalid output
                mock_run.side_effect = [
                    (0, "origin/main", ""),  # get_upstream_branch
                    (0, "invalid_number", ""),  # rev-list --count
                ]

                result = has_unpushed_commits()
                self.assertFalse(
                    result, "Should return False when git output is invalid"
                )

        except ImportError as e:
            self.skipTest(f"Could not import required modules: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_has_modified_tracked_files_no_changes(self):
        """Test has_modified_tracked_files with no changes."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.git_utils import has_modified_tracked_files

            # No changes - should return False
            result = has_modified_tracked_files()
            self.assertFalse(result, "Should return False when there are no changes")

        except ImportError as e:
            self.skipTest(f"Could not import required modules: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_has_modified_tracked_files_unstaged_changes(self):
        """Test has_modified_tracked_files with unstaged changes to tracked files."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.git_utils import has_modified_tracked_files

            # Modify a tracked file
            with open("initial.txt", "w") as f:
                f.write("Modified content")

            # Should detect modified tracked file
            result = has_modified_tracked_files()
            self.assertTrue(result, "Should return True when tracked file is modified")

        except ImportError as e:
            self.skipTest(f"Could not import required modules: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_has_modified_tracked_files_staged_changes(self):
        """Test has_modified_tracked_files with staged changes."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.git_utils import has_modified_tracked_files

            # Modify and stage a tracked file
            with open("initial.txt", "w") as f:
                f.write("Staged content")
            subprocess.run(
                ["git", "add", "initial.txt"], check=True, capture_output=True
            )

            # Should detect staged changes
            result = has_modified_tracked_files()
            self.assertTrue(result, "Should return True when changes are staged")

        except ImportError as e:
            self.skipTest(f"Could not import required modules: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_has_modified_tracked_files_only_untracked(self):
        """Test has_modified_tracked_files with only untracked files."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.git_utils import has_modified_tracked_files

            # Add an untracked file
            with open("untracked.txt", "w") as f:
                f.write("Untracked content")

            # Should NOT detect untracked files
            result = has_modified_tracked_files()
            self.assertFalse(
                result, "Should return False when only untracked files exist"
            )

        except ImportError as e:
            self.skipTest(f"Could not import required modules: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_has_modified_tracked_files_mixed(self):
        """Test has_modified_tracked_files with both tracked and untracked changes."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.git_utils import has_modified_tracked_files

            # Modify tracked file
            with open("initial.txt", "w") as f:
                f.write("Modified tracked")

            # Add untracked file
            with open("untracked.txt", "w") as f:
                f.write("Untracked content")

            # Should detect the modified tracked file
            result = has_modified_tracked_files()
            self.assertTrue(
                result,
                "Should return True when tracked file is modified (even with untracked files)",
            )

        except ImportError as e:
            self.skipTest(f"Could not import required modules: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_workflow_unpushed_commits_no_changes(self):
        """Test that workflow runs correctly with unpushed commits but no new changes."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.git_utils import has_changes_to_commit, has_unpushed_commits

            # Create a bare repo to act as remote
            remote_dir = tempfile.mkdtemp()
            subprocess.run(
                ["git", "init", "--bare"],
                cwd=remote_dir,
                check=True,
                capture_output=True,
            )

            # Add remote and push
            subprocess.run(
                ["git", "remote", "add", "origin", remote_dir],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "push", "-u", "origin", "main"],
                check=True,
                capture_output=True,
            )

            # Create a new commit
            with open("new_file.txt", "w") as f:
                f.write("New content")
            subprocess.run(
                ["git", "add", "new_file.txt"], check=True, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-m", "New commit"], check=True, capture_output=True
            )

            # Now we have unpushed commits but no working directory changes
            has_changes = has_changes_to_commit()
            has_unpushed = has_unpushed_commits()

            self.assertFalse(has_changes, "Should have no working directory changes")
            self.assertTrue(has_unpushed, "Should have unpushed commits")

            # This state should allow codeup to run (the key test case)
            should_run = has_changes or has_unpushed
            self.assertTrue(
                should_run, "Codeup should run when there are unpushed commits"
            )

            # Cleanup remote dir
            import shutil
            import stat

            def handle_remove_readonly(func, path, exc):
                if os.path.exists(path):
                    os.chmod(path, stat.S_IWRITE)
                    func(path)

            shutil.rmtree(remote_dir, onerror=handle_remove_readonly)

        except ImportError as e:
            self.skipTest(f"Could not import required modules: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_workflow_should_commit_logic(self):
        """Test the should_commit logic - commit only when tracked files are modified."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.git_utils import has_modified_tracked_files

            # Scenario 1: Only untracked files
            with open("untracked1.txt", "w") as f:
                f.write("Untracked")

            should_commit = has_modified_tracked_files()
            self.assertFalse(
                should_commit,
                "Should NOT commit when only untracked files are present",
            )

            # Clean up
            os.remove("untracked1.txt")

            # Scenario 2: Modified tracked file
            with open("initial.txt", "w") as f:
                f.write("Modified tracked file")

            should_commit = has_modified_tracked_files()
            self.assertTrue(
                should_commit, "Should commit when tracked file is modified"
            )

            # Scenario 3: Both modified tracked and untracked files
            with open("untracked2.txt", "w") as f:
                f.write("Another untracked")

            should_commit = has_modified_tracked_files()
            self.assertTrue(
                should_commit,
                "Should commit when tracked file is modified (even with untracked files)",
            )

        except ImportError as e:
            self.skipTest(f"Could not import required modules: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)


if __name__ == "__main__":
    unittest.main()
