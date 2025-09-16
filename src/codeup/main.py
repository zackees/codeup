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

import openai

from codeup.args import Args
from codeup.git_utils import (
    attempt_rebase,
    check_rebase_needed,
    find_git_directory,
    get_current_branch,
    get_git_diff,
    get_git_diff_cached,
    get_git_status,
    get_main_branch,
    get_untracked_files,
    git_add_all,
    git_add_file,
    git_fetch,
    git_push,
    has_changes_to_commit,
    safe_git_commit,
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


def _get_keyring_api_key() -> Union[str, None]:
    """Get OpenAI API key from system keyring/keystore."""
    try:
        import keyring

        api_key = keyring.get_password("zcmds", "openai_api_key")
        return api_key if api_key else None
    except ImportError as e:
        logger.debug(f"Keyring not available: {e}")
        return None
    except KeyboardInterrupt:
        logger.info("_get_keyring_api_key interrupted by user")
        _thread.interrupt_main()
        return None
    except Exception as e:
        logger.error(f"Error accessing keyring: {e}")
        return None


def _generate_ai_commit_message_anthropic(diff_text: str) -> Union[str, None]:
    """Generate commit message using Anthropic Claude API as fallback."""
    try:
        import anthropic

        from codeup.config import get_anthropic_api_key

        api_key = get_anthropic_api_key()
        if not api_key:
            logger.info("No Anthropic API key found")
            return None

        logger.info("Using Anthropic Claude API for commit message generation")
        client = anthropic.Anthropic(api_key=api_key)

        prompt = f"""You are an expert developer who writes clear, concise commit messages following conventional commit format.

Analyze the following git diff and generate a single line commit message that:
1. Follows conventional commit format (type(scope): description)
2. Uses one of these types: feat, fix, docs, style, refactor, perf, test, chore, ci, build
3. Is under 72 characters
4. Describes the main change concisely
5. Uses imperative mood (e.g., "add", not "added")

Git diff:
```
{diff_text}
```

Respond with only the commit message, nothing else."""

        response = client.messages.create(
            model="claude-3-haiku-20240307",  # Fast and cost-effective model
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )

        if response.content and len(response.content) > 0:
            first_block = response.content[0]
            # Check if it's a text block and has the text attribute
            if hasattr(first_block, "text"):
                commit_message = first_block.text.strip()  # type: ignore
                logger.info(
                    f"Generated Anthropic commit message: {commit_message[:50]}..."
                )
                return commit_message
            else:
                logger.warning("Anthropic API returned non-text content")
                return None
        else:
            logger.warning("Anthropic API returned empty response")
            return None

    except ImportError:
        logger.info("Anthropic library not available")
        return None
    except KeyboardInterrupt:
        logger.info("_generate_ai_commit_message_anthropic interrupted by user")
        _thread.interrupt_main()
        return None
    except Exception as e:
        logger.error(f"Failed to generate Anthropic commit message: {e}")
        return None


def _generate_ai_commit_message() -> Union[str, None]:
    """Generate commit message using OpenAI API with Anthropic fallback."""
    try:
        # Import and use existing OpenAI config system
        from codeup.config import get_openai_api_key

        api_key = get_openai_api_key()

        # Get staged diff
        logger.info("Getting git diff for commit message generation")
        diff_text = get_git_diff_cached()

        if not diff_text:
            # No staged changes, get regular diff
            logger.info("No staged changes, getting regular diff")
            diff_text = get_git_diff()
            if not diff_text:
                logger.warning("No changes found in git diff")
                return None

        logger.info(f"Got diff, length: {len(diff_text)}")

        # Try OpenAI first if we have a key
        if api_key:
            try:
                # Set the API key for OpenAI
                os.environ["OPENAI_API_KEY"] = api_key

                # Force the correct OpenAI API endpoint
                os.environ["OPENAI_BASE_URL"] = "https://api.openai.com/v1"
                os.environ["OPENAI_API_BASE"] = "https://api.openai.com/v1"

                logger.info(f"Using OpenAI API key, length: {len(api_key)}")
                logger.info("Set OpenAI base URL to: https://api.openai.com/v1")

                # Create OpenAI client
                client = openai.OpenAI(api_key=api_key)

                prompt = f"""You are an expert developer who writes clear, concise commit messages following conventional commit format.

Analyze the following git diff and generate a single line commit message that:
1. Follows conventional commit format (type(scope): description)
2. Uses one of these types: feat, fix, docs, style, refactor, perf, test, chore, ci, build
3. Is under 72 characters
4. Describes the main change concisely
5. Uses imperative mood (e.g., "add", not "added")

Git diff:
```
{diff_text}
```

Respond with only the commit message, nothing else."""

                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    temperature=0.3,
                )

                if response.choices and len(response.choices) > 0:
                    content = response.choices[0].message.content
                    commit_message = content.strip() if content else ""
                    logger.info(
                        f"Successfully generated OpenAI commit message: {commit_message[:50]}..."
                    )
                    return commit_message
                else:
                    logger.warning("OpenAI API returned empty response")

            except KeyboardInterrupt:
                logger.info("OpenAI API call interrupted by user")
                _thread.interrupt_main()
                return None
            except Exception as e:
                # Extract cleaner error message from OpenAI exceptions
                error_msg = str(e)
                if "Error code: 401" in error_msg and "Incorrect API key" in error_msg:
                    clean_msg = "Invalid OpenAI API key"
                elif "Error code:" in error_msg and "message" in error_msg:
                    # Try to extract just the message part from OpenAI error
                    try:
                        import re

                        match = re.search(r"'message': '([^']*)'", error_msg)
                        if match:
                            clean_msg = match.group(1)
                        else:
                            clean_msg = (
                                error_msg.split(" - ")[0]
                                if " - " in error_msg
                                else str(e)
                            )
                    except Exception:
                        clean_msg = str(e)
                else:
                    clean_msg = str(e)

                logger.warning(f"OpenAI commit message generation failed: {clean_msg}")
                print(f"OpenAI generation failed: {clean_msg}")

        # Fallback to Anthropic only if we have a key
        from codeup.config import get_anthropic_api_key

        if get_anthropic_api_key():
            logger.info("Trying Anthropic as fallback for commit message generation")
            anthropic_message = _generate_ai_commit_message_anthropic(diff_text)
            if anthropic_message:
                return anthropic_message
        else:
            logger.info("No Anthropic API key found, skipping Anthropic fallback")

        # If both failed
        logger.warning("AI commit message generation failed")
        print("Warning: AI commit message generation failed")
        print("Solutions:")
        print("  - Set OpenAI API key: export OPENAI_API_KEY=your_key")
        print("  - Set Anthropic API key: export ANTHROPIC_API_KEY=your_key")
        print(
            "  - Set keys via config: python -c \"from codeup.config import save_config; save_config({'openai_key': 'your_openai_key', 'anthropic_key': 'your_anthropic_key'})\""
        )
        return None

    except KeyboardInterrupt:
        logger.info("_generate_ai_commit_message interrupted by user")
        _thread.interrupt_main()
        return None
    except Exception as e:
        logger.error(f"Failed to generate AI commit message: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception args: {e.args}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")

        error_msg = str(e)
        print("Error: AI commit message generation failed")
        print(f"Exception: {type(e).__name__}: {error_msg}")
        print("Full traceback:")
        print(traceback.format_exc())

        return None


def _opencommit_or_prompt_for_commit_message(
    auto_accept: bool, no_interactive: bool = False
) -> None:
    """Generate AI commit message or prompt for manual input."""
    # Try to generate AI commit message first
    ai_message = _generate_ai_commit_message()

    if ai_message:
        print(f"Generated commit message: {ai_message}")
        # Always auto-accept AI-generated messages when they succeed
        print("Auto-accepting AI-generated commit message")
        safe_git_commit(ai_message)
        return
    elif no_interactive:
        # In non-interactive mode, fail if AI commit generation fails
        logger.error("AI commit generation failed in non-interactive mode")
        print("Error: Failed to generate AI commit message in non-interactive mode")
        print("This may be due to:")
        print("  - OpenAI API issues or rate limiting")
        print("  - Missing or invalid OpenAI API key")
        print("  - Network connectivity problems")
        print("Solutions:")
        print("  - Run in interactive mode: codeup (without --no-interactive)")
        print("  - Set API key via environment: export OPENAI_API_KEY=your_key")
        print("  - Set API key via imgai: imgai --set-key YOUR_KEY")
        print("  - Set API key via Python config:")
        print(
            "    python -c \"from codeup.config import save_config; save_config({'openai_key': 'your_key'})\""
        )
        raise RuntimeError(
            "AI commit message generation failed in non-interactive terminal"
        )

    # Fall back to manual commit message
    if no_interactive:
        logger.warning(
            "Cannot get manual commit message input in non-interactive mode, using fallback"
        )
        print("Cannot get commit message input in non-interactive mode")
        print("Using generic commit message as fallback...")
        safe_git_commit("chore: automated commit (AI unavailable)")
        return

    try:
        msg = input_with_timeout("Commit message: ", timeout_seconds=300)
        safe_git_commit(msg)
    except (EOFError, InputTimeoutError) as e:
        logger.warning(f"Manual commit message input failed: {e}")
        print(f"Commit message input failed or timed out ({type(e).__name__})")
        print("Using generic commit message as fallback...")
        safe_git_commit("chore: automated commit (input failed)")
        return


def _ai_commit_or_prompt_for_commit_message(
    no_autoaccept: bool, message: Union[str, None] = None, no_interactive: bool = False
) -> None:
    """Generate commit message using AI or prompt for manual input."""
    if message:
        # Use provided commit message directly
        safe_git_commit(message)
    else:
        # Use AI or interactive commit
        _opencommit_or_prompt_for_commit_message(
            auto_accept=not no_autoaccept, no_interactive=no_interactive
        )


# demo help message


def safe_rebase_try() -> bool:
    """Attempt a safe rebase using proper git commands. Returns True if successful or no rebase needed."""
    try:
        # Get the main branch
        main_branch = get_main_branch()
        current_branch = get_current_branch()

        # If we're on the main branch, no rebase needed
        if current_branch == main_branch:
            return True

        # Check if rebase is needed
        if not check_rebase_needed(main_branch):
            print(f"Branch is already up to date with origin/{main_branch}")
            return True

        # Attempt the rebase directly - this will handle conflicts properly
        print(f"Attempting rebase onto origin/{main_branch}...")
        success, had_conflicts = attempt_rebase(main_branch)

        if success:
            print(f"Successfully rebased onto origin/{main_branch}")
            return True
        elif had_conflicts:
            print(
                f"Cannot automatically rebase: conflicts detected with origin/{main_branch}"
            )
            print(
                "Remote repository has conflicting changes that must be manually resolved."
            )
            print(f"Please run: git rebase origin/{main_branch}")
            print("Then resolve any conflicts manually.")
            return False
        else:
            print("Rebase failed for other reasons")
            return False

    except KeyboardInterrupt:
        logger.info("safe_rebase_try interrupted by user")
        _thread.interrupt_main()
        return False
    except Exception as e:
        logger.error(f"Error in safe_rebase_try: {e}")
        print(f"Error during safe rebase attempt: {e}")
        return False


def safe_push() -> bool:
    """Attempt to push safely, with automatic rebase if safe to do so."""
    try:
        # First, try a normal push
        print("Attempting to push to remote...")
        success, stderr = git_push()

        if success:
            print("Successfully pushed to remote")
            return True

        # If normal push failed, check if it's due to non-fast-forward
        stderr_output = stderr.lower()

        if "non-fast-forward" in stderr_output or "rejected" in stderr_output:
            print(
                "Push rejected (non-fast-forward). Repository needs to be updated first."
            )
            print(
                "This indicates the remote branch has changes that need to be integrated."
            )

            # Attempt safe rebase if possible
            if safe_rebase_try():
                # Rebase succeeded, try push again
                print("Rebase successful, attempting push again...")
                success, stderr = git_push()

                if success:
                    print("Successfully pushed to remote after rebase")
                    return True
                else:
                    print(f"Push failed after rebase: {stderr}")
                    return False
            else:
                # Rebase failed or not safe, provide manual instructions
                return False
        else:
            print(f"Push failed: {stderr}")
            return False

    except KeyboardInterrupt:
        logger.info("safe_push interrupted by user")
        _thread.interrupt_main()
        return False
    except Exception as e:
        logger.error(f"Push error: {e}")
        print(f"Push error: {e}")
        return False


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
            _ai_commit_or_prompt_for_commit_message(
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
        _ai_commit_or_prompt_for_commit_message(
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
