"""Command-line argument definitions for codeup."""

import argparse
from dataclasses import dataclass


@dataclass
class Args:
    repo: str | None
    no_push: bool
    verbose: bool
    no_test: bool
    no_lint: bool
    publish: bool
    no_autoaccept: bool
    message: str | None
    no_rebase: bool
    no_interactive: bool
    log: bool
    just_ai_commit: bool
    set_key_anthropic: str | None
    set_key_openai: str | None
    dry_run: bool
    lint: bool
    test: bool
    pre_test: bool

    def __post_init__(self) -> None:
        assert isinstance(
            self.repo, (str, type(None))
        ), f"Expected str, got {type(self.repo)}"
        assert isinstance(
            self.no_push, bool
        ), f"Expected bool, got {type(self.no_push)}"
        assert isinstance(
            self.verbose, bool
        ), f"Expected bool, got {type(self.verbose)}"
        assert isinstance(
            self.no_test, bool
        ), f"Expected bool, got {type(self.no_test)}"
        assert isinstance(
            self.no_lint, bool
        ), f"Expected bool, got {type(self.no_lint)}"
        assert isinstance(
            self.publish, bool
        ), f"Expected bool, got {type(self.publish)}"
        assert isinstance(
            self.no_autoaccept, bool
        ), f"Expected bool, got {type(self.no_autoaccept)}"
        assert isinstance(
            self.message, (str, type(None))
        ), f"Expected str, got {type(self.message)}"
        assert isinstance(
            self.no_rebase, bool
        ), f"Expected bool, got {type(self.no_rebase)}"
        assert isinstance(
            self.no_interactive, bool
        ), f"Expected bool, got {type(self.no_interactive)}"
        assert isinstance(self.log, bool), f"Expected bool, got {type(self.log)}"
        assert isinstance(
            self.just_ai_commit, bool
        ), f"Expected bool, got {type(self.just_ai_commit)}"
        assert isinstance(
            self.set_key_anthropic, (str, type(None))
        ), f"Expected (str, type(None)), got {type(self.set_key_anthropic)}"
        assert isinstance(
            self.set_key_openai, (str, type(None))
        ), f"Expected (str, type(None)), got {type(self.set_key_openai)}"
        assert isinstance(
            self.dry_run, bool
        ), f"Expected bool, got {type(self.dry_run)}"
        assert isinstance(self.lint, bool), f"Expected bool, got {type(self.lint)}"
        assert isinstance(self.test, bool), f"Expected bool, got {type(self.test)}"
        assert isinstance(
            self.pre_test, bool
        ), f"Expected bool, got {type(self.pre_test)}"

    @staticmethod
    def parse_args() -> "Args":
        """Parse command-line arguments and return Args instance."""
        return _parse_args()


def _parse_args() -> Args:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", help="Path to the repo to summarize", nargs="?")
    parser.add_argument(
        "--no-push", help="Do not push after successful commit", action="store_true"
    )
    parser.add_argument(
        "--verbose",
        help="Passes the verbose flag to the linter and tester",
        action="store_true",
    )
    parser.add_argument("--publish", "-p", help="Publish the repo", action="store_true")
    parser.add_argument(
        "--no-test", "-nt", help="Do not run tests", action="store_true"
    )
    parser.add_argument("--no-lint", help="Do not run linter", action="store_true")
    parser.add_argument(
        "--no-autoaccept",
        "-na",
        help="Do not auto-accept commit messages from AI",
        action="store_true",
    )
    parser.add_argument(
        "-m",
        "--message",
        help="Commit message (bypasses AI commit generation)",
        type=str,
    )
    parser.add_argument(
        "--no-rebase",
        help="Do not attempt to rebase before pushing",
        action="store_true",
    )
    parser.add_argument(
        "--no-interactive",
        help="Fail if auto commit message generation fails (non-interactive mode)",
        action="store_true",
    )
    parser.add_argument(
        "--log",
        help="Enable logging to codeup.log file",
        action="store_true",
    )
    parser.add_argument(
        "--just-ai-commit",
        help="Skip linting and testing, just run the automatic AI commit generator",
        action="store_true",
    )
    parser.add_argument(
        "--set-key-anthropic",
        type=str,
        help="Set Anthropic API key and exit",
    )
    parser.add_argument(
        "--set-key-openai",
        type=str,
        help="Set OpenAI API key and exit",
    )
    parser.add_argument(
        "--dry-run",
        help="Run only lint and test scripts without git operations or user interaction",
        action="store_true",
    )
    parser.add_argument(
        "--lint",
        help="When used with --dry-run, run only the lint script",
        action="store_true",
    )
    parser.add_argument(
        "--test",
        help="When used with --dry-run, run only the test script",
        action="store_true",
    )
    parser.add_argument(
        "--pre-test",
        help="Error if there are untracked files (prevents blocking when run as subcommand)",
        action="store_true",
    )
    tmp = parser.parse_args()

    out: Args = Args(
        repo=tmp.repo,
        no_push=tmp.no_push,
        verbose=tmp.verbose,
        no_test=tmp.no_test,
        no_lint=tmp.no_lint,
        publish=tmp.publish,
        no_autoaccept=tmp.no_autoaccept,
        message=tmp.message,
        no_rebase=tmp.no_rebase,
        no_interactive=tmp.no_interactive,
        log=tmp.log,
        just_ai_commit=tmp.just_ai_commit,
        set_key_anthropic=tmp.set_key_anthropic,
        set_key_openai=tmp.set_key_openai,
        dry_run=tmp.dry_run,
        lint=tmp.lint,
        test=tmp.test,
        pre_test=tmp.pre_test,
    )
    return out
