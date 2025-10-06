"""Utility functions for CodeUp."""

import logging
import os
import shlex
import subprocess
import sys
import threading
import warnings
from pathlib import Path
from shutil import which

from codeup.git_utils import find_git_directory
from codeup.running_process_adapter import run_command_with_streaming

logger = logging.getLogger(__name__)

# ANSI color codes
RED = "\033[91m"
RESET = "\033[0m"


def is_suspicious_file(filename: str) -> bool:
    """Check if a file has a suspicious extension that typically shouldn't be committed.

    Args:
        filename: The filename to check

    Returns:
        True if the file has a suspicious extension
    """
    suspicious_patterns = [
        ".txt",
        ".log",
        ".tmp",
        ".temp",
        ".o",
        ".obj",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".pyc",
        ".pyo",
        ".pyd",
        ".class",
        ".vsproj",
        ".vcxproj",
        ".sln",
        ".suo",
        ".user",
        ".cache",
        ".bak",
        ".swp",
        ".swo",
    ]

    filename_lower = filename.lower()

    # Check for exact extension matches
    for pattern in suspicious_patterns:
        if filename_lower.endswith(pattern):
            return True

    # Check for *tmp*.* pattern (any file with 'tmp' in the name)
    if "tmp" in filename_lower or "temp" in filename_lower:
        return True

    return False


def format_filename_with_warning(filename: str) -> str:
    """Format a filename with red color if it's suspicious.

    Args:
        filename: The filename to format

    Returns:
        The filename, possibly wrapped in ANSI red color codes
    """
    if is_suspicious_file(filename):
        return f"{RED}{filename}{RESET}"
    return filename


class InputTimeoutError(Exception):
    """Raised when input times out."""

    pass


def input_with_timeout(prompt: str, timeout_seconds: int = 300) -> str:
    """
    Get user input with a timeout. Raises InputTimeoutError if timeout is reached.

    Args:
        prompt: The prompt to display to the user
        timeout_seconds: Timeout in seconds (default 5 minutes)

    Returns:
        The user's input string

    Raises:
        InputTimeoutError: If timeout is reached without user input
        EOFError: If input stream is closed
    """
    # Check if we're in a non-interactive environment first
    if not sys.stdin.isatty():
        raise EOFError("No interactive terminal available")

    result = []
    exception_holder = []

    def get_input():
        try:
            result.append(input(prompt))
        except KeyboardInterrupt:
            from codeup.git_utils import interrupt_main

            interrupt_main()
            raise
        except Exception as e:
            exception_holder.append(e)

    # Start input thread
    input_thread = threading.Thread(target=get_input, daemon=True)
    input_thread.start()

    # Wait for either input or timeout
    input_thread.join(timeout=timeout_seconds)

    if input_thread.is_alive():
        # Timeout occurred
        logger.warning(f"Input timed out after {timeout_seconds} seconds")
        raise InputTimeoutError(f"Input timed out after {timeout_seconds} seconds")

    # Check if an exception occurred in the input thread
    if exception_holder:
        raise exception_holder[0]

    # Return the input if successful
    if result:
        return result[0]
    else:
        raise InputTimeoutError("No input received")


def is_uv_project(directory=".") -> bool:
    """
    Detect if the given directory is a uv-managed Python project.

    Args:
        directory (str): Path to the directory to check (default is current directory).

    Returns:
        bool: True if it's a uv project, False otherwise.
    """
    try:
        required_files = ["pyproject.toml", "uv.lock"]
        return all(os.path.isfile(os.path.join(directory, f)) for f in required_files)
    except KeyboardInterrupt:
        logger.info("is_uv_project interrupted by user")
        from codeup.git_utils import interrupt_main

        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error in is_uv_project: {e}")
        print(f"Error: {e}")
        return False


def _find_bash_on_windows() -> str:
    """Find bash executable on Windows by checking common locations.

    Prioritizes Git Bash over WSL bash for better script compatibility.
    """
    # Git Bash locations (prioritized for better script compatibility)
    git_bash_paths = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
        r"C:\Git\bin\bash.exe",
        r"C:\Git\usr\bin\bash.exe",
    ]

    # Check Git Bash locations first
    for path in git_bash_paths:
        if Path(path).exists():
            logger.debug(f"Found Git Bash at: {path}")
            return path

    # Check if bash is in PATH (but exclude WSL if we can detect it)
    bash_path = which("bash")
    if bash_path and "System32" not in bash_path:
        logger.debug(f"Found bash in PATH: {bash_path}")
        return bash_path

    # Other bash locations (MSYS2, etc.)
    other_bash_paths = [
        r"C:\msys64\usr\bin\bash.exe",
        r"C:\msys32\usr\bin\bash.exe",
    ]

    for path in other_bash_paths:
        if Path(path).exists():
            logger.debug(f"Found MSYS2 bash at: {path}")
            return path

    # WSL bash as last resort
    wsl_bash_path = r"C:\Windows\System32\bash.exe"
    if Path(wsl_bash_path).exists():
        logger.debug(f"Using WSL bash as fallback: {wsl_bash_path}")
        return wsl_bash_path

    # Final fallback
    logger.warning("No bash executable found, using 'bash' as fallback")
    return "bash"


def _to_exec_str(cmd: str, bash: bool) -> str:
    """Convert command to properly escaped string for execution.

    Uses subprocess.list2cmdline for secure command building on Windows.

    Args:
        cmd: The command string to execute
        bash: Whether to run via bash shell

    Returns:
        Properly escaped command string
    """
    if bash and sys.platform == "win32":
        bash_exe = _find_bash_on_windows()
        # Use subprocess.list2cmdline for secure string building
        args = [bash_exe, "-c", cmd]
        return subprocess.list2cmdline(args)
    return cmd


def _to_exec_args(cmd: str, bash: bool) -> list[str]:
    """Convert command string to properly escaped argument list for process execution.

    Args:
        cmd: The command string to execute
        bash: Whether to run via bash shell

    Returns:
        List of strings suitable for RunningProcess execution
    """
    if bash and sys.platform == "win32":
        bash_exe = _find_bash_on_windows()
        # Use list of args to avoid shell injection
        return [bash_exe, "-c", cmd]
    else:
        # For non-bash commands, split properly using shlex
        return shlex.split(cmd)


def _exec(cmd: str, bash: bool, die=True) -> int:
    print(f"Running: {cmd}")
    original_cmd = cmd
    cmd = _to_exec_str(cmd, bash)

    logger.debug(f"Original command: {original_cmd}")
    logger.debug(f"Transformed command: {cmd}")
    logger.debug(f"Bash mode: {bash}")

    try:
        # Use our new streaming process management for better reliability
        if bash:
            # For bash commands on Windows, split the command properly for process execution
            cmd_parts = shlex.split(cmd)
            logger.debug(f"Command parts for bash: {cmd_parts}")
            rtn = run_command_with_streaming(cmd_parts, shell=True)
        else:
            # For non-bash commands, split the command properly
            cmd_parts = shlex.split(cmd)
            logger.debug(f"Command parts for non-bash: {cmd_parts}")
            rtn = run_command_with_streaming(cmd_parts)
    except KeyboardInterrupt:
        logger.info("_exec interrupted by user")
        from codeup.git_utils import interrupt_main

        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error in _exec: {e}")
        print(f"Error executing command: {e}", file=sys.stderr)
        rtn = 1

    if rtn != 0:
        print(f"Error: {cmd} returned {rtn}")
        if die:
            sys.exit(1)
    return rtn


def check_environment() -> Path:
    if which("git") is None:
        print("Error: git is not installed.")
        sys.exit(1)
    git_dir = find_git_directory()
    if not git_dir:
        print("Error: .git directory does not exist.")
        sys.exit(1)

    if not which("oco"):
        warnings.warn(
            "opencommit (oco) is not installed. Skipping automatic commit message generation.",
            stacklevel=2,
        )
    return Path(git_dir)


def get_answer_yes_or_no(question: str, default: bool | str = "y") -> bool:
    """Ask a yes/no question and return the answer."""
    # Check if stdin is available
    if not sys.stdin.isatty():
        # No interactive terminal, use default
        result = (
            True
            if (isinstance(default, str) and default.lower() == "y")
            or (isinstance(default, bool) and default)
            else False
        )
        print(f"{question} [y/n]: {'y' if result else 'n'} (auto-selected, no stdin)")
        return result

    while True:
        try:
            answer = (
                input_with_timeout(question + " [y/n]: ", timeout_seconds=300)
                .lower()
                .strip()
            )
            if "y" in answer:
                return True
            if "n" in answer:
                return False
            if answer == "":
                if isinstance(default, bool):
                    return default
                if isinstance(default, str):
                    if default.lower() == "y":
                        return True
                    elif default.lower() == "n":
                        return False
                return True
            print("Please answer 'yes' or 'no'.")
        except KeyboardInterrupt:
            from codeup.git_utils import interrupt_main

            interrupt_main()
            raise
        except (EOFError, InputTimeoutError) as e:
            # No stdin available or timeout, use default
            result = (
                True
                if (isinstance(default, str) and default.lower() == "y")
                or (isinstance(default, bool) and default)
                else False
            )
            logger.warning(f"Input failed for yes/no question: {e}")
            print(
                f"\nInput failed or timed out ({type(e).__name__}), using default: {'y' if result else 'n'}"
            )
            return result


def configure_logging(enable_file_logging: bool) -> None:
    """Configure logging based on whether file logging should be enabled."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if enable_file_logging:
        handlers.append(logging.FileHandler("codeup.log"))

    logging.basicConfig(
        level=logging.INFO,  # Changed from DEBUG to INFO to reduce spam
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,  # Override any existing configuration
    )

    # Reduce verbosity of third-party loggers to prevent debug spam
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)


def _publish() -> None:
    publish_script = "upload_package.sh"
    if not os.path.exists(publish_script):
        print(f"Error: {publish_script} does not exist.")
        sys.exit(1)
    _exec("./upload_package.sh", bash=True)
