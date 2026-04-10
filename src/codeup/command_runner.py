"""Command runner with streaming output and callback support."""

import logging
import os
import sys

from running_process import RunningProcess
from running_process.compat import PIPE
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
    stderr_lines = []
    stopped_early = False

    from codeup.utils import get_next_process_output, get_process_output_iterator

    rp = RunningProcess(
        command=cmd,
        shell=shell,
        auto_run=True,
        check=False,
        output_formatter=NullOutputFormatter(),
        stderr=PIPE,
    )
    output_iterator = get_process_output_iterator(rp, timeout=1.0)

    try:
        while True:
            try:
                output_batch = get_next_process_output(
                    rp,
                    output_iterator,
                    timeout=1.0,
                )
            except TimeoutError as err:
                from codeup.utils import is_interrupted, process_is_running

                if is_interrupted():
                    rp.kill()
                    raise KeyboardInterrupt("Process interrupted") from err
                if process_is_running(rp):
                    continue
                break

            if output_batch is None:
                break

            for stream_name, line in output_batch:
                if stream_name == "stderr":
                    stderr_lines.append(line)
                else:
                    stdout_lines.append(line)

                output_stream = sys.stderr if stream_name == "stderr" else sys.stdout
                print(line, file=output_stream, flush=True)

                from codeup.utils import is_interrupted

                if is_interrupted():
                    rp.kill()
                    raise KeyboardInterrupt("Process interrupted")

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
                        interrupt_main()
                        rp.kill()
                        raise
                    except Exception as e:
                        logger.error(f"Callback raised exception: {e}")
                        stopped_early = True
                        rp.kill()
                        break

            if stopped_early:
                break

    except KeyboardInterrupt:
        logger.info("Command execution interrupted by user")
        interrupt_main()
        rp.kill()
        raise
    except Exception as e:
        logger.warning(f"Exception during line iteration: {e}")
        rp.kill()

    rp.wait()
    stdout_text = "\n".join(stdout_lines)
    stderr_text = "\n".join(stderr_lines)
    return rp.returncode or 0, stdout_text, stderr_text, stopped_early


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
        from codeup.utils import _to_exec_args

        cmd_parts = _to_exec_args("./lint", bash=True)
        logger.debug(f"Running lint with command parts: {cmd_parts}")

        # Run with callback support
        exit_code, stdout, stderr, stopped_early = run_command_with_callback(
            cmd_parts, on_line=on_line, shell=False
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
        from codeup.utils import _to_exec_args

        cmd_parts = _to_exec_args("./test", bash=True)
        logger.debug(f"Running test with command parts: {cmd_parts}")

        # Run with callback support
        exit_code, stdout, stderr, stopped_early = run_command_with_callback(
            cmd_parts, on_line=on_line, shell=False
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
