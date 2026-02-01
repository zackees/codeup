"""Tests for AI commit message generation functionality."""

import unittest
from unittest.mock import patch

from codeup.aicommit import AuthException, _opencommit_or_prompt_for_commit_message


class TestAICommitNonPTY(unittest.TestCase):
    """Test AI commit behavior when terminal is not a PTY."""

    @patch("codeup.aicommit._generate_ai_commit_message")
    @patch("sys.stdin.isatty")
    def test_both_ai_providers_fail_non_pty_raises_error(
        self, mock_isatty, mock_generate_ai
    ):
        """
        Test that when both AI providers fail AND terminal is not a PTY,
        the function raises RuntimeError instead of using a fallback message.
        """
        # Mock AI generation to fail with AuthException
        mock_generate_ai.return_value = AuthException(
            "No valid API keys configured", provider=None
        )

        # Mock terminal to not be a PTY
        mock_isatty.return_value = False

        # Should raise RuntimeError with appropriate message
        with self.assertRaises(RuntimeError) as context:
            _opencommit_or_prompt_for_commit_message(
                auto_accept=True, no_interactive=False
            )

        # Verify error message contains expected text
        error_message = str(context.exception)
        self.assertIn("codeup -m", error_message.lower())

    @patch("codeup.aicommit._generate_ai_commit_message")
    @patch("sys.stdin.isatty")
    def test_ai_success_does_not_check_pty(self, mock_isatty, mock_generate_ai):
        """
        Test that when AI succeeds, PTY status doesn't matter.
        """
        # Mock AI generation to succeed
        mock_generate_ai.return_value = "feat: add new feature"

        # Mock terminal to not be a PTY
        mock_isatty.return_value = False

        # Mock safe_git_commit to avoid actual git operations
        with patch("codeup.aicommit.safe_git_commit") as mock_commit:
            # Should not raise an error
            _opencommit_or_prompt_for_commit_message(
                auto_accept=True, no_interactive=False
            )

            # Verify commit was called with AI-generated message
            mock_commit.assert_called_once_with("feat: add new feature")

    @patch("codeup.aicommit._generate_ai_commit_message")
    @patch("sys.stdin.isatty")
    @patch("builtins.input")
    def test_ai_fails_pty_allows_manual_input(
        self, mock_input, mock_isatty, mock_generate_ai
    ):
        """
        Test that when AI fails but terminal IS a PTY,
        manual input is requested.
        """
        # Mock AI generation to fail with AuthException
        mock_generate_ai.return_value = AuthException(
            "No valid API keys configured", provider=None
        )

        # Mock terminal to be a PTY
        mock_isatty.return_value = True

        # Mock user input
        mock_input.return_value = "fix: manual commit message"

        # Mock safe_git_commit to avoid actual git operations
        with patch("codeup.aicommit.safe_git_commit") as mock_commit:
            # Should not raise an error
            _opencommit_or_prompt_for_commit_message(
                auto_accept=True, no_interactive=False
            )

            # Verify commit was called with manual message
            mock_commit.assert_called_once_with("fix: manual commit message")

    @patch("codeup.aicommit._generate_ai_commit_message")
    def test_no_interactive_mode_raises_error(self, mock_generate_ai):
        """
        Test that when AI fails in no_interactive mode,
        RuntimeError is raised regardless of PTY status.
        """
        # Mock AI generation to fail with AuthException
        mock_generate_ai.return_value = AuthException(
            "No valid API keys configured", provider=None
        )

        # Should raise RuntimeError with appropriate message
        with self.assertRaises(RuntimeError) as context:
            _opencommit_or_prompt_for_commit_message(
                auto_accept=True, no_interactive=True
            )

        # Verify error message
        error_message = str(context.exception)
        self.assertIn("codeup -m", error_message.lower())

    @patch("codeup.aicommit._generate_ai_commit_message")
    def test_unexpected_exception_non_interactive_raises_error(self, mock_generate_ai):
        """
        Test that when an unexpected Exception occurs in non-interactive mode,
        RuntimeError is raised with appropriate message.
        """
        # Mock AI generation to fail with unexpected Exception
        mock_generate_ai.return_value = ValueError("Unexpected error occurred")

        # Should raise RuntimeError with appropriate message
        with self.assertRaises(RuntimeError) as context:
            _opencommit_or_prompt_for_commit_message(
                auto_accept=True, no_interactive=True
            )

        # Verify error message mentions the unexpected error
        error_message = str(context.exception)
        self.assertIn("unexpected error", error_message.lower())

    @patch("codeup.aicommit._generate_ai_commit_message")
    @patch("sys.stdin.isatty")
    def test_unexpected_exception_non_pty_raises_error(
        self, mock_isatty, mock_generate_ai
    ):
        """
        Test that when an unexpected Exception occurs AND terminal is not a PTY,
        RuntimeError is raised.
        """
        # Mock AI generation to fail with unexpected Exception
        mock_generate_ai.return_value = ValueError("Unexpected error occurred")

        # Mock terminal to not be a PTY
        mock_isatty.return_value = False

        # Should raise RuntimeError with appropriate message
        with self.assertRaises(RuntimeError) as context:
            _opencommit_or_prompt_for_commit_message(
                auto_accept=True, no_interactive=False
            )

        # Verify error message mentions the unexpected error
        error_message = str(context.exception)
        self.assertIn("unexpected error", error_message.lower())


if __name__ == "__main__":
    unittest.main()
