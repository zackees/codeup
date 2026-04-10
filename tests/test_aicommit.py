"""Tests for AI commit message generation functionality."""

import shutil
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from codeup.aicommit import (
    AuthException,
    _clean_clud_output,
    _generate_ai_commit_message,
    _generate_ai_commit_message_clud,
    _opencommit_or_prompt_for_commit_message,
    _strip_emojis,
)


class TestAICommitNonPTY(unittest.TestCase):
    """Test AI commit behavior when terminal is not a PTY."""

    @patch("codeup.aicommit._generate_ai_commit_message")
    def test_both_ai_providers_fail_non_pty_exits_after_prompt_timeout(
        self, mock_generate_ai
    ):
        """
        Test that when both AI providers fail AND terminal is not a PTY,
        prompt failure exits instead of creating a synthetic commit.
        """
        mock_generate_ai.return_value = AuthException(
            "No valid API keys configured", provider=None
        )

        from codeup.utils import InputTimeoutError

        with (
            patch("sys.stdin.isatty", return_value=False),
            patch(
                "codeup.utils.input_with_timeout",
                side_effect=InputTimeoutError("Input timed out"),
            ),
            patch(
                "codeup.utils.exit_for_missing_user_input",
                side_effect=SystemExit(1),
            ) as mock_exit,
            patch("codeup.aicommit.safe_git_commit") as mock_commit,
        ):
            with self.assertRaises(SystemExit) as context:
                _opencommit_or_prompt_for_commit_message(
                    auto_accept=True, no_interactive=False
                )

        self.assertEqual(context.exception.code, 1)
        mock_exit.assert_called_once()
        mock_commit.assert_not_called()

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
    def test_ai_fails_pty_allows_manual_input(self, mock_generate_ai):
        """
        Test that when AI fails but terminal IS a PTY,
        manual input is requested.
        """
        mock_generate_ai.return_value = AuthException(
            "No valid API keys configured", provider=None
        )

        with (
            patch("sys.stdin.isatty", return_value=True),
            patch(
                "codeup.utils.input_with_timeout",
                return_value="fix: manual commit message",
            ),
            patch("codeup.aicommit.safe_git_commit") as mock_commit,
        ):
            _opencommit_or_prompt_for_commit_message(
                auto_accept=True, no_interactive=False
            )

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
    def test_unexpected_exception_non_pty_exits_after_prompt_timeout(
        self, mock_generate_ai
    ):
        """
        Test that unexpected AI errors still follow prompt timeout exit behavior.
        """
        mock_generate_ai.return_value = ValueError("Unexpected error occurred")

        from codeup.utils import InputTimeoutError

        with (
            patch("sys.stdin.isatty", return_value=False),
            patch(
                "codeup.utils.input_with_timeout",
                side_effect=InputTimeoutError("Input timed out"),
            ),
            patch(
                "codeup.utils.exit_for_missing_user_input",
                side_effect=SystemExit(1),
            ) as mock_exit,
            patch("codeup.aicommit.safe_git_commit") as mock_commit,
        ):
            with self.assertRaises(SystemExit) as context:
                _opencommit_or_prompt_for_commit_message(
                    auto_accept=True, no_interactive=False
                )

        self.assertEqual(context.exception.code, 1)
        mock_exit.assert_called_once()
        mock_commit.assert_not_called()


class TestStripEmojis(unittest.TestCase):
    """Test emoji stripping utility."""

    def test_strips_common_emojis(self):
        self.assertEqual(
            _strip_emojis("\U0001f389 feat: add feature"), "feat: add feature"
        )

    def test_strips_multiple_emojis(self):
        self.assertEqual(
            _strip_emojis("\U0001f525\U0001f680 fix: resolve bug \U0001f41b"),
            "fix: resolve bug",
        )

    def test_preserves_plain_text(self):
        self.assertEqual(_strip_emojis("chore: update deps"), "chore: update deps")

    def test_returns_empty_for_only_emojis(self):
        self.assertEqual(_strip_emojis("\U0001f389\U0001f525\U0001f680"), "")

    def test_strips_speech_balloon(self):
        """Test stripping the 💬 emoji clud uses as output prefix."""
        self.assertEqual(
            _strip_emojis("\U0001f4ac feat: add logging"), "feat: add logging"
        )


class TestCleanCludOutput(unittest.TestCase):
    """Test clud output cleaning logic."""

    def test_cleans_typical_clud_output(self):
        """Test typical clud output: 💬 message + 📊 tokens line."""
        raw = "\U0001f4ac feat(app): add logging\n\U0001f4ca tokens: 4\n"
        self.assertEqual(_clean_clud_output(raw), "feat(app): add logging")

    def test_cleans_output_with_code_fences(self):
        """Test clud output wrapped in markdown code fences."""
        raw = "\U0001f4ac ```\nfeat(app): add logging\n```\n\U0001f4ca tokens: 4\n"
        self.assertEqual(_clean_clud_output(raw), "feat(app): add logging")

    def test_cleans_plain_message(self):
        """Test output that is just a plain commit message."""
        self.assertEqual(_clean_clud_output("feat: add logging\n"), "feat: add logging")

    def test_returns_none_for_only_metadata(self):
        self.assertIsNone(_clean_clud_output("\U0001f4ca tokens: 4\n"))

    def test_returns_none_for_only_emojis(self):
        self.assertIsNone(_clean_clud_output("\U0001f4ac\U0001f525"))

    def test_takes_first_non_empty_line(self):
        raw = "\n\nfeat: add logging\nsome extra text\n"
        self.assertEqual(_clean_clud_output(raw), "feat: add logging")

    def test_strips_tokens_line_with_various_counts(self):
        raw = "\U0001f4ac fix: bug\n\U0001f4ca tokens: 123\n"
        self.assertEqual(_clean_clud_output(raw), "fix: bug")

    def test_handles_multiple_tokens_lines(self):
        """Test output with 📊 appearing multiple times (as seen in practice)."""
        raw = "\U0001f4ca tokens: 12\n\U0001f4ac feat: add logging\n\U0001f4ca tokens: 12\n"
        self.assertEqual(_clean_clud_output(raw), "feat: add logging")

    def test_ignores_stdin_status_line_before_commit_message(self):
        """Test status chatter is ignored when a commit message follows."""
        raw = (
            "Reading additional input from stdin...\nfeat(docs): clarify README usage\n"
        )
        self.assertEqual(_clean_clud_output(raw), "feat(docs): clarify README usage")


@unittest.skipUnless(shutil.which("clud"), "clud not available on this system")
class TestCludCommitMessageGeneration(unittest.TestCase):
    """Integration tests for clud-based commit message generation (requires clud)."""

    def test_clud_generates_commit_message(self):
        """Test that clud produces a valid commit message from a diff."""
        diff_text = (
            "diff --git a/src/app.py b/src/app.py\n"
            "index 1234567..abcdefg 100644\n"
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -10,6 +10,7 @@\n"
            " def main():\n"
            "+    logging.basicConfig(level=logging.INFO)\n"
            "     app.run()\n"
        )
        result = _generate_ai_commit_message_clud(diff_text)

        self.assertIsInstance(result, str)
        assert isinstance(result, str)  # narrow type for subsequent asserts
        self.assertGreater(len(result), 0)
        # Should be a single line
        self.assertNotIn("\n", result)
        # Should be reasonable length
        self.assertLessEqual(len(result), 100)
        # Should not contain emojis (we strip them)
        self.assertEqual(result, _strip_emojis(result))

    def test_clud_returns_conventional_format(self):
        """Test that clud output follows conventional commit type prefix."""
        diff_text = (
            "diff --git a/README.md b/README.md\n"
            "--- a/README.md\n"
            "+++ b/README.md\n"
            "@@ -1,3 +1,4 @@\n"
            " # My Project\n"
            "+This project does amazing things.\n"
            " ## Usage\n"
        )
        result = _generate_ai_commit_message_clud(diff_text)

        self.assertIsInstance(result, str)
        assert isinstance(result, str)  # narrow type
        valid_types = (
            "feat",
            "fix",
            "docs",
            "style",
            "refactor",
            "perf",
            "test",
            "chore",
            "ci",
            "build",
        )
        has_valid_type = any(result.startswith(t) for t in valid_types)
        self.assertTrue(
            has_valid_type,
            f"Commit message '{result}' does not start with a conventional commit type",
        )


class TestCludCommitMessageUnit(unittest.TestCase):
    """Unit tests for clud commit message generation (mocked, no clud required)."""

    @patch("shutil.which", return_value=None)
    def test_returns_none_when_clud_not_found(self, _mock_which):
        result = _generate_ai_commit_message_clud("some diff")
        self.assertIsNone(result)

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/clud")
    def test_returns_message_on_success(self, _mock_which, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="feat: add logging\n", stderr=""
        )
        result = _generate_ai_commit_message_clud("some diff")
        self.assertEqual(result, "feat: add logging")

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/clud")
    def test_strips_emojis_from_output(self, _mock_which, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="\U0001f389 feat: add logging\n", stderr=""
        )
        result = _generate_ai_commit_message_clud("some diff")
        self.assertEqual(result, "feat: add logging")

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/clud")
    def test_cleans_typical_clud_output(self, _mock_which, mock_run):
        """Test end-to-end cleaning of real clud output format."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="\U0001f4ac feat: add logging\n\U0001f4ca tokens: 4\n",
            stderr="",
        )
        result = _generate_ai_commit_message_clud("some diff")
        self.assertEqual(result, "feat: add logging")

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/clud")
    def test_cleans_code_fence_output(self, _mock_which, mock_run):
        """Test cleaning clud output wrapped in code fences."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="\U0001f4ac ```\nfeat: add logging\n```\n\U0001f4ca tokens: 4\n",
            stderr="",
        )
        result = _generate_ai_commit_message_clud("some diff")
        self.assertEqual(result, "feat: add logging")

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/clud")
    def test_takes_first_line_only(self, _mock_which, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="feat: add logging\n\nThis adds structured logging.\n",
            stderr="",
        )
        result = _generate_ai_commit_message_clud("some diff")
        self.assertEqual(result, "feat: add logging")

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/clud")
    def test_returns_none_on_nonzero_exit(self, _mock_which, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error occurred"
        )
        result = _generate_ai_commit_message_clud("some diff")
        self.assertIsNone(result)

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/clud")
    def test_returns_none_on_empty_output(self, _mock_which, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = _generate_ai_commit_message_clud("some diff")
        self.assertIsNone(result)

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/clud")
    def test_returns_none_on_emoji_only_output(self, _mock_which, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="\U0001f389\U0001f525\U0001f680\n", stderr=""
        )
        result = _generate_ai_commit_message_clud("some diff")
        self.assertIsNone(result)

    @patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired("clud", 120),
    )
    @patch("shutil.which", return_value="/usr/bin/clud")
    def test_returns_none_on_timeout(self, _mock_which, _mock_run):
        result = _generate_ai_commit_message_clud("some diff")
        self.assertIsNone(result)

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/clud")
    def test_passes_diff_via_stdin(self, _mock_which, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="fix: patch bug\n", stderr=""
        )
        _generate_ai_commit_message_clud("my special diff content")
        args = mock_run.call_args
        self.assertEqual(args.kwargs["input"], "my special diff content")

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/clud")
    def test_preserves_diff_newlines_in_stdin(self, _mock_which, mock_run):
        """Test that diff newlines are preserved when passed via stdin."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="feat: add feature\n", stderr=""
        )
        _generate_ai_commit_message_clud("line1\nline2\nline3")
        args = mock_run.call_args
        self.assertEqual(args.kwargs["input"], "line1\nline2\nline3")

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/clud")
    def test_codex_backend_passed_to_cli(self, _mock_which, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="feat: add codex cli support\n", stderr=""
        )
        result = _generate_ai_commit_message(provider="codex")
        self.assertEqual(result, "feat: add codex cli support")
        self.assertEqual(
            mock_run.call_args.args[0][:3],
            ["clud", "--session-model", "codex"],
        )

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/clud")
    def test_claude_backend_passed_to_cli(self, _mock_which, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="fix: use claude cli for commits\n", stderr=""
        )
        result = _generate_ai_commit_message(provider="claude")
        self.assertEqual(result, "fix: use claude cli for commits")
        self.assertEqual(
            mock_run.call_args.args[0][:3],
            ["clud", "--session-model", "claude"],
        )

    @patch("shutil.which", return_value=None)
    def test_forced_provider_fails_without_fallback_when_clud_missing(
        self, _mock_which
    ):
        with (
            patch("codeup.aicommit.get_git_diff_cached", return_value="diff --git a b"),
            patch("codeup.console.error") as mock_error,
            patch("codeup.aicommit.safe_git_commit") as mock_commit,
        ):
            with self.assertRaises(RuntimeError):
                _opencommit_or_prompt_for_commit_message(
                    auto_accept=True,
                    no_interactive=False,
                    provider="codex",
                )

        mock_commit.assert_not_called()
        self.assertTrue(
            any(
                "Codex CLI commit message generation failed." in call.args[0]
                for call in mock_error.call_args_list
            )
        )


if __name__ == "__main__":
    unittest.main()
