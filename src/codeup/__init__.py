"""CodeUp - Intelligent git workflow automation tool."""

__version__ = "1.0.23"

# Import result dataclasses with underscore to keep them private at module level
from .api import LintTestResult as _LintTestResult
from .git_utils import (
    InteractiveAddResult as _InteractiveAddResult,
)
from .git_utils import (
    LintResult as _LintResult,
)
from .git_utils import (
    PreCheckGitResult as _PreCheckGitResult,
)
from .git_utils import (
    TestResult as _TestResult,
)


class Codeup:
    """Stable public API for CodeUp.

    This class provides a stable interface to CodeUp functionality through static methods.
    Internal implementation changes will not affect this API surface.

    All methods are static to ensure the API is stable and predictable.

    Result Types (for type hints):
        LintTestResult: Result from lint_test() operations
        InteractiveAddResult: Result from interactive_add_untracked_files()
        PreCheckGitResult: Result from pre_check_git()
        LintResult: Result from lint()
        TestResult: Result from test()
    """

    # Expose result dataclasses as class attributes for type hints
    LintTestResult = _LintTestResult
    InteractiveAddResult = _InteractiveAddResult
    PreCheckGitResult = _PreCheckGitResult
    LintResult = _LintResult
    TestResult = _TestResult

    # ===== Entry Points =====

    @staticmethod
    def main() -> int:
        """Run the main CodeUp workflow.

        This is the primary entry point that runs the full git workflow:
        - Check git status
        - Run linting (if ./lint exists)
        - Run tests (if ./test exists)
        - Stage changes
        - Generate AI commit message
        - Push to remote (with rebase handling)

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        from .main import main as _main

        return _main()

    # ===== Programmatic API =====

    @staticmethod
    def lint_test(
        verbose: bool = False,
        log_level: str | None = None,
        capture_output: bool = True,
    ):
        """Run lint and/or test scripts programmatically.

        This provides a programmatic interface to run ./lint and ./test scripts
        without the full git workflow. Equivalent to the lint-test command.

        Args:
            verbose: Enable verbose output
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            capture_output: Whether to capture stdout/stderr

        Returns:
            LintTestResult object with success status and any error messages
        """
        from .api import lint_test as _lint_test

        return _lint_test(
            verbose=verbose, log_level=log_level, capture_output=capture_output
        )

    # ===== Git Status Queries =====

    @staticmethod
    def get_untracked_files() -> list[str]:
        """Get list of untracked files in the repository.

        Returns:
            List of file paths that are untracked by git
        """
        from .git_utils import get_untracked_files as _get_untracked_files

        return _get_untracked_files()

    @staticmethod
    def get_staged_files() -> list[str]:
        """Get list of staged files in the repository.

        Returns:
            List of file paths that are staged for commit
        """
        from .git_utils import get_staged_files as _get_staged_files

        return _get_staged_files()

    @staticmethod
    def get_unstaged_files() -> list[str]:
        """Get list of unstaged modified files in the repository.

        Returns:
            List of file paths that have been modified but not staged
        """
        from .git_utils import get_unstaged_files as _get_unstaged_files

        return _get_unstaged_files()

    # ===== Git Operations =====

    @staticmethod
    def git_add_all() -> int:
        """Run 'git add .' to stage all changes.

        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        from .git_utils import git_add_all as _git_add_all

        return _git_add_all()

    @staticmethod
    def interactive_add_untracked_files(
        is_tty: bool = True,
        pre_test_mode: bool = False,
        no_interactive: bool = False,
    ):
        """Interactively add untracked files to git staging area.

        This function encapsulates the full workflow for handling untracked files:
        - Gets list of untracked files
        - Checks for incompatible modes (non-TTY, pre-test)
        - Either auto-adds all files (non-interactive) or prompts for each file

        Args:
            is_tty: Whether running in a terminal (sys.stdin.isatty())
            pre_test_mode: Whether running in pre-test mode (requires all files tracked)
            no_interactive: Whether to auto-add all files without prompting

        Returns:
            InteractiveAddResult with success status, error message, and lists of
            files added and skipped
        """
        from .git_utils import interactive_add_untracked_files as _interactive_add

        return _interactive_add(
            is_tty=is_tty,
            pre_test_mode=pre_test_mode,
            no_interactive=no_interactive,
        )

    @staticmethod
    def pre_check_git(allow_interactive: bool = False):
        """Pre-check git status and optionally prompt for interactive file adds.

        This function checks the current git repository status, including:
        - Untracked files
        - Unstaged changes
        - Staged changes

        When allow_interactive=True, it will prompt the user to add untracked files
        interactively.

        Args:
            allow_interactive: If True, prompt to add untracked files when detected

        Returns:
            PreCheckGitResult with success status, file lists, and change indicators
        """
        from .git_utils import pre_check_git as _pre_check

        return _pre_check(allow_interactive=allow_interactive)

    @staticmethod
    def lint(on_line=None):
        """Run ./lint script with optional line callback for early exit.

        The lint script output is streamed in real-time AND captured for the result.
        An optional callback can be provided to process each line of output and
        optionally stop execution early.

        Args:
            on_line: Optional callback (line: str) -> bool. Return False to stop early.

        Returns:
            LintResult with success status, output, and whether execution stopped early
        """
        from .command_runner import run_lint

        return run_lint(on_line=on_line)

    @staticmethod
    def test(on_line=None):
        """Run ./test script with optional line callback for early exit.

        The test script output is streamed in real-time AND captured for the result.
        An optional callback can be provided to process each line of output and
        optionally stop execution early.

        Args:
            on_line: Optional callback (line: str) -> bool. Return False to stop early.

        Returns:
            TestResult with success status, output, and whether execution stopped early
        """
        from .command_runner import run_test

        return run_test(on_line=on_line)

    # ===== Display Utilities =====

    @staticmethod
    def git_status_summary(
        staged: list[str],
        unstaged: list[str],
        untracked: list[str],
        unpushed_count: int = 0,
        unpushed_files: list[str] | None = None,
    ) -> None:
        """Display a clean, color-coded git status summary.

        Args:
            staged: List of staged file paths
            unstaged: List of unstaged modified file paths
            untracked: List of untracked file paths
            unpushed_count: Number of unpushed commits
            unpushed_files: List of files in unpushed commits
        """
        from .console import git_status_summary as _git_status_summary

        _git_status_summary(
            staged=staged,
            unstaged=unstaged,
            untracked=untracked,
            unpushed_count=unpushed_count,
            unpushed_files=unpushed_files or [],
        )


# Export only the API class
__all__ = ["Codeup"]
