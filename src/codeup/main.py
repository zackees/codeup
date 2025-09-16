"""
Runs:
  * git status
  * if there are not changes then exit 1
  * else
    * if ./lint exists, then run it
    * if ./test exists, then run it
    * git add .
    * opencommit (oco)
"""

import _thread
import logging
import os
import sys
import threading
import warnings
from pathlib import Path
from shutil import which
from typing import List, Union

from codeup.aicommit import ai_commit_or_prompt_for_commit_message
from codeup.args import Args
from codeup.git_utils import (
    attempt_rebase,
    check_rebase_needed,
    find_git_directory,
    get_current_branch,
    get_git_status,
    get_main_branch,
    get_untracked_files,
    git_add_all,
    git_add_file,
    git_fetch,
    has_changes_to_commit,
    safe_push,
)
from codeup.running_process import (
    run_command_with_streaming,
    run_command_with_timeout,
)

# Logger will be configured in main() based on --log flag
logger = logging.getLogger(__name__)


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
            import _thread

            _thread.interrupt_main()
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


# Force UTF-8 encoding for proper international character handling
if sys.platform == "win32":
    import codecs

    # Force UTF-8 encoding for all subprocess operations on Windows
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONLEGACYWINDOWSSTDIO"] = "0"

    if sys.stdout.encoding != "utf-8":
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    if sys.stderr.encoding != "utf-8":
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")


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
        _thread.interrupt_main()
        return False
    except Exception as e:
        logger.error(f"Error in is_uv_project: {e}")
        print(f"Error: {e}")
        return False


IS_UV_PROJECT = is_uv_project()

# Example usage
if __name__ == "__main__":
    if is_uv_project():
        print("This is a uv project.")
    else:
        print("This is not a uv project.")


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
    import subprocess

    if bash and sys.platform == "win32":
        bash_exe = _find_bash_on_windows()
        # Use subprocess.list2cmdline for secure string building
        args = [bash_exe, "-c", cmd]
        return subprocess.list2cmdline(args)
    return cmd


def _to_exec_args(cmd: str, bash: bool) -> List[str]:
    """Convert command string to properly escaped argument list for subprocess.

    Args:
        cmd: The command string to execute
        bash: Whether to run via bash shell

    Returns:
        List of strings suitable for subprocess execution
    """
    if bash and sys.platform == "win32":
        bash_exe = _find_bash_on_windows()
        # Use list of args to avoid shell injection
        return [bash_exe, "-c", cmd]
    else:
        # For non-bash commands, split properly using shlex
        import shlex

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
            # For bash commands on Windows, split the command properly for subprocess
            import shlex

            cmd_parts = shlex.split(cmd)
            logger.debug(f"Command parts for bash: {cmd_parts}")
            rtn = run_command_with_streaming(cmd_parts, shell=True)
        else:
            # For non-bash commands, split the command properly
            import shlex

            cmd_parts = shlex.split(cmd)
            logger.debug(f"Command parts for non-bash: {cmd_parts}")
            rtn = run_command_with_streaming(cmd_parts)
    except KeyboardInterrupt:
        logger.info("_exec interrupted by user")
        _thread.interrupt_main()
        return 130
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


def get_answer_yes_or_no(question: str, default: Union[bool, str] = "y") -> bool:
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
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if enable_file_logging:
        handlers.append(logging.FileHandler("codeup.log"))

    logging.basicConfig(
        level=logging.DEBUG,  # Changed to DEBUG for troubleshooting
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,  # Override any existing configuration
    )

    # Reduce verbosity of third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _publish() -> None:
    publish_script = "upload_package.sh"
    if not os.path.exists(publish_script):
        print(f"Error: {publish_script} does not exist.")
        sys.exit(1)
    _exec("./upload_package.sh", bash=True)


# demo help message


def main() -> int:
    """Run git status, lint, test, add, and commit."""

    args = Args.parse_args()
    configure_logging(args.log)
    verbose = args.verbose

    # Handle key setting flags
    if args.set_key_anthropic:
        try:
            import keyring

            keyring.set_password("zcmds", "anthropic_api_key", args.set_key_anthropic)
            print("Anthropic API key stored in system keyring")
            return 0
        except ImportError as e:
            logger.warning(f"Keyring not available for Anthropic key: {e}")
            print("Error: keyring not available. Install with: pip install keyring")
            return 1
        except Exception as e:
            logger.error(f"Error storing Anthropic key: {e}")
            print(f"Error storing Anthropic key: {e}")
            return 1

    if args.set_key_openai:
        try:
            import keyring

            keyring.set_password("zcmds", "openai_api_key", args.set_key_openai)
            print("OpenAI API key stored in system keyring")
            return 0
        except ImportError as e:
            logger.warning(f"Keyring not available for OpenAI key: {e}")
            print("Error: keyring not available. Install with: pip install keyring")
            return 1
        except Exception as e:
            logger.error(f"Error storing OpenAI key: {e}")
            print(f"Error storing OpenAI key: {e}")
            return 1

    git_path = check_environment()
    os.chdir(str(git_path))

    # Handle --just-ai-commit flag
    if args.just_ai_commit:
        try:
            # Just run the AI commit workflow
            git_add_all()
            ai_commit_or_prompt_for_commit_message(
                args.no_autoaccept, args.message, no_interactive=False
            )
            return 0
        except KeyboardInterrupt:
            logger.info("just-ai-commit interrupted by user")
            print("Aborting")
            _thread.interrupt_main()
            return 1
        except Exception as e:
            logger.error(f"Unexpected error in just-ai-commit: {e}")
            print(f"Unexpected error: {e}")
            return 1

    try:
        git_status_str = get_git_status()
        print(git_status_str)

        # Check if there are any changes to commit
        if not has_changes_to_commit():
            print("No changes to commit, working tree clean.")
            return 1

        untracked_files = get_untracked_files()
        has_untracked = len(untracked_files) > 0
        if has_untracked:
            print("There are untracked files.")
            if args.no_interactive:
                # In non-interactive mode, automatically add all untracked files
                print("Non-interactive mode: automatically adding all untracked files.")
                for untracked_file in untracked_files:
                    print(f"  Adding {untracked_file}")
                    git_add_file(untracked_file)
            else:
                answer_yes = get_answer_yes_or_no("Continue?", "y")
                if not answer_yes:
                    print("Aborting.")
                    return 1
                for untracked_file in untracked_files:
                    answer_yes = get_answer_yes_or_no(f"  Add {untracked_file}?", "y")
                    if answer_yes:
                        git_add_file(untracked_file)
                    else:
                        print(f"  Skipping {untracked_file}")
        if os.path.exists("./lint") and not args.no_lint:
            cmd = "./lint" + (" --verbose" if verbose else "")
            cmd = _to_exec_str(cmd, bash=True)

            # Use our new streaming process with timeout
            uv_resolved_dependencies = True
            try:
                # Capture output to check for dependency resolution issues
                import io
                import shlex

                # Redirect stdout temporarily to capture output
                original_stdout = sys.stdout
                output_capture = io.StringIO()

                class TeeOutput:
                    def __init__(self, *files):
                        self.files = files

                    def write(self, obj):
                        for f in self.files:
                            f.write(obj)
                            f.flush()

                    def flush(self):
                        for f in self.files:
                            f.flush()

                sys.stdout = TeeOutput(original_stdout, output_capture)

                # Split the command properly for subprocess
                cmd_parts = shlex.split(cmd)
                logger.debug(f"Running lint with command parts: {cmd_parts}")

                # Run with 300 second (5 minute) timeout
                rtn = run_command_with_timeout(cmd_parts, timeout=300.0, shell=True)

                # Restore stdout and check output
                sys.stdout = original_stdout
                output_text = output_capture.getvalue()

                if "No solution found when resolving dependencies" in output_text:
                    uv_resolved_dependencies = False

                if rtn != 0:
                    print("Error: Linting failed.")
                    if uv_resolved_dependencies:
                        sys.exit(1)
                    if args.no_interactive:
                        print(
                            "Non-interactive mode: automatically running 'uv pip install -e . --refresh'"
                        )
                        answer_yes = True
                    else:
                        answer_yes = get_answer_yes_or_no(
                            "'uv pip install -e . --refresh'?",
                            "y",
                        )
                        if not answer_yes:
                            print("Aborting.")
                            sys.exit(1)
                    for _ in range(3):
                        refresh_rtn = _exec(
                            "uv pip install -e . --refresh", bash=True, die=False
                        )
                        if refresh_rtn == 0:
                            break
                    else:
                        print("Error: uv pip install -e . --refresh failed.")
                        sys.exit(1)
            except KeyboardInterrupt:
                logger.info("Linting interrupted by user")
                _thread.interrupt_main()
                sys.exit(1)
            except Exception as e:
                logger.error(f"Error during linting: {e}")
                print(f"Linting error: {e}", file=sys.stderr)
                sys.exit(1)
        if not args.no_test and os.path.exists("./test"):
            test_cmd = "./test" + (" --verbose" if verbose else "")
            test_cmd = _to_exec_str(test_cmd, bash=True)

            print(f"Running: {test_cmd}")
            try:
                # Run tests with 300 second (5 minute) timeout
                rtn = run_command_with_timeout(test_cmd, timeout=300.0, shell=True)
                if rtn != 0:
                    print("Error: Tests failed.")
                    sys.exit(1)
            except KeyboardInterrupt:
                logger.info("Testing interrupted by user")
                _thread.interrupt_main()
                sys.exit(1)
            except Exception as e:
                logger.error(f"Error during testing: {e}")
                print(f"Testing error: {e}", file=sys.stderr)
                sys.exit(1)
        _exec("git add .", bash=False)
        ai_commit_or_prompt_for_commit_message(
            args.no_autoaccept, args.message, args.no_interactive
        )

        if not args.no_push:
            # Fetch latest changes from remote
            print("Fetching latest changes from remote...")
            git_fetch()

            # Check if rebase is needed and handle it
            if not args.no_rebase:
                main_branch = get_main_branch()
                current_branch = get_current_branch()

                if current_branch != main_branch and check_rebase_needed(main_branch):
                    print(
                        f"Current branch '{current_branch}' is behind origin/{main_branch}"
                    )

                    if args.no_interactive:
                        print(
                            f"Non-interactive mode: attempting automatic rebase onto origin/{main_branch}"
                        )
                        success, had_conflicts = attempt_rebase(main_branch)
                        if success:
                            print(f"Successfully rebased onto origin/{main_branch}")
                        elif had_conflicts:
                            print(
                                "Error: Rebase failed due to conflicts that need manual resolution"
                            )
                            print(f"Please run: git rebase origin/{main_branch}")
                            print(
                                "Then resolve any conflicts manually and re-run codeup"
                            )
                            return 1
                        else:
                            print("Error: Rebase failed for unknown reasons")
                            return 1
                    else:
                        proceed = get_answer_yes_or_no(
                            f"Attempt rebase onto origin/{main_branch}?", "y"
                        )
                        if not proceed:
                            print("Skipping rebase.")
                            return 1

                        # Perform the rebase
                        success, had_conflicts = attempt_rebase(main_branch)
                        if success:
                            print(f"Successfully rebased onto origin/{main_branch}")
                        elif had_conflicts:
                            print(
                                "Rebase failed due to conflicts. Please resolve conflicts manually and try again."
                            )
                            print(f"Run: git rebase origin/{main_branch}")
                            print("Then resolve conflicts and re-run codeup")
                            return 1
                        else:
                            print("Rebase failed for other reasons")
                            return 1

            # Now attempt the push
            if not safe_push():
                print("Push failed. You may need to resolve conflicts manually.")
                return 1
        if args.publish:
            _publish()
    except KeyboardInterrupt:
        logger.info("codeup main function interrupted by user")
        print("Aborting")
        _thread.interrupt_main()
        return 1
    except Exception as e:
        logger.error(f"Unexpected error in codeup main: {e}")
        print(f"Unexpected error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    main()
