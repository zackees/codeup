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
import time
import traceback
from dataclasses import dataclass

from running_process import RunningProcess
from running_process.output_formatter import NullOutputFormatter

from codeup.aicommit import ai_commit_or_prompt_for_commit_message
from codeup.args import Args
from codeup.console import dim, error, git_status_summary, info, success, warning
from codeup.git_utils import (
    check_rebase_needed,
    enhanced_attempt_rebase,
    get_current_branch,
    get_main_branch,
    get_staged_files,
    get_unpushed_commit_files,
    get_unstaged_files,
    get_untracked_files,
    get_upstream_branch,
    git_add_all,
    git_add_file,
    git_fetch,
    has_modified_tracked_files,
    has_unpushed_commits,
    safe_push,
)
from codeup.keyring import set_anthropic_api_key, set_openai_api_key
from codeup.timestamp_formatter import TimestampOutputFormatter
from codeup.utils import (
    _exec,
    _publish,
    _to_exec_str,
    check_environment,
    configure_logging,
    format_filename_with_warning,
    get_answer_yes_or_no,
    is_uv_project,
    set_interrupted,
)

# Logger will be configured in main() based on --log flag
logger = logging.getLogger(__name__)


@dataclass
class CommandContext:
    """Context information for currently running command."""

    phase: str  # "LINTING", "TESTING", "DRY_RUN_LINT", etc.
    command_display: str  # Human-readable command
    command_parts: list[str]  # Actual command parts
    start_time: float
    has_pty: bool  # sys.stdin.isatty()


# Banner constants
LINTING_BANNER = """
#########################################
#               LINTING                 #
#########################################

"""

TESTING_BANNER = """
#########################################
#               TESTING                 #
#########################################

"""


# Force UTF-8 encoding for proper international character handling
if sys.platform == "win32":
    import codecs

    # Force UTF-8 encoding for all subprocess operations on Windows
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONLEGACYWINDOWSSTDIO"] = "0"
    # Force unbuffered output for all Python subprocesses to prevent stdout buffering issues
    # when output is piped (prevents multi-second delays in test output)
    os.environ["PYTHONUNBUFFERED"] = "1"

    if sys.stdout.encoding != "utf-8":
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    if sys.stderr.encoding != "utf-8":
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")


IS_UV_PROJECT = is_uv_project()

# Global activity tracker for timeout handling
_activity_tracker = None

# Global command context for timeout diagnostics
_current_command_context = None


def _set_activity_tracker(tracker):
    """Set the global activity tracker."""
    global _activity_tracker
    _activity_tracker = tracker


def _set_current_command_context(context):
    """Set current command context for timeout diagnostics."""
    global _current_command_context
    _current_command_context = context


def _clear_current_command_context():
    """Clear current command context."""
    global _current_command_context
    _current_command_context = None


def _run_command_streaming(
    cmd: list[str],
    shell: bool = False,
    quiet: bool = False,
    capture_output: bool = True,
    output_formatter=None,
    phase: str = "COMMAND",
) -> tuple[int, str, str]:
    """Run a command with RunningProcess and track activity for timeout."""
    stdout_lines = []

    if output_formatter is None:
        output_formatter = NullOutputFormatter()

    # Track command context for timeout diagnostics
    _set_current_command_context(
        CommandContext(
            phase=phase,
            command_display=" ".join(cmd),
            command_parts=cmd,
            start_time=time.time(),
            has_pty=sys.stdin.isatty(),
        )
    )

    rp = RunningProcess(
        command=cmd,
        shell=shell,
        auto_run=True,
        check=False,
        output_formatter=output_formatter,
    )

    try:
        for line in rp.line_iter(
            timeout=600.0
        ):  # 10 minute timeout for long-running builds/tests
            if capture_output:
                stdout_lines.append(line)
            if not quiet:
                print(line, flush=True)

            # Update activity tracker when we receive output
            if _activity_tracker is not None:
                _activity_tracker[0] = time.time()
    except KeyboardInterrupt:
        rp.kill()
        from codeup.git_utils import interrupt_main

        interrupt_main()
        raise
    except TimeoutError as e:
        import traceback

        logger.error(f"Timeout waiting for process output: {e}")
        logger.error(f"Command that timed out: {cmd}")
        logger.error("Stack trace of timeout location:")
        logger.error(traceback.format_exc())
        rp.kill()
    except Exception as e:
        logger.warning(
            f"Exception during line iteration (streaming may be affected): {e}"
        )
        rp.kill()  # Kill the process on timeout or other exceptions

    rp.wait()
    stdout_text = "\n".join(stdout_lines) if capture_output else ""

    # Clear command context after execution
    _clear_current_command_context()

    return rp.returncode or 0, stdout_text, ""


def _main_worker() -> int:
    """Worker function that runs the main codeup logic."""

    args = Args.parse_args()
    configure_logging(args.log)
    verbose = args.verbose

    # Handle key setting flags
    if args.set_key_anthropic:
        if set_anthropic_api_key(args.set_key_anthropic):
            return 0
        else:
            return 1

    if args.set_key_openai:
        if set_openai_api_key(args.set_key_openai):
            return 0
        else:
            return 1

    git_path = check_environment()
    print(f"Git repository: {git_path}", flush=True)
    os.chdir(str(git_path))

    # Handle --dry-run flag
    if args.dry_run:
        print("Starting dry-run mode...", flush=True)
        # Determine what to run based on positive flags
        should_run_lint = False
        should_run_test = False

        if args.lint and args.test:
            # Both positive flags specified - run both
            should_run_lint = True
            should_run_test = True
            print("Dry-run mode: Running lint and test scripts only", flush=True)
        elif args.lint:
            # Only lint flag specified - run only lint
            should_run_lint = True
            print("Dry-run mode: Running lint script only", flush=True)
        elif args.test:
            # Only test flag specified - run only test
            should_run_test = True
            print("Dry-run mode: Running test script only", flush=True)
        else:
            # No positive flags - default behavior (run both if not disabled)
            should_run_lint = not args.no_lint
            should_run_test = not args.no_test
            print("Dry-run mode: Running lint and test scripts only", flush=True)

        try:
            # Run linting if should run and available
            if should_run_lint and os.path.exists("./lint"):
                print(LINTING_BANNER, end="")

                cmd = "./lint" + (" --verbose" if verbose else "")
                cmd = _to_exec_str(cmd, bash=True)

                # Use streaming process that captures output AND streams in real-time
                uv_resolved_dependencies = True
                try:
                    import shlex

                    # Split the command properly for subprocess
                    cmd_parts = shlex.split(cmd)
                    logger.debug(f"Running lint with command parts: {cmd_parts}")

                    dim(f"Running: {cmd}")
                    # Run with streaming AND capture for dependency detection
                    rtn, stdout, stderr = _run_command_streaming(
                        cmd_parts,
                        shell=True,
                        quiet=False,  # Stream output in real-time
                        capture_output=True,  # Also capture for dependency checking
                        output_formatter=TimestampOutputFormatter(),
                        phase="DRY_RUN_LINT",
                    )

                    # Check captured output for dependency resolution issues
                    output_text = stdout + stderr
                    if "No solution found when resolving dependencies" in output_text:
                        uv_resolved_dependencies = False

                    if rtn != 0:
                        error("Linting failed.")
                        # Display captured output if linting failed
                        if stderr.strip():
                            error("STDERR:")
                            print(stderr, file=sys.stderr)
                        if stdout.strip():
                            info("STDOUT:")
                            print(stdout)
                        if uv_resolved_dependencies:
                            return 1
                        # In dry-run mode, automatically try dependency refresh without prompting
                        info(
                            "Dry-run mode: automatically running 'uv pip install -e . --refresh'"
                        )
                        for _ in range(3):
                            refresh_rtn = _exec(
                                "uv pip install -e . --refresh", bash=False, die=False
                            )
                            if refresh_rtn == 0:
                                break
                        else:
                            error("uv pip install -e . --refresh failed.")
                            return 1
                except KeyboardInterrupt:
                    logger.info("Dry-run linting interrupted by user")
                    set_interrupted()
                    from codeup.git_utils import interrupt_main

                    interrupt_main()
                    raise
                except Exception as e:
                    logger.error(f"Error during dry-run linting: {e}")
                    error(f"Linting error: {e}")
                    return 1

            # Run testing if should run and available
            if should_run_test and os.path.exists("./test"):
                print(TESTING_BANNER, end="")

                test_cmd = "./test" + (" --verbose" if verbose else "")
                test_cmd = _to_exec_str(test_cmd, bash=True)

                dim(f"Running: {test_cmd}")
                try:
                    import shlex

                    # Split the command properly for subprocess
                    test_cmd_parts = shlex.split(test_cmd)
                    logger.debug(f"Running test with command parts: {test_cmd_parts}")

                    # Run tests with streaming output (no need to capture for tests)
                    rtn, _, _ = _run_command_streaming(
                        test_cmd_parts,
                        shell=True,
                        quiet=False,  # Stream output in real-time
                        capture_output=False,  # No need to capture test output
                        output_formatter=TimestampOutputFormatter(),
                        phase="DRY_RUN_TEST",
                    )
                    if rtn != 0:
                        error("Tests failed.")
                        return 1
                except KeyboardInterrupt:
                    logger.info("Dry-run testing interrupted by user")
                    set_interrupted()
                    from codeup.git_utils import interrupt_main

                    interrupt_main()
                    raise
                except Exception as e:
                    logger.error(f"Error during dry-run testing: {e}")
                    error(f"Testing error: {e}")
                    return 1

            success("Dry-run completed successfully")
            return 0

        except KeyboardInterrupt:
            logger.info("Dry-run interrupted by user")
            set_interrupted()
            warning("Aborting")
            from codeup.git_utils import interrupt_main

            interrupt_main()
            raise
        except Exception as e:
            logger.error(f"Unexpected error in dry-run mode: {e}")
            error(f"Unexpected error: {e}")
            return 1

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
            set_interrupted()
            warning("Aborting")
            from codeup.git_utils import interrupt_main

            interrupt_main()
            raise
        except Exception as e:
            logger.error(f"Unexpected error in just-ai-commit: {e}")
            error(f"Unexpected error: {e}")
            return 1

    try:
        # Gather git status information
        staged_files = get_staged_files()
        unstaged_files = get_unstaged_files()
        untracked_files = get_untracked_files()
        has_unpushed = has_unpushed_commits()

        # Get unpushed commit count and files for display
        unpushed_count = 0
        unpushed_files = []
        if has_unpushed:
            try:
                upstream_branch = get_upstream_branch()
                if upstream_branch:
                    exit_code, stdout, _ = _run_command_streaming(
                        ["git", "rev-list", "--count", f"{upstream_branch}..HEAD"],
                        quiet=True,
                        phase="GIT_STATUS",
                    )
                    if exit_code == 0:
                        unpushed_count = int(stdout.strip())
                    # Get files in unpushed commits
                    unpushed_files = get_unpushed_commit_files()
            except (KeyboardInterrupt, Exception):
                pass

        # Display clean, color-coded status summary
        git_status_summary(
            staged_files,
            unstaged_files,
            untracked_files,
            unpushed_count,
            unpushed_files,
        )

        # Check if there are any changes to commit
        has_changes = bool(staged_files or unstaged_files or untracked_files)

        if not has_changes and not has_unpushed:
            return 1

        # Special case: unpushed commits without unstaged/untracked changes
        if not has_changes and has_unpushed:
            info("Proceeding with lint/test/push for unpushed commits")
            # Run linting and testing, then push
            # Skip the untracked files check and git add since there are no changes
            has_untracked = False
        else:
            has_untracked = len(untracked_files) > 0

        if has_untracked:
            # Check if running as subprocess (not in PTY) - if so, require all files to be staged
            if not sys.stdin.isatty():
                error("Untracked files detected when running as subprocess")
                error("All files must be staged before running codeup as a subprocess")
                error(
                    "Please stage these files with 'git add' or run codeup interactively"
                )
                return 1
            if args.pre_test:
                # In pre-test mode, error out if there are untracked files
                # This prevents blocking when codeup is called as a subcommand
                error("Untracked files detected in pre-test mode")
                error("Pre-test mode requires all files to be tracked before running")
                error(
                    "Please add these files to git or run codeup without --pre-test flag"
                )
                return 1
            elif args.no_interactive:
                # In non-interactive mode, automatically add all untracked files
                info("Non-interactive mode: automatically adding all untracked files")
                for untracked_file in untracked_files:
                    formatted_name = format_filename_with_warning(untracked_file)
                    info(f"  Adding {formatted_name}")
                    git_add_file(untracked_file)
            else:
                answer_yes = get_answer_yes_or_no("Continue?", "y")
                if not answer_yes:
                    warning("Aborting")
                    return 1
                for untracked_file in untracked_files:
                    formatted_name = format_filename_with_warning(untracked_file)
                    answer_yes = get_answer_yes_or_no(f"  Add {formatted_name}?", "y")
                    if answer_yes:
                        git_add_file(untracked_file)
                    else:
                        info(f"  Skipping {formatted_name}")

        # If pre-test mode and we've gotten this far, all files are tracked - exit successfully
        if args.pre_test:
            success("Pre-test check passed: all files are tracked")
            return 0

        if os.path.exists("./lint") and not args.no_lint:
            print(LINTING_BANNER, end="")

            cmd = "./lint" + (" --verbose" if verbose else "")
            cmd = _to_exec_str(cmd, bash=True)

            # Use streaming process that captures output AND streams in real-time
            uv_resolved_dependencies = True
            try:
                import shlex

                # Split the command properly for subprocess
                cmd_parts = shlex.split(cmd)
                logger.debug(f"Running lint with command parts: {cmd_parts}")

                dim(f"Running: {cmd}")
                # Run with streaming AND capture for dependency detection
                rtn, stdout, stderr = _run_command_streaming(
                    cmd_parts,
                    shell=True,
                    quiet=False,  # Stream output in real-time
                    capture_output=True,  # Also capture for dependency checking
                    output_formatter=TimestampOutputFormatter(),
                    phase="LINTING",
                )

                # Check captured output for dependency resolution issues
                output_text = stdout + stderr
                if "No solution found when resolving dependencies" in output_text:
                    uv_resolved_dependencies = False

                if rtn != 0:
                    error("Linting failed.")
                    # Display captured output if linting failed
                    if stderr.strip():
                        error("STDERR:")
                        print(stderr, file=sys.stderr)
                    if stdout.strip():
                        info("STDOUT:")
                        print(stdout)
                    if uv_resolved_dependencies:
                        sys.exit(1)
                    if args.no_interactive:
                        info(
                            "Non-interactive mode: automatically running 'uv pip install -e . --refresh'"
                        )
                        answer_yes = True
                    else:
                        answer_yes = get_answer_yes_or_no(
                            "'uv pip install -e . --refresh'?",
                            "y",
                        )
                        if not answer_yes:
                            warning("Aborting.")
                            sys.exit(1)
                    for _ in range(3):
                        refresh_rtn = _exec(
                            "uv pip install -e . --refresh", bash=False, die=False
                        )
                        if refresh_rtn == 0:
                            break
                    else:
                        error("uv pip install -e . --refresh failed.")
                        sys.exit(1)
            except KeyboardInterrupt:
                logger.info("Linting interrupted by user")
                set_interrupted()
                from codeup.git_utils import interrupt_main

                interrupt_main()
                raise
            except Exception as e:
                logger.error(f"Error during linting: {e}")
                error(f"Linting error: {e}")
                sys.exit(1)
        if not args.no_test and os.path.exists("./test"):
            print(TESTING_BANNER, end="")

            test_cmd = "./test" + (" --verbose" if verbose else "")
            test_cmd = _to_exec_str(test_cmd, bash=True)

            dim(f"Running: {test_cmd}")
            try:
                import shlex

                # Split the command properly for subprocess
                test_cmd_parts = shlex.split(test_cmd)
                logger.debug(f"Running test with command parts: {test_cmd_parts}")

                # Run tests with streaming output (no need to capture for tests)
                rtn, _, _ = _run_command_streaming(
                    test_cmd_parts,
                    shell=True,
                    quiet=False,  # Stream output in real-time
                    capture_output=False,  # No need to capture test output
                    output_formatter=TimestampOutputFormatter(),
                    phase="TESTING",
                )
                if rtn != 0:
                    error("Tests failed.")
                    sys.exit(1)
            except KeyboardInterrupt:
                logger.info("Testing interrupted by user")
                set_interrupted()
                from codeup.git_utils import interrupt_main

                interrupt_main()
                raise
            except Exception as e:
                logger.error(f"Error during testing: {e}")
                error(f"Testing error: {e}")
                sys.exit(1)

        # Handle git add and commit based on whether we have changes
        if has_changes:
            # Check if there are modified tracked files BEFORE git add
            # This is important because after git add, we can't distinguish between
            # modified tracked files and newly added untracked files
            should_commit = has_modified_tracked_files()

            _exec("git add .", bash=False)

            # Only create a commit if there were modified tracked files before git add
            # (i.e., don't commit if only untracked files were added)
            if should_commit:
                ai_commit_or_prompt_for_commit_message(
                    args.no_autoaccept, args.message, args.no_interactive
                )
            else:
                info(
                    "No modified tracked files to commit - only untracked files were added."
                )
        else:
            info("Skipping git add and commit - no new changes to commit.")

        if not args.no_push:
            # Fetch latest changes from remote
            info("Fetching latest changes from remote...")
            git_fetch()

            # Check if rebase is needed and handle it
            if not args.no_rebase:
                current_branch = get_current_branch()
                upstream_branch = get_upstream_branch()
                main_branch = get_main_branch()

                # Determine the target branch for rebase
                if upstream_branch:
                    # Use the upstream tracking branch if it exists
                    target_branch = upstream_branch
                    info(f"Current branch: {current_branch}")
                    info(f"Upstream branch: {upstream_branch}")
                else:
                    # Fallback to main branch behavior
                    target_branch = main_branch
                    info(f"Current branch: {current_branch}")
                    info(f"Main branch: {main_branch} (no upstream tracking)")

                # Skip rebase if we're on the main branch and no upstream is set
                should_skip_rebase = (
                    not upstream_branch and current_branch == main_branch
                )

                if not should_skip_rebase:
                    rebase_needed = check_rebase_needed(target_branch)
                    info(f"Rebase needed: {rebase_needed}")

                    if rebase_needed:
                        remote_ref = (
                            target_branch
                            if target_branch.startswith("origin/")
                            else f"origin/{target_branch}"
                        )
                        warning(
                            f"Current branch '{current_branch}' is behind {remote_ref}"
                        )

                        if args.no_interactive:
                            info(
                                f"Non-interactive mode: attempting enhanced safe rebase onto {remote_ref}"
                            )
                            result = enhanced_attempt_rebase(target_branch)

                            if result.success:
                                success(f"Successfully rebased onto {remote_ref}")
                            elif result.had_conflicts:
                                error(
                                    "Rebase failed due to conflicts that need manual resolution"
                                )
                                error("Remote repository has conflicting changes.")
                                info("\nRecovery commands:")
                                for cmd in result.recovery_commands:
                                    info(f"  {cmd}")
                                return 1
                            else:
                                error(f"{result.error_message}")
                                if result.recovery_commands:
                                    info("\nRecovery commands:")
                                    for cmd in result.recovery_commands:
                                        info(f"  {cmd}")
                                return 1
                        else:
                            info(
                                f"Performing enhanced safe rebase onto {remote_ref}..."
                            )

                            # Perform the enhanced rebase
                            result = enhanced_attempt_rebase(target_branch)
                            if result.success:
                                success(f"Successfully rebased onto {remote_ref}")
                            elif result.had_conflicts:
                                error(
                                    "Rebase failed due to conflicts that need manual resolution."
                                )
                                warning(
                                    "The repository has been restored to its original state."
                                )
                                info("\nRecovery commands:")
                                for cmd in result.recovery_commands:
                                    info(f"  {cmd}")
                                return 1
                            else:
                                error(f"Rebase failed: {result.error_message}")
                                if result.recovery_commands:
                                    info("\nRecovery commands:")
                                    for cmd in result.recovery_commands:
                                        info(f"  {cmd}")
                                return 1

            # Now attempt the push
            if not safe_push():
                # If push still fails, check if we need to try the enhanced rebase approach
                warning("Push failed. Checking if enhanced rebase is needed...")

                # Refresh the rebase status check after potential changes
                current_branch = get_current_branch()
                upstream_branch = get_upstream_branch()
                main_branch = get_main_branch()

                # Determine the target branch for fallback rebase
                if upstream_branch:
                    target_branch = upstream_branch
                else:
                    target_branch = main_branch

                if check_rebase_needed(target_branch):
                    remote_ref = (
                        target_branch
                        if target_branch.startswith("origin/")
                        else f"origin/{target_branch}"
                    )
                    info(
                        f"Repository is behind remote - attempting enhanced rebase onto {remote_ref}..."
                    )
                    result = enhanced_attempt_rebase(target_branch)

                    if result.success:
                        info("Enhanced rebase successful, attempting push again...")
                        if safe_push():
                            success("Successfully pushed after enhanced rebase")
                        else:
                            error(
                                "Push failed even after enhanced rebase. Manual intervention required."
                            )
                            return 1
                    else:
                        error(f"Enhanced rebase failed: {result.error_message}")
                        if result.recovery_commands:
                            info("\nRecovery commands:")
                            for cmd in result.recovery_commands:
                                info(f"  {cmd}")
                        return 1
                else:
                    error(
                        "Push failed for non-rebase reasons. Manual intervention required."
                    )
                    return 1
        if args.publish:
            _publish()
    except KeyboardInterrupt:
        logger.info("codeup main function interrupted by user")
        set_interrupted()
        warning("Aborting")
        from codeup.git_utils import interrupt_main

        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Unexpected error in codeup main: {e}")
        error(f"Unexpected error: {e}")
        return 1
    return 0


def _is_waiting_for_user_input() -> bool:
    """Detect if any thread is waiting for user input."""
    for thread in threading.enumerate():
        if thread != threading.current_thread() and thread.ident is not None:
            frame = sys._current_frames().get(thread.ident)
            if frame:
                # Check if thread is blocked on input operations
                while frame:
                    # Check for input-related function calls in the stack
                    if frame.f_code.co_name in (
                        "input",
                        "read",
                        "readline",
                        "get_input",
                    ):
                        # Check if it's in our input_with_timeout function
                        if (
                            "input_with_timeout" in frame.f_code.co_filename
                            or "get_answer_yes_or_no" in frame.f_code.co_filename
                        ):
                            return True
                    frame = frame.f_back
    return False


def _dump_all_thread_stacks() -> None:
    """Dump stack traces with prominent command context banner."""

    # Display prominent banner at top with command context
    print("\n" + "╔" + "═" * 77 + "╗", file=sys.stderr)
    print("║" + " " * 23 + "TIMEOUT - PROCESS HUNG" + " " * 32 + "║", file=sys.stderr)
    print("╠" + "═" * 77 + "╣", file=sys.stderr)

    if _current_command_context:
        ctx = _current_command_context
        elapsed = time.time() - ctx.start_time
        elapsed_min = int(elapsed // 60)
        elapsed_sec = int(elapsed % 60)
        elapsed_str = f"{elapsed_min} minutes {elapsed_sec} seconds"

        # Truncate command display if too long
        cmd_display = ctx.command_display
        if len(cmd_display) > 60:
            cmd_display = cmd_display[:57] + "..."

        pty_status = (
            "YES (can prompt user)" if ctx.has_pty else "NO (cannot prompt user)"
        )

        print(f"║ Phase:         {ctx.phase:<60}║", file=sys.stderr)
        print(f"║ Command:       {cmd_display:<60}║", file=sys.stderr)
        print(f"║ Running for:   {elapsed_str:<60}║", file=sys.stderr)
        print(f"║ PTY available: {pty_status:<60}║", file=sys.stderr)
    else:
        print(
            "║ No command context available (not running a command)" + " " * 22 + "║",
            file=sys.stderr,
        )

    print("╠" + "═" * 77 + "╣", file=sys.stderr)
    print(
        "║ Likely cause: Subprocess hung or waiting for input" + " " * 26 + "║",
        file=sys.stderr,
    )
    print("╚" + "═" * 77 + "╝", file=sys.stderr)
    print(file=sys.stderr)

    # Then show thread stacks
    print("=" * 80, file=sys.stderr)
    print("Thread Stack Traces:", file=sys.stderr)
    print("=" * 80, file=sys.stderr)

    for thread_id, frame in sys._current_frames().items():
        thread = None
        for t in threading.enumerate():
            if t.ident == thread_id:
                thread = t
                break

        thread_name = thread.name if thread else f"Thread-{thread_id}"
        print(f"\nThread: {thread_name} (ID: {thread_id})", file=sys.stderr)
        print("-" * 40, file=sys.stderr)

        # Print the stack trace for this thread
        try:
            traceback.print_stack(frame, file=sys.stderr)
        except Exception as e:
            print(f"Error printing stack trace: {e}", file=sys.stderr)

    print("=" * 80, file=sys.stderr)


def main() -> int:
    """Main entry point with 5-minute timeout and non-blocking execution."""

    # Global variable to store the result from the worker thread
    result = [1]  # Default to error exit code

    # Global variable to track the last activity time for test output monitoring
    last_activity_time = [time.time()]

    # Set up the activity tracker
    _set_activity_tracker(last_activity_time)

    def timeout_handler():
        """Handle timeout by checking test output activity, warn at 4 min, timeout at 5 min."""
        warned = False
        while True:
            time.sleep(60)  # Check every minute

            current_time = time.time()
            time_since_last_activity = current_time - last_activity_time[0]

            # Reset warning flag if activity resumed
            if time_since_last_activity < 240 and warned:
                warned = False

            # Warning at 4 minutes of no output
            if time_since_last_activity >= 240 and not warned:
                print(
                    "\n⚠️  WARNING: No output for 4 minutes, will timeout in 1 minute...",
                    file=sys.stderr,
                    flush=True,
                )
                warned = True

            # If no activity for 5 minutes, trigger thread dump and exit
            if time_since_last_activity >= 300:
                # Check if we're waiting for user input
                if _is_waiting_for_user_input():
                    try:
                        logger.error(
                            "Process timed out after 5 minutes while waiting for user input"
                        )
                    except (ValueError, OSError):
                        # Log file may be closed, write directly to stderr
                        pass
                    print(
                        "ERROR: Process timed out after 5 minutes - died while waiting for user input",
                        file=sys.stderr,
                    )
                else:
                    try:
                        logger.error(
                            "Process timed out after 5 minutes of no test output, dumping stack traces"
                        )
                    except (ValueError, OSError) as e:
                        # Log file may be closed, write directly to stderr
                        print(
                            f"Warning: Could not write to log file during timeout: {e}",
                            file=sys.stderr,
                        )
                    print(
                        "ERROR: Process timed out after 5 minutes of no test output",
                        file=sys.stderr,
                    )
                    _dump_all_thread_stacks()

                _thread.interrupt_main()
                os._exit(1)

    def worker_wrapper():
        """Wrapper for the main worker that stores the result."""
        try:
            result[0] = _main_worker()
        except KeyboardInterrupt:
            logger.info("Worker thread interrupted")
            set_interrupted()  # Ensure flag is set
            result[0] = 1
        except Exception as e:
            logger.error(f"Worker thread failed: {e}")
            result[0] = 1

    # Start the timeout handler in a daemon thread
    timeout_thread = threading.Thread(
        target=timeout_handler, daemon=True, name="TimeoutHandler"
    )
    timeout_thread.start()

    # Start the main worker in a separate thread (not daemon - we want to wait for it)
    worker_thread = threading.Thread(
        target=worker_wrapper, name="MainWorker", daemon=False
    )
    worker_thread.start()

    try:
        # Poll the worker thread so we can respond to Ctrl+C immediately
        while worker_thread.is_alive():
            worker_thread.join(timeout=0.1)  # Poll every 100ms
        return result[0]
    except KeyboardInterrupt:
        logger.info("Main thread interrupted by user")
        set_interrupted()  # Signal worker thread to stop
        print("Aborting", file=sys.stderr)
        # Wait briefly for worker to notice interrupt and exit cleanly
        worker_thread.join(timeout=0.5)
        return 1


def lint_test_main() -> int:
    """Entry point for lint-test command - runs lint and test without git operations.

    This is equivalent to 'codeup --dry-run' but provides its own argument parser
    with a simpler interface focused on linting and testing. Output is always streamed.
    """
    from codeup.args import parse_lint_test_args

    # Parse lint-test specific arguments (will handle --help automatically)
    args = parse_lint_test_args()

    # Configure logging based on --log flag
    configure_logging(args.log)

    # Now run the main workflow with these args
    # We need to inject the args into the system so _main_worker can use them
    import sys

    # Save original argv
    original_argv = sys.argv.copy()

    try:
        # Build argv to match what the args represent
        new_argv = [sys.argv[0], "--dry-run"]
        if args.no_test:
            new_argv.append("--no-test")
        if args.no_lint:
            new_argv.append("--no-lint")
        if args.lint:
            new_argv.append("--lint")
        if args.test:
            new_argv.append("--test")
        if args.log:
            new_argv.append("--log")

        sys.argv = new_argv
        return main()
    finally:
        # Restore original argv
        sys.argv = original_argv


if __name__ == "__main__":
    sys.exit(main())
