"""Command runner with streaming output and callback support."""

import logging
import os
import shlex

from running_process import RunningProcess
from running_process.output_formatter import NullOutputFormatter

from codeup.git_utils import LintResult, TestResult, interrupt_main

logger = logging.getLogger(__name__)


def run_command_with_callback(
    cmd: list[str],
    on_line=None,
    shell: bool = False,
) -> tuple[int, str, str, bool]:
    """Run a command with streaming output and optional line callback.

    The command output is both streamed to stdout in real-time AND captured
    for return. If a callback is provided, it's called for each output line
    and can return False to stop execution early.

    Args:
        cmd: Command and arguments as list
        on_line: Optional callback (line: str) -> bool. Return False to stop.
        shell: Whether to run in shell mode

    Returns:
        Tuple of (exit_code, stdout, stderr, stopped_early)
    """
    stdout_lines = []
    stopped_early = False

    rp = RunningProcess(
        command=cmd,
        shell=shell,
        auto_run=True,
        check=False,
        output_formatter=NullOutputFormatter(),
    )

    try:
        for line in rp.line_iter(timeout=600.0):  # 10 minute timeout
            # Capture the line
            stdout_lines.append(line)

            # Stream to stdout
            print(line, flush=True)

            # Call callback if provided
            if on_line is not None:
                try:
                    should_continue = on_line(line)
                    if should_continue is False:
                        logger.info("Callback requested early stop")
                        stopped_early = True
                        rp.kill()
                        break
                except KeyboardInterrupt:
                    logger.info("Callback interrupted by user")
                    rp.kill()
                    interrupt_main()
                    raise
                except Exception as e:
                    logger.error(f"Callback raised exception: {e}")
                    stopped_early = True
                    rp.kill()
                    break

    except KeyboardInterrupt:
        logger.info("Command execution interrupted by user")
        rp.kill()
        interrupt_main()
        raise
    except TimeoutError as e:
        logger.error(f"Timeout waiting for process output: {e}")
        rp.kill()
    except Exception as e:
        logger.warning(f"Exception during line iteration: {e}")
        rp.kill()

    rp.wait()
    stdout_text = "\n".join(stdout_lines)
    return rp.returncode or 0, stdout_text, "", stopped_early


def run_lint(on_line=None) -> LintResult:
    """Run ./lint script with optional line callback.

    Args:
        on_line: Optional callback (line: str) -> bool. Return False to stop early.

    Returns:
        LintResult with success status, output, and whether execution stopped early
    """
    try:
        # Check if ./lint exists
        if not os.path.exists("./lint"):
            return LintResult(
                success=False,
                exit_code=1,
                stdout="",
                stderr="",
                stopped_early=False,
                error_message="./lint script not found",
            )

        # Prepare command
        from codeup.utils import _to_exec_str

        cmd = _to_exec_str("./lint", bash=True)
        cmd_parts = shlex.split(cmd)
        logger.debug(f"Running lint with command parts: {cmd_parts}")

        # Run with callback support
        exit_code, stdout, stderr, stopped_early = run_command_with_callback(
            cmd_parts, on_line=on_line, shell=True
        )

        # Determine success
        success = exit_code == 0 and not stopped_early
        error_message = None
        if stopped_early:
            error_message = "Linting stopped early by callback"
        elif exit_code != 0:
            error_message = f"Linting failed with exit code {exit_code}"

        return LintResult(
            success=success,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            stopped_early=stopped_early,
            error_message=error_message or "",
        )

    except KeyboardInterrupt:
        logger.info("run_lint interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error running lint: {e}")
        return LintResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr="",
            stopped_early=False,
            error_message=f"Unexpected error: {e}",
        )


def run_test(on_line=None) -> TestResult:
    """Run ./test script with optional line callback.

    Args:
        on_line: Optional callback (line: str) -> bool. Return False to stop early.

    Returns:
        TestResult with success status, output, and whether execution stopped early
    """
    try:
        # Check if ./test exists
        if not os.path.exists("./test"):
            return TestResult(
                success=False,
                exit_code=1,
                stdout="",
                stderr="",
                stopped_early=False,
                error_message="./test script not found",
            )

        # Prepare command
        from codeup.utils import _to_exec_str

        cmd = _to_exec_str("./test", bash=True)
        cmd_parts = shlex.split(cmd)
        logger.debug(f"Running test with command parts: {cmd_parts}")

        # Run with callback support
        exit_code, stdout, stderr, stopped_early = run_command_with_callback(
            cmd_parts, on_line=on_line, shell=True
        )

        # Determine success
        success = exit_code == 0 and not stopped_early
        error_message = None
        if stopped_early:
            error_message = "Testing stopped early by callback"
        elif exit_code != 0:
            error_message = f"Testing failed with exit code {exit_code}"

        return TestResult(
            success=success,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            stopped_early=stopped_early,
            error_message=error_message or "",
        )

    except KeyboardInterrupt:
        logger.info("run_test interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error running test: {e}")
        return TestResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr="",
            stopped_early=False,
            error_message=f"Unexpected error: {e}",
        )
