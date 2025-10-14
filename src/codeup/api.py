"""
Public API for programmatic access to CodeUp functionality.

This module provides a clean programmatic interface to CodeUp's core features,
allowing other tools and scripts to use CodeUp as a library.
"""

import logging
import sys
from dataclasses import dataclass
from io import StringIO

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LintTestResult:
    """Result from running lint and test operations.

    Attributes:
        success: Whether lint and test both passed
        exit_code: The exit code (0 for success, non-zero for failure)
        lint_passed: Whether linting passed (None if not run)
        test_passed: Whether testing passed (None if not run)
        stdout: Captured stdout output
        stderr: Captured stderr output
        error_message: Human-readable error message if failed
    """

    success: bool
    exit_code: int
    lint_passed: bool | None
    test_passed: bool | None
    stdout: str
    stderr: str
    error_message: str | None


def lint_test(
    verbose: bool = False,
    log_level: str | None = None,
    capture_output: bool = True,
) -> LintTestResult:
    """Run lint and test operations programmatically.

    This function provides programmatic access to the lint-test functionality,
    which runs ./lint and ./test scripts without git operations.

    Args:
        verbose: Enable verbose output
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        capture_output: Whether to capture stdout/stderr (if False, output goes to console)

    Returns:
        LintTestResult with structured information about the run

    Example:
        >>> from codeup.api import lint_test
        >>> result = lint_test(verbose=True)
        >>> if result.success:
        ...     print("Linting and testing passed!")
        ... else:
        ...     print(f"Failed: {result.error_message}")
    """

    # Save original stdout/stderr
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    original_argv = sys.argv.copy()

    # Prepare arguments for dry-run mode
    argv = [sys.argv[0], "--dry-run"]
    if verbose:
        argv.append("--verbose")
    if log_level:
        argv.extend(["--log", log_level])

    stdout_capture = StringIO()
    stderr_capture = StringIO()

    try:
        # Override sys.argv for argument parsing
        sys.argv = argv

        # Capture output if requested
        if capture_output:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture

        # Import and run the main function
        from codeup.main import main

        exit_code = main()

        # Restore original streams
        sys.stdout = original_stdout
        sys.stderr = original_stderr

        # Get captured output
        stdout_text = stdout_capture.getvalue()
        stderr_text = stderr_capture.getvalue()

        # Determine what passed/failed from output
        lint_passed = None
        test_passed = None
        error_message = None

        if exit_code == 0:
            # Success - try to determine what ran
            if "./lint" in stdout_text or "LINTING" in stdout_text:
                lint_passed = True
            if "./test" in stdout_text or "TESTING" in stdout_text:
                test_passed = True
        else:
            # Failure - try to determine what failed
            if "Linting failed" in stdout_text or "Linting failed" in stderr_text:
                lint_passed = False
                error_message = "Linting failed"
            elif "Tests failed" in stdout_text or "Tests failed" in stderr_text:
                test_passed = False
                lint_passed = True  # Lint must have passed to get to tests
                error_message = "Tests failed"
            else:
                error_message = "Unknown failure during lint/test"

        return LintTestResult(
            success=(exit_code == 0),
            exit_code=exit_code,
            lint_passed=lint_passed,
            test_passed=test_passed,
            stdout=stdout_text,
            stderr=stderr_text,
            error_message=error_message,
        )

    except KeyboardInterrupt:
        logger.info("Lint and test interrupted by user")
        return LintTestResult(
            success=False,
            exit_code=130,  # Standard exit code for SIGINT
            lint_passed=None,
            test_passed=None,
            stdout=stdout_capture.getvalue(),
            stderr=stderr_capture.getvalue(),
            error_message="Interrupted by user",
        )
    except Exception as e:
        logger.error(f"Unexpected error during lint and test: {e}")
        return LintTestResult(
            success=False,
            exit_code=1,
            lint_passed=None,
            test_passed=None,
            stdout=stdout_capture.getvalue(),
            stderr=stderr_capture.getvalue(),
            error_message=f"Unexpected error: {e}",
        )
    finally:
        # Always restore original state
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        sys.argv = original_argv


__all__ = [
    "LintTestResult",
    "lint_test",
]
