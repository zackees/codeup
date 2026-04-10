"""Utility functions for CodeUp."""

import importlib
import logging
import os
import shlex
import subprocess
import sys
import threading
from pathlib import Path
from shutil import which

from running_process import RunningProcess
from running_process.output_formatter import NullOutputFormatter

from codeup.git_utils import find_git_directory


def _load_running_process_end_of_stream_type():
    """Return the dependency's end-of-stream sentinel when available."""
    try:
        module = importlib.import_module("running_process.process_output_reader")
    except ImportError:  # pragma: no cover - compatibility with older running_process
        return None
    return getattr(module, "EndOfStream", None)


_RunningProcessEndOfStream = _load_running_process_end_of_stream_type()

logger = logging.getLogger(__name__)

# ANSI color codes
RED = "\033[91m"
RESET = "\033[0m"

# Global interrupt flag - set when user presses Ctrl-C
_interrupted = False


def set_interrupted() -> None:
    """Mark that the process has been interrupted by user."""
    global _interrupted
    _interrupted = True


def is_interrupted() -> bool:
    """Check if the process has been interrupted by user."""
    return _interrupted


def process_is_running(process) -> bool:
    """Return whether a RunningProcess-like object is still active.

    The installed running_process package exposes ``poll()``/``finished`` rather than
    ``is_running()``. Keep a compatibility fallback for tests or older wrappers.
    """
    is_running = getattr(process, "is_running", None)
    if callable(is_running):
        return bool(is_running())

    finished = getattr(process, "finished", None)
    if finished is not None:
        return not bool(finished)

    poll = getattr(process, "poll", None)
    if callable(poll):
        return poll() is None

    return False


def is_end_of_stream(process, line) -> bool:
    """Return whether a streamed line is the dependency's end-of-stream sentinel.

    ``running_process`` has shipped two sentinel APIs:
    newer releases return ``process_output_reader.EndOfStream`` directly, while
    some wrappers expose an ``end_of_stream_type`` attribute on the process.
    """
    end_of_stream_type = getattr(process, "end_of_stream_type", None)
    if end_of_stream_type is not None and isinstance(line, end_of_stream_type):
        return True
    if _RunningProcessEndOfStream is not None and isinstance(
        line, _RunningProcessEndOfStream
    ):
        return True
    return False


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


def is_agent_prompt_environment() -> bool:
    """Return True when codeup is likely running under an AI agent wrapper."""
    if os.environ.get("IN_CLUD"):
        return True

    for key, value in os.environ.items():
        if not value:
            continue
        normalized_key = key.upper()
        if normalized_key.startswith("CLAUDE") or normalized_key.startswith("CODEX"):
            return True

    return False


def get_prompt_timeout_seconds() -> int | None:
    """Return the timeout policy for interactive prompts."""
    if not sys.stdin.isatty():
        return 15
    if is_agent_prompt_environment():
        return 120
    return None


def exit_for_missing_user_input() -> None:
    """Exit with a simple message when no prompt answer is provided in time."""
    from codeup.console import error

    error("Exiting because the user didn't give an answer.")
    raise SystemExit(1)


def input_with_timeout(prompt: str, timeout_seconds: int | None = None) -> str:
    """
    Get user input with a timeout. Raises InputTimeoutError if timeout is reached.

    Args:
        prompt: The prompt to display to the user
        timeout_seconds: Timeout in seconds. ``None`` waits indefinitely.

    Returns:
        The user's input string

    Raises:
        InputTimeoutError: If timeout is reached without user input
        EOFError: If input stream is closed
    """
    if timeout_seconds is None:
        timeout_seconds = get_prompt_timeout_seconds()

    result = []
    exception_holder = []

    def get_input():
        try:
            result.append(input(prompt))
        except KeyboardInterrupt:
            from codeup.git_utils import interrupt_main

            set_interrupted()
            interrupt_main()
            raise
        except EOFError:
            if sys.stdin.isatty():
                # EOFError often indicates Ctrl-C on Windows in interactive mode.
                from codeup.git_utils import interrupt_main

                set_interrupted()
                interrupt_main()
                raise KeyboardInterrupt("Input interrupted (EOFError)") from None
            exception_holder.append(EOFError("No input available"))
        except Exception as e:
            exception_holder.append(e)

    # Start input thread
    input_thread = threading.Thread(target=get_input, daemon=True)
    input_thread.start()

    # Poll with short joins so we can respond to Ctrl+C quickly
    import time

    deadline = None if timeout_seconds is None else time.time() + timeout_seconds
    while input_thread.is_alive():
        input_thread.join(timeout=0.2)
        if is_interrupted():
            raise KeyboardInterrupt("Process interrupted")
        if deadline is not None and time.time() >= deadline:
            break

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
    cmd_parts = _to_exec_args(cmd, bash)
    command_display = _to_exec_str(cmd, bash)

    logger.debug(f"Original command: {original_cmd}")
    logger.debug(f"Transformed command: {command_display}")
    logger.debug(f"Bash mode: {bash}")
    logger.debug(f"Command parts: {cmd_parts}")

    try:
        # Set up environment to force color output
        env = os.environ.copy()
        env["FORCE_COLOR"] = "1"
        env["CLICOLOR_FORCE"] = "1"  # For tools that use this variable

        # Use RunningProcess directly for better streaming
        rp = RunningProcess(
            command=cmd_parts,
            shell=False,
            auto_run=True,
            check=False,
            output_formatter=NullOutputFormatter(),
            env=env,
        )

        # Stream output in real-time
        while True:
            try:
                line = rp.get_next_line(timeout=1.0)
            except TimeoutError:
                if is_interrupted():
                    rp.kill()
                    raise KeyboardInterrupt("Process interrupted") from None
                if process_is_running(rp):
                    continue
                break

            if is_end_of_stream(rp, line):
                break

            print(line, flush=True)

            # Check if process was interrupted by Ctrl+C
            if is_interrupted():
                rp.kill()
                raise KeyboardInterrupt("Process interrupted")

        rp.wait()
        rtn = rp.returncode or 0
    except KeyboardInterrupt:
        logger.info("_exec interrupted by user")
        from codeup.git_utils import interrupt_main

        interrupt_main()
        rp.kill()
        raise
    except Exception as e:
        logger.error(f"Error in _exec: {e}")
        rp.kill()  # Kill the process on timeout or other exceptions
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
    return Path(git_dir)


def get_answer_yes_or_no(question: str, default: bool | str = "y") -> bool:
    """Ask a yes/no question and return the answer."""
    # Check if process has been interrupted
    if is_interrupted():
        logger.info("get_answer_yes_or_no: process already interrupted, raising")
        raise KeyboardInterrupt("Process interrupted")

    while True:
        try:
            answer = input_with_timeout(question + " [y/n]: ").lower().strip()
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
            # Check if we're shutting down due to interrupt
            if is_interrupted():
                logger.info("Input failed during shutdown, raising KeyboardInterrupt")
                raise KeyboardInterrupt("Process interrupted") from e

            logger.warning(f"Input failed for yes/no question: {e}")
            exit_for_missing_user_input()


def get_answer_with_choices(
    question: str,
    choices: list[str],
    default: str,
) -> str:
    """Ask a question with explicit choices and return the selected option key."""
    if is_interrupted():
        logger.info("get_answer_with_choices: process already interrupted, raising")
        raise KeyboardInterrupt("Process interrupted")

    normalized_choices = [choice.lower().strip() for choice in choices]
    normalized_default = default.lower().strip()
    if normalized_default not in normalized_choices:
        raise ValueError(
            f"Default choice '{default}' must be one of {normalized_choices}"
        )

    aliases: dict[str, str] = {choice: choice for choice in normalized_choices}
    if "y" in aliases:
        aliases["yes"] = "y"
    if "n" in aliases:
        aliases["no"] = "n"
    if "r" in aliases:
        aliases["remove"] = "r"
    if "k" in aliases:
        aliases["keep"] = "k"
    if "a" in aliases:
        aliases["add"] = "a"

    prompt = f"{question} [{'/'.join(normalized_choices)}]: "

    while True:
        try:
            answer = input_with_timeout(prompt).lower().strip()
            if answer == "":
                return normalized_default
            if answer in aliases:
                return aliases[answer]
            print(f"Please answer with one of: {', '.join(normalized_choices)}.")
        except KeyboardInterrupt:
            from codeup.git_utils import interrupt_main

            interrupt_main()
            raise
        except (EOFError, InputTimeoutError) as e:
            if is_interrupted():
                logger.info(
                    "Choice input failed during shutdown, raising KeyboardInterrupt"
                )
                raise KeyboardInterrupt("Process interrupted") from e

            logger.warning(f"Input failed for choice question: {e}")
            exit_for_missing_user_input()


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
