import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class GitOperationsTester(unittest.TestCase):
    """Test git-related operations in codeup."""

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

        # Create initial files
        with open("test_file.txt", "w") as f:
            f.write("Initial content")

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

    def test_git_status_detection(self):
        """Test that git status is correctly detected."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.main import get_git_status, has_changes_to_commit

            # Initially should have no changes
            self.assertFalse(
                has_changes_to_commit(), "Should have no changes initially"
            )

            # Make a change
            with open("test_file.txt", "w") as f:
                f.write("Modified content")

            # Now should have changes
            self.assertTrue(
                has_changes_to_commit(), "Should detect changes after modification"
            )

            # Test git status output
            status = get_git_status()
            self.assertIn("modified:", status, "Should show modified files in status")

        except ImportError as e:
            self.skipTest(f"Could not import required modules: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_untracked_files_detection(self):
        """Test detection of untracked files."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.main import get_untracked_files, has_changes_to_commit

            # Add an untracked file
            with open("new_file.txt", "w") as f:
                f.write("New file content")

            # Should detect the untracked file
            untracked = get_untracked_files()
            self.assertIn("new_file.txt", untracked, "Should detect new untracked file")

            # Should detect that there are changes to commit
            self.assertTrue(
                has_changes_to_commit(), "Should detect untracked files as changes"
            )

        except ImportError as e:
            self.skipTest(f"Could not import required modules: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_branch_operations(self):
        """Test branch-related operations."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.main import get_current_branch, get_main_branch

            # Test current branch detection
            current = get_current_branch()
            self.assertIsInstance(current, str, "Current branch should be a string")
            self.assertGreater(
                len(current), 0, "Current branch name should not be empty"
            )

            # Test main branch detection
            main = get_main_branch()
            self.assertIn(
                main, ["main", "master"], "Main branch should be 'main' or 'master'"
            )

        except ImportError as e:
            self.skipTest(f"Could not import required modules: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_safe_git_commit(self):
        """Test safe git commit functionality."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.git_utils import safe_git_commit

            # Make a change and stage it
            with open("test_file.txt", "w") as f:
                f.write("Content for commit test")
            subprocess.run(
                ["git", "add", "test_file.txt"], check=True, capture_output=True
            )

            # Test commit
            result = safe_git_commit("Test commit message")
            self.assertEqual(result, 0, "Git commit should succeed")

            # Verify commit was created
            log_result = subprocess.run(
                ["git", "log", "--oneline", "-1"],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn(
                "Test commit message",
                log_result.stdout,
                "Commit message should appear in git log",
            )

        except ImportError as e:
            self.skipTest(f"Could not import required modules: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_git_directory_detection(self):
        """Test git directory detection functionality."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.git_utils import find_git_directory

            # Should find current directory as git repo
            git_dir = find_git_directory()
            self.assertEqual(
                git_dir, self.test_dir, "Should find the test git directory"
            )

            # Test from subdirectory
            subdir = os.path.join(self.test_dir, "subdir")
            os.makedirs(subdir)
            os.chdir(subdir)

            git_dir = find_git_directory()
            self.assertEqual(
                git_dir, self.test_dir, "Should find git directory from subdirectory"
            )

        except ImportError as e:
            self.skipTest(f"Could not import required modules: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)


if __name__ == "__main__":
    unittest.main()
