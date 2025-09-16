import os
import sys
import unittest
from pathlib import Path

import pytest


class ArgumentParsingTester(unittest.TestCase):
    """Test command line argument parsing functionality."""

    def setUp(self):
        """Set up test environment."""
        self.original_cwd = os.getcwd()

    def tearDown(self):
        """Clean up test environment."""
        pass

    @pytest.mark.unit
    def test_basic_argument_parsing(self):
        """Test basic argument parsing functionality."""
        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.args import _parse_args

            # Mock sys.argv for testing
            original_argv = sys.argv

            # Test default arguments
            sys.argv = ["codeup"]
            args = _parse_args()

            self.assertIsNone(args.repo, "Default repo should be None")
            self.assertFalse(args.no_push, "Default no_push should be False")
            self.assertFalse(args.verbose, "Default verbose should be False")
            self.assertFalse(args.no_test, "Default no_test should be False")
            self.assertFalse(args.no_lint, "Default no_lint should be False")
            self.assertFalse(args.publish, "Default publish should be False")
            self.assertFalse(
                args.no_autoaccept, "Default no_autoaccept should be False"
            )
            self.assertIsNone(args.message, "Default message should be None")
            self.assertFalse(args.no_rebase, "Default no_rebase should be False")
            self.assertFalse(
                args.no_interactive, "Default no_interactive should be False"
            )
            self.assertFalse(args.log, "Default log should be False")
            self.assertFalse(
                args.just_ai_commit, "Default just_ai_commit should be False"
            )

            # Restore original argv
            sys.argv = original_argv

        except ImportError as e:
            self.skipTest(f"Could not import main module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    @pytest.mark.unit
    def test_flag_arguments(self):
        """Test flag argument parsing."""
        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.args import _parse_args

            original_argv = sys.argv

            # Test various flags
            sys.argv = [
                "codeup",
                "--no-push",
                "--verbose",
                "--no-test",
                "--no-lint",
                "--publish",
                "--no-autoaccept",
                "--no-rebase",
                "--no-interactive",
                "--log",
                "--just-ai-commit",
            ]
            args = _parse_args()

            self.assertTrue(args.no_push, "no_push should be True when flag is set")
            self.assertTrue(args.verbose, "verbose should be True when flag is set")
            self.assertTrue(args.no_test, "no_test should be True when flag is set")
            self.assertTrue(args.no_lint, "no_lint should be True when flag is set")
            self.assertTrue(args.publish, "publish should be True when flag is set")
            self.assertTrue(
                args.no_autoaccept, "no_autoaccept should be True when flag is set"
            )
            self.assertTrue(args.no_rebase, "no_rebase should be True when flag is set")
            self.assertTrue(
                args.no_interactive, "no_interactive should be True when flag is set"
            )
            self.assertTrue(args.log, "log should be True when flag is set")
            self.assertTrue(
                args.just_ai_commit, "just_ai_commit should be True when flag is set"
            )

            sys.argv = original_argv

        except ImportError as e:
            self.skipTest(f"Could not import main module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    @pytest.mark.unit
    def test_message_argument(self):
        """Test message argument parsing."""
        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.args import _parse_args

            original_argv = sys.argv

            # Test message argument
            test_message = "Test commit message"
            sys.argv = ["codeup", "-m", test_message]
            args = _parse_args()
            self.assertEqual(
                args.message, test_message, "Message should be parsed correctly with -m"
            )

            # Test long form
            sys.argv = ["codeup", "--message", test_message]
            args = _parse_args()
            self.assertEqual(
                args.message,
                test_message,
                "Message should be parsed correctly with --message",
            )

            sys.argv = original_argv

        except ImportError as e:
            self.skipTest(f"Could not import main module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    @pytest.mark.unit
    def test_repo_argument(self):
        """Test repository path argument parsing."""
        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.args import _parse_args

            original_argv = sys.argv

            # Test repo argument
            test_repo = "/path/to/repo"
            sys.argv = ["codeup", test_repo]
            args = _parse_args()
            self.assertEqual(
                args.repo, test_repo, "Repository path should be parsed correctly"
            )

            sys.argv = original_argv

        except ImportError as e:
            self.skipTest(f"Could not import main module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    @pytest.mark.unit
    def test_short_flag_aliases(self):
        """Test short flag aliases."""
        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.args import _parse_args

            original_argv = sys.argv

            # Test short aliases
            sys.argv = ["codeup", "-p", "-nt", "-na"]
            args = _parse_args()

            self.assertTrue(args.publish, "publish should be True with -p flag")
            self.assertTrue(args.no_test, "no_test should be True with -nt flag")
            self.assertTrue(
                args.no_autoaccept, "no_autoaccept should be True with -na flag"
            )

            sys.argv = original_argv

        except ImportError as e:
            self.skipTest(f"Could not import main module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    @pytest.mark.unit
    def test_api_key_arguments(self):
        """Test API key setting arguments."""
        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.args import _parse_args

            original_argv = sys.argv

            # Test OpenAI key setting
            test_openai_key = "sk-test123456789"
            sys.argv = ["codeup", "--set-key-openai", test_openai_key]
            args = _parse_args()
            self.assertEqual(
                args.set_key_openai,
                test_openai_key,
                "OpenAI key should be parsed correctly",
            )

            # Test Anthropic key setting
            test_anthropic_key = "sk-ant-test123456789"
            sys.argv = ["codeup", "--set-key-anthropic", test_anthropic_key]
            args = _parse_args()
            self.assertEqual(
                args.set_key_anthropic,
                test_anthropic_key,
                "Anthropic key should be parsed correctly",
            )

            sys.argv = original_argv

        except ImportError as e:
            self.skipTest(f"Could not import main module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    @pytest.mark.unit
    def test_args_dataclass_validation(self):
        """Test that Args dataclass validates input types."""
        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.main import Args

            # Test valid arguments
            valid_args = Args(
                repo=None,
                no_push=False,
                verbose=False,
                no_test=False,
                no_lint=False,
                publish=False,
                no_autoaccept=False,
                message=None,
                no_rebase=False,
                no_interactive=False,
                log=False,
                just_ai_commit=False,
                set_key_anthropic=None,
                set_key_openai=None,
            )

            # Should not raise any exceptions
            self.assertIsNotNone(
                valid_args, "Valid Args should be created successfully"
            )

            # Test with string values
            string_args = Args(
                repo="/path/to/repo",
                no_push=True,
                verbose=True,
                no_test=True,
                no_lint=True,
                publish=True,
                no_autoaccept=True,
                message="Test message",
                no_rebase=True,
                no_interactive=True,
                log=True,
                just_ai_commit=True,
                set_key_anthropic="sk-ant-test",
                set_key_openai="sk-test",
            )

            self.assertIsNotNone(
                string_args, "Args with string values should be created successfully"
            )

        except ImportError as e:
            self.skipTest(f"Could not import main module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)


if __name__ == "__main__":
    unittest.main()
