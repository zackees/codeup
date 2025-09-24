"""
Adapter module to bridge the old running_process interface with the new package.
"""

from pathlib import Path
from typing import Any

from running_process import RunningProcess
from running_process.output_formatter import NullOutputFormatter

# Timeout constants
LINE_ITERATION_TIMEOUT = 300.0  # 5 minutes for line iteration


def run_command_with_streaming(
    cmd: str | list[str],
    cwd: str | None = None,
    timeout: int | None = None,
    **kwargs: Any,
) -> int:
    """Run command with streaming output using the new package."""
    try:
        rp = RunningProcess(
            command=cmd,
            cwd=Path(cwd) if cwd else None,
            timeout=timeout,
            auto_run=True,
            check=False,
            output_formatter=NullOutputFormatter(),
        )
    except FileNotFoundError:
        return 127

    # Stream output
    try:
        for line in rp.line_iter(timeout=LINE_ITERATION_TIMEOUT):
            print(line, flush=True)
    except KeyboardInterrupt:
        rp.kill()
        from codeup.git_utils import interrupt_main

        interrupt_main()
        raise
    except Exception as e:
        # Log the exception to understand what's being silently swallowed
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            f"Exception during line iteration (streaming may be affected): {e}"
        )
        # Continue if line iteration times out or has other non-fatal errors
        pass

    # Wait for completion
    rp.wait()
    return rp.returncode or 0


def run_command_with_streaming_and_capture(
    cmd: str | list[str],
    cwd: str | None = None,
    timeout: int | None = None,
    quiet: bool = False,
    raw_output: bool = False,
    capture_output: bool = True,
    **kwargs: Any,
) -> "tuple[int, str, str]":
    """Run command with streaming and capture output.

    Args:
        cmd: Command to execute
        cwd: Working directory
        timeout: Timeout in seconds
        quiet: If True, don't print output to console
        raw_output: Deprecated parameter (all output is now raw without timestamps)
        capture_output: If True, capture output for return value; if False, only stream
        **kwargs: Additional arguments
    """
    stdout_lines = []

    # Use NullOutputFormatter for all commands since git commands are fast
    formatter = NullOutputFormatter()

    rp = RunningProcess(
        command=cmd,
        cwd=Path(cwd) if cwd else None,
        timeout=timeout,
        auto_run=True,
        check=False,
        output_formatter=formatter,
    )

    try:
        for line in rp.line_iter(timeout=LINE_ITERATION_TIMEOUT):
            if capture_output:
                stdout_lines.append(line)
            if not quiet:
                print(line, flush=True)
    except KeyboardInterrupt:
        rp.kill()
        from codeup.git_utils import interrupt_main

        interrupt_main()
        raise
    except Exception as e:
        # Log the exception to understand what's being silently swallowed
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            f"Exception during line iteration (streaming may be affected): {e}"
        )
        # Continue if line iteration times out or has other non-fatal errors
        pass

    # Wait for completion
    rp.wait()

    # The new package merges stderr into stdout, so we'll return stdout for both
    stdout_text = "\n".join(stdout_lines) if capture_output else ""
    stderr_text = ""  # Empty since stderr is merged into stdout

    return rp.returncode or 0, stdout_text, stderr_text


def run_command_with_timeout(
    cmd: str | list[str],
    timeout: int,
    cwd: str | None = None,
    **kwargs: Any,
) -> int:
    """Run command with timeout."""
    return run_command_with_streaming(cmd, cwd=cwd, timeout=timeout, **kwargs)


class ProcessManager:
    """Simple process manager adapter."""

    def __init__(self, cmd: str | list[str], **kwargs: Any):
        self.cmd = cmd
        self.kwargs = kwargs
        self.process: RunningProcess | None = None
        self.exit_code: int | None = None

    def __enter__(self) -> "ProcessManager":
        """Start the process when entering context."""
        self.process = RunningProcess(
            command=self.cmd,
            auto_run=True,
            output_formatter=NullOutputFormatter(),
            **self.kwargs,
        )
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Clean up the process when exiting context."""
        if self.process and not self.process.finished:
            self.process.terminate()

    def is_running(self) -> bool:
        """Check if the process is still running."""
        return self.process is not None and not self.process.finished

    def run(self) -> int:
        """Run the process and wait for completion."""
        if self.process:
            self.process.wait()
            self.exit_code = self.process.returncode or 0
            return self.exit_code
        return 1

    def terminate(self) -> None:
        """Terminate the process."""
        if self.process:
            self.process.terminate()

    def kill(self) -> None:
        """Kill the process."""
        if self.process:
            self.process.kill()
