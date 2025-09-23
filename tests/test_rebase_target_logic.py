"""Test the corrected rebase target logic for feature branches."""

import unittest
from unittest.mock import patch

from codeup.git_utils import (
    enhanced_attempt_rebase,
    get_upstream_branch,
    git_push,
    safe_rebase_try,
)


class RebaseTargetLogicTester(unittest.TestCase):
    """Test cases for the corrected rebase target logic."""

    def test_get_upstream_branch_with_tracking(self):
        """Test get_upstream_branch when branch has upstream tracking."""
        with patch(
            "codeup.git_utils.run_command_with_streaming_and_capture"
        ) as mock_run:
            # Mock successful upstream detection
            mock_run.return_value = (0, "origin/feature-xyz", "")

            result = get_upstream_branch()

            self.assertEqual(result, "origin/feature-xyz")
            mock_run.assert_called_once_with(
                ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
                quiet=True,
            )

    def test_get_upstream_branch_without_tracking(self):
        """Test get_upstream_branch when branch has no upstream tracking."""
        with patch(
            "codeup.git_utils.run_command_with_streaming_and_capture"
        ) as mock_run:
            # Mock no upstream (command fails)
            mock_run.return_value = (1, "", "fatal: no upstream configured")

            result = get_upstream_branch()

            self.assertEqual(result, "")

    @patch("codeup.git_utils.attempt_rebase")
    @patch("codeup.git_utils.check_rebase_needed")
    @patch("codeup.git_utils.get_main_branch")
    @patch("codeup.git_utils.get_upstream_branch")
    @patch("codeup.git_utils.get_current_branch")
    def test_safe_rebase_try_with_upstream_tracking(
        self,
        mock_get_current_branch,
        mock_get_upstream_branch,
        mock_get_main_branch,
        mock_check_rebase_needed,
        mock_attempt_rebase,
    ):
        """Test safe_rebase_try when feature branch has upstream tracking."""
        # Setup mocks
        mock_get_current_branch.return_value = "feature-xyz"
        mock_get_upstream_branch.return_value = "origin/feature-xyz"
        mock_get_main_branch.return_value = "main"
        mock_check_rebase_needed.return_value = True
        mock_attempt_rebase.return_value = (True, False)  # success, no conflicts

        with patch("builtins.print") as mock_print:
            result = safe_rebase_try()

        # Verify it used the upstream branch, not main
        self.assertTrue(result)
        mock_check_rebase_needed.assert_called_once_with("origin/feature-xyz")
        mock_attempt_rebase.assert_called_once_with("origin/feature-xyz")

        # Verify correct messaging
        mock_print.assert_any_call(
            "Current branch 'feature-xyz' tracks 'origin/feature-xyz'"
        )
        mock_print.assert_any_call("Attempting rebase onto origin/feature-xyz...")

    @patch("codeup.git_utils.attempt_rebase")
    @patch("codeup.git_utils.check_rebase_needed")
    @patch("codeup.git_utils.get_main_branch")
    @patch("codeup.git_utils.get_upstream_branch")
    @patch("codeup.git_utils.get_current_branch")
    def test_safe_rebase_try_without_upstream_tracking(
        self,
        mock_get_current_branch,
        mock_get_upstream_branch,
        mock_get_main_branch,
        mock_check_rebase_needed,
        mock_attempt_rebase,
    ):
        """Test safe_rebase_try when feature branch has no upstream tracking."""
        # Setup mocks
        mock_get_current_branch.return_value = "feature-abc"
        mock_get_upstream_branch.return_value = ""  # No upstream
        mock_get_main_branch.return_value = "main"
        mock_check_rebase_needed.return_value = True
        mock_attempt_rebase.return_value = (True, False)  # success, no conflicts

        with patch("builtins.print") as mock_print:
            result = safe_rebase_try()

        # Verify it fell back to main branch
        self.assertTrue(result)
        mock_check_rebase_needed.assert_called_once_with("main")
        mock_attempt_rebase.assert_called_once_with("main")

        # Verify correct messaging
        mock_print.assert_any_call(
            "Current branch 'feature-abc' has no upstream, using main branch 'main'"
        )

    @patch("codeup.git_utils.attempt_rebase")
    @patch("codeup.git_utils.check_rebase_needed")
    @patch("codeup.git_utils.get_main_branch")
    @patch("codeup.git_utils.get_upstream_branch")
    @patch("codeup.git_utils.get_current_branch")
    def test_safe_rebase_try_on_main_branch_no_upstream(
        self,
        mock_get_current_branch,
        mock_get_upstream_branch,
        mock_get_main_branch,
        mock_check_rebase_needed,
        mock_attempt_rebase,
    ):
        """Test safe_rebase_try when on main branch with no upstream."""
        # Setup mocks
        mock_get_current_branch.return_value = "main"
        mock_get_upstream_branch.return_value = ""  # No upstream
        mock_get_main_branch.return_value = "main"

        result = safe_rebase_try()

        # Should return True immediately without attempting rebase
        self.assertTrue(result)
        mock_check_rebase_needed.assert_not_called()
        mock_attempt_rebase.assert_not_called()

    @patch("codeup.git_utils.run_command_with_streaming_and_capture")
    @patch("codeup.git_utils.get_upstream_branch")
    @patch("codeup.git_utils.get_current_branch")
    def test_git_push_sets_upstream_for_new_branch(
        self, mock_get_current_branch, mock_get_upstream_branch, mock_run
    ):
        """Test git_push sets upstream for branches without tracking."""
        # Setup mocks
        mock_get_current_branch.return_value = "new-feature"
        mock_get_upstream_branch.return_value = ""  # No upstream
        mock_run.return_value = (0, "", "")  # Successful push

        with patch("builtins.print") as mock_print:
            success, error = git_push()

        # Verify it used --set-upstream
        self.assertTrue(success)
        self.assertEqual(error, "")
        mock_run.assert_called_once_with(
            ["git", "push", "--set-upstream", "origin", "new-feature"],
            quiet=False,
        )

        # Verify messaging
        mock_print.assert_called_once_with(
            "No upstream set for branch 'new-feature', setting upstream to origin/new-feature"
        )

    @patch("codeup.git_utils.run_command_with_streaming_and_capture")
    @patch("codeup.git_utils.get_upstream_branch")
    @patch("codeup.git_utils.get_current_branch")
    def test_git_push_normal_with_upstream(
        self, mock_get_current_branch, mock_get_upstream_branch, mock_run
    ):
        """Test git_push uses normal push when upstream is already set."""
        # Setup mocks
        mock_get_current_branch.return_value = "feature-xyz"
        mock_get_upstream_branch.return_value = "origin/feature-xyz"  # Has upstream
        mock_run.return_value = (0, "", "")  # Successful push

        success, error = git_push()

        # Verify it used normal push
        self.assertTrue(success)
        self.assertEqual(error, "")
        mock_run.assert_called_once_with(
            ["git", "push"],
            quiet=False,
        )

    @patch("codeup.git_utils.git_fetch")
    @patch("codeup.git_utils.run_command_with_streaming_and_capture")
    @patch("codeup.git_utils.capture_pre_rebase_state")
    @patch("codeup.git_utils.verify_clean_working_directory")
    def test_enhanced_attempt_rebase_uses_correct_target(
        self, mock_verify_clean, mock_capture_state, mock_run, mock_git_fetch
    ):
        """Test enhanced_attempt_rebase uses the correct target branch."""
        # Setup mocks
        mock_verify_clean.return_value = True
        mock_capture_state.return_value = "abc123"
        mock_git_fetch.return_value = 0
        mock_run.return_value = (0, "", "")  # Successful rebase

        with patch("codeup.git_utils.verify_rebase_success") as mock_verify_success:
            mock_verify_success.return_value = True

            # Test with feature branch target
            result = enhanced_attempt_rebase("feature-xyz")

        # Verify it attempted rebase with correct target
        self.assertTrue(result.success)
        self.assertFalse(result.had_conflicts)

        # Verify the correct git rebase command was called
        # Look for the rebase command in the call list
        git_rebase_found = False
        for call in mock_run.call_args_list:
            if (
                len(call[0]) > 0
                and len(call[0][0]) > 2
                and call[0][0][0] == "git"
                and call[0][0][1] == "rebase"
                and call[0][0][2] == "origin/feature-xyz"
            ):
                git_rebase_found = True
                break
        self.assertTrue(
            git_rebase_found,
            "Expected 'git rebase origin/feature-xyz' command not found",
        )

    @patch("codeup.git_utils.git_fetch")
    @patch("codeup.git_utils.run_command_with_streaming_and_capture")
    @patch("codeup.git_utils.capture_pre_rebase_state")
    @patch("codeup.git_utils.verify_clean_working_directory")
    def test_enhanced_attempt_rebase_handles_origin_prefix(
        self, mock_verify_clean, mock_capture_state, mock_run, mock_git_fetch
    ):
        """Test enhanced_attempt_rebase handles target branches with origin/ prefix."""
        # Setup mocks
        mock_verify_clean.return_value = True
        mock_capture_state.return_value = "abc123"
        mock_git_fetch.return_value = 0
        mock_run.return_value = (0, "", "")  # Successful rebase

        with patch("codeup.git_utils.verify_rebase_success") as mock_verify_success:
            mock_verify_success.return_value = True

            # Test with target that already has origin/ prefix
            result = enhanced_attempt_rebase("origin/feature-xyz")

        # Verify it didn't double the origin/ prefix
        self.assertTrue(result.success)

        # Verify the correct git rebase command was called without doubling origin/
        git_rebase_found = False
        for call in mock_run.call_args_list:
            if (
                len(call[0]) > 0
                and len(call[0][0]) > 2
                and call[0][0][0] == "git"
                and call[0][0][1] == "rebase"
                and call[0][0][2] == "origin/feature-xyz"
            ):
                git_rebase_found = True
                break
        self.assertTrue(
            git_rebase_found,
            "Expected 'git rebase origin/feature-xyz' command not found",
        )


if __name__ == "__main__":
    unittest.main()
