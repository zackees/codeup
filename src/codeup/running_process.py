"""
Process management utilities for streaming subprocess output.

Migrated and adapted from zackees/clud repository.
"""

import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Union


def stream_and_capture_output(
    process: subprocess.Popen[str], quiet: bool = False
) -> "tuple[int, str, str]":
    """Stream output in real-time while also capturing it."""
    stdout_lines = []
    stderr_lines = []

    try:
        while True:
            if process.poll() is not None:
                break

            # Read and optionally print stdout
            if process.stdout:
                line = process.stdout.readline()
                if line:
                    stdout_lines.append(line)
                    if not quiet:
                        print(line.rstrip(), flush=True)

            # Read and optionally print stderr
            if process.stderr:
                line = process.stderr.readline()
                if line:
                    stderr_lines.append(line)
                    if not quiet:
                        print(line.rstrip(), file=sys.stderr, flush=True)

            time.sleep(0.01)

        # Capture remaining output
        if process.stdout:
            for line in process.stdout:
                stdout_lines.append(line)
                if not quiet:
                    print(line.rstrip(), flush=True)

        if process.stderr:
            for line in process.stderr:
                stderr_lines.append(line)
                if not quiet:
                    print(line.rstrip(), file=sys.stderr, flush=True)

        exit_code = process.wait()
        stdout = "".join(stdout_lines)
        stderr = "".join(stderr_lines)

        return exit_code, stdout, stderr

    except KeyboardInterrupt:
        if not quiet:
            print("\nTerminating process...", file=sys.stderr)
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return 130, "".join(stdout_lines), "".join(stderr_lines)


def stream_process_output(process: subprocess.Popen[str]) -> int:
    """Stream output from a subprocess in real-time."""
    try:
        # Stream stdout and stderr in real-time
        while True:
            # Check if process has terminated
            if process.poll() is not None:
                break

            # Read and print any available output
            if process.stdout:
                line = process.stdout.readline()
                if line:
                    print(line.rstrip(), flush=True)

            if process.stderr:
                line = process.stderr.readline()
                if line:
                    print(line.rstrip(), file=sys.stderr, flush=True)

            # Small delay to prevent busy waiting
            time.sleep(0.01)

        # Get any remaining output
        if process.stdout:
            for line in process.stdout:
                print(line.rstrip(), flush=True)

        if process.stderr:
            for line in process.stderr:
                print(line.rstrip(), file=sys.stderr, flush=True)

        # Wait for process to complete and return exit code
        return process.wait()

    except KeyboardInterrupt:
        print("\nTerminating process...", file=sys.stderr)
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return 130  # Standard exit code for SIGINT


def run_command_with_streaming(
    cmd: List[str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    shell: bool = False,
    encoding: str = "utf-8",
) -> int:
    """
    Run a command with real-time output streaming.

    Args:
        cmd: Command and arguments as a list
        cwd: Working directory for the command
        env: Environment variables
        shell: Whether to use shell

    Returns:
        Exit code of the process
    """
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            cwd=cwd,
            env=env,
            shell=shell,
            encoding=encoding,
            errors="replace",
        )

        return stream_process_output(process)

    except FileNotFoundError as e:
        print(f"Command not found: {' '.join(cmd)}", file=sys.stderr)
        print(f"Error: {e}", file=sys.stderr)
        return 127
    except Exception as e:
        print(f"Error running command: {e}", file=sys.stderr)
        return 1


def run_command_with_streaming_and_capture(
    cmd: List[str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    shell: bool = False,
    quiet: bool = False,
    capture_output: bool = True,
    check: bool = False,
    encoding: str = "utf-8",
) -> "tuple[int, str, str]":
    """
    Run a command with optional streaming and output capture.

    Args:
        cmd: Command and arguments as a list
        cwd: Working directory for the command
        env: Environment variables
        shell: Whether to use shell
        quiet: If True, suppress real-time streaming (for quick operations)
        capture_output: If True, capture and return stdout/stderr
        check: If True, raise CalledProcessError on non-zero exit
        encoding: Text encoding for subprocess

    Returns:
        Tuple of (exit_code, stdout, stderr)
        If capture_output=False, stdout and stderr will be empty strings

    Raises:
        subprocess.CalledProcessError: If check=True and process returns non-zero exit code
    """
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
            bufsize=1,
            universal_newlines=True,
            cwd=cwd,
            env=env,
            shell=shell,
            encoding=encoding,
            errors="replace",
        )

        if capture_output:
            exit_code, stdout, stderr = stream_and_capture_output(process, quiet=quiet)
        else:
            # For non-capturing operations, just stream without capture
            exit_code = stream_process_output(process)
            stdout, stderr = "", ""

        if check and exit_code != 0:
            raise subprocess.CalledProcessError(
                exit_code, cmd, output=stdout, stderr=stderr
            )

        return exit_code, stdout, stderr

    except FileNotFoundError as e:
        print(f"Command not found: {' '.join(cmd)}", file=sys.stderr)
        print(f"Error: {e}", file=sys.stderr)
        return 127, "", str(e)
    except Exception as e:
        print(f"Error running command: {e}", file=sys.stderr)
        return 1, "", str(e)


def run_command_with_timeout(
    cmd: Union[List[str], str],
    timeout: float = 300.0,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    shell: bool = False,
    encoding: str = "utf-8",
) -> int:
    """
    Run a command with a timeout and streaming output.

    Args:
        cmd: Command and arguments as a list, or command string if shell=True
        timeout: Timeout in seconds
        cwd: Working directory for the command
        env: Environment variables
        shell: Whether to use shell

    Returns:
        Exit code of the process
    """
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            cwd=cwd,
            env=env,
            shell=shell,
            encoding=encoding,
            errors="replace",
        )

        # Start streaming in a separate thread
        exit_code = None

        def stream_thread():
            nonlocal exit_code
            exit_code = stream_process_output(process)

        thread = threading.Thread(target=stream_thread)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            # Timeout occurred
            print(f"\nCommand timed out after {timeout} seconds", file=sys.stderr)
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            return 124  # Standard timeout exit code

        return exit_code if exit_code is not None else 1

    except Exception as e:
        print(f"Error running command with timeout: {e}", file=sys.stderr)
        return 1


class ProcessManager:
    """
    A context manager for handling subprocess execution with streaming output.
    """

    def __init__(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        shell: bool = False,
    ):
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self.shell = shell
        self.process: Optional[subprocess.Popen] = None
        self.exit_code: Optional[int] = None

    def __enter__(self) -> "ProcessManager":
        try:
            self.process = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                cwd=self.cwd,
                env=self.env,
                shell=self.shell,
            )
        except Exception as e:
            print(f"Failed to start process: {e}", file=sys.stderr)
            raise
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.process:
            if self.process.poll() is None:
                # Process is still running, terminate it
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()

    def run(self) -> int:
        """Run the process and stream its output."""
        if not self.process:
            raise RuntimeError("Process not started")

        self.exit_code = stream_process_output(self.process)
        return self.exit_code

    def is_running(self) -> bool:
        """Check if the process is still running."""
        return self.process is not None and self.process.poll() is None

    def terminate(self) -> None:
        """Terminate the process gracefully."""
        if self.process and self.is_running():
            self.process.terminate()

    def kill(self) -> None:
        """Force kill the process."""
        if self.process:
            self.process.kill()
