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

from running_process import RunningProcess
from running_process.output_formatter import NullOutputFormatter

from codeup.aicommit import ai_commit_or_prompt_for_commit_message
from codeup.args import Args
from codeup.console import error, git_status_summary, info, warning
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
)

# Logger will be configured in main() based on --log flag
logger = logging.getLogger(__name__)

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


def _set_activity_tracker(tracker):
    """Set the global activity tracker."""
    global _activity_tracker
    _activity_tracker = tracker


def _run_command_streaming(
    cmd: list[str],
    shell: bool = False,
    quiet: bool = False,
    capture_output: bool = True,
    output_formatter=None,
) -> tuple[int, str, str]:
    """Run a command with RunningProcess and track activity for timeout."""
    stdout_lines = []

    if output_formatter is None:
        output_formatter = NullOutputFormatter()

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
    os.chdir(str(git_path))

    # Handle --dry-run flag
    if args.dry_run:
        # Determine what to run based on positive flags
        should_run_lint = False
        should_run_test = False

        if args.lint and args.test:
            # Both positive flags specified - run both
            should_run_lint = True
            should_run_test = True
            print("Dry-run mode: Running lint and test scripts only")
        elif args.lint:
            # Only lint flag specified - run only lint
            should_run_lint = True
            print("Dry-run mode: Running lint script only")
        elif args.test:
            # Only test flag specified - run only test
            should_run_test = True
            print("Dry-run mode: Running test script only")
        else:
            # No positive flags - default behavior (run both if not disabled)
            should_run_lint = not args.no_lint
            should_run_test = not args.no_test
            print("Dry-run mode: Running lint and test scripts only")

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

                    print(f"Running: {cmd}")
                    # Run with streaming AND capture for dependency detection
                    rtn, stdout, stderr = _run_command_streaming(
                        cmd_parts,
                        shell=True,
                        quiet=False,  # Stream output in real-time
                        capture_output=True,  # Also capture for dependency checking
                        output_formatter=TimestampOutputFormatter(),
                    )

                    # Check captured output for dependency resolution issues
                    output_text = stdout + stderr
                    if "No solution found when resolving dependencies" in output_text:
                        uv_resolved_dependencies = False

                    if rtn != 0:
                        print("Error: Linting failed.")
                        # Display captured output if linting failed
                        if stderr.strip():
                            print("STDERR:", file=sys.stderr)
                            print(stderr, file=sys.stderr)
                        if stdout.strip():
                            print("STDOUT:")
                            print(stdout)
                        if uv_resolved_dependencies:
                            return 1
                        # In dry-run mode, automatically try dependency refresh without prompting
                        print(
                            "Dry-run mode: automatically running 'uv pip install -e . --refresh'"
                        )
                        for _ in range(3):
                            refresh_rtn = _exec(
                                "uv pip install -e . --refresh", bash=False, die=False
                            )
                            if refresh_rtn == 0:
                                break
                        else:
                            print("Error: uv pip install -e . --refresh failed.")
                            return 1
                except KeyboardInterrupt:
                    logger.info("Dry-run linting interrupted by user")
                    from codeup.git_utils import interrupt_main

                    interrupt_main()
                    raise
                except Exception as e:
                    logger.error(f"Error during dry-run linting: {e}")
                    print(f"Linting error: {e}", file=sys.stderr)
                    return 1

            # Run testing if should run and available
            if should_run_test and os.path.exists("./test"):
                print(TESTING_BANNER, end="")

                test_cmd = "./test" + (" --verbose" if verbose else "")
                test_cmd = _to_exec_str(test_cmd, bash=True)

                print(f"Running: {test_cmd}")
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
                    )
                    if rtn != 0:
                        print("Error: Tests failed.")
                        return 1
                except KeyboardInterrupt:
                    logger.info("Dry-run testing interrupted by user")
                    from codeup.git_utils import interrupt_main

                    interrupt_main()
                    raise
                except Exception as e:
                    logger.error(f"Error during dry-run testing: {e}")
                    print(f"Testing error: {e}", file=sys.stderr)
                    return 1

            print("Dry-run completed successfully")
            return 0

        except KeyboardInterrupt:
            logger.info("Dry-run interrupted by user")
            print("Aborting")
            from codeup.git_utils import interrupt_main

            interrupt_main()
            raise
        except Exception as e:
            logger.error(f"Unexpected error in dry-run mode: {e}")
            print(f"Unexpected error: {e}")
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
            print("Aborting")
            from codeup.git_utils import interrupt_main

            interrupt_main()
            raise
        except Exception as e:
            logger.error(f"Unexpected error in just-ai-commit: {e}")
            print(f"Unexpected error: {e}")
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

                print(f"Running: {cmd}")
                # Run with streaming AND capture for dependency detection
                rtn, stdout, stderr = _run_command_streaming(
                    cmd_parts,
                    shell=True,
                    quiet=False,  # Stream output in real-time
                    capture_output=True,  # Also capture for dependency checking
                    output_formatter=TimestampOutputFormatter(),
                )

                # Check captured output for dependency resolution issues
                output_text = stdout + stderr
                if "No solution found when resolving dependencies" in output_text:
                    uv_resolved_dependencies = False

                if rtn != 0:
                    print("Error: Linting failed.")
                    # Display captured output if linting failed
                    if stderr.strip():
                        print("STDERR:", file=sys.stderr)
                        print(stderr, file=sys.stderr)
                    if stdout.strip():
                        print("STDOUT:")
                        print(stdout)
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
                            "uv pip install -e . --refresh", bash=False, die=False
                        )
                        if refresh_rtn == 0:
                            break
                    else:
                        print("Error: uv pip install -e . --refresh failed.")
                        sys.exit(1)
            except KeyboardInterrupt:
                logger.info("Linting interrupted by user")
                from codeup.git_utils import interrupt_main

                interrupt_main()
                raise
            except Exception as e:
                logger.error(f"Error during linting: {e}")
                print(f"Linting error: {e}", file=sys.stderr)
                sys.exit(1)
        if not args.no_test and os.path.exists("./test"):
            print(TESTING_BANNER, end="")

            test_cmd = "./test" + (" --verbose" if verbose else "")
            test_cmd = _to_exec_str(test_cmd, bash=True)

            print(f"Running: {test_cmd}")
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
                )
                if rtn != 0:
                    print("Error: Tests failed.")
                    sys.exit(1)
            except KeyboardInterrupt:
                logger.info("Testing interrupted by user")
                from codeup.git_utils import interrupt_main

                interrupt_main()
                raise
            except Exception as e:
                logger.error(f"Error during testing: {e}")
                print(f"Testing error: {e}", file=sys.stderr)
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
                print(
                    "No modified tracked files to commit - only untracked files were added."
                )
        else:
            print("Skipping git add and commit - no new changes to commit.")

        if not args.no_push:
            # Fetch latest changes from remote
            print("Fetching latest changes from remote...")
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
                    print(f"Current branch: {current_branch}")
                    print(f"Upstream branch: {upstream_branch}")
                else:
                    # Fallback to main branch behavior
                    target_branch = main_branch
                    print(f"Current branch: {current_branch}")
                    print(f"Main branch: {main_branch} (no upstream tracking)")

                # Skip rebase if we're on the main branch and no upstream is set
                should_skip_rebase = (
                    not upstream_branch and current_branch == main_branch
                )

                if not should_skip_rebase:
                    rebase_needed = check_rebase_needed(target_branch)
                    print(f"Rebase needed: {rebase_needed}")

                    if rebase_needed:
                        remote_ref = (
                            target_branch
                            if target_branch.startswith("origin/")
                            else f"origin/{target_branch}"
                        )
                        print(
                            f"Current branch '{current_branch}' is behind {remote_ref}"
                        )

                        if args.no_interactive:
                            print(
                                f"Non-interactive mode: attempting enhanced safe rebase onto {remote_ref}"
                            )
                            result = enhanced_attempt_rebase(target_branch)

                            if result.success:
                                print(f"Successfully rebased onto {remote_ref}")
                            elif result.had_conflicts:
                                print(
                                    "Error: Rebase failed due to conflicts that need manual resolution"
                                )
                                print("Remote repository has conflicting changes.")
                                print("\nRecovery commands:")
                                for cmd in result.recovery_commands:
                                    print(f"  {cmd}")
                                return 1
                            else:
                                print(f"Error: {result.error_message}")
                                if result.recovery_commands:
                                    print("\nRecovery commands:")
                                    for cmd in result.recovery_commands:
                                        print(f"  {cmd}")
                                return 1
                        else:
                            print(
                                f"Performing enhanced safe rebase onto {remote_ref}..."
                            )

                            # Perform the enhanced rebase
                            result = enhanced_attempt_rebase(target_branch)
                            if result.success:
                                print(f"Successfully rebased onto {remote_ref}")
                            elif result.had_conflicts:
                                print(
                                    "Rebase failed due to conflicts that need manual resolution."
                                )
                                print(
                                    "The repository has been restored to its original state."
                                )
                                print("\nRecovery commands:")
                                for cmd in result.recovery_commands:
                                    print(f"  {cmd}")
                                return 1
                            else:
                                print(f"Rebase failed: {result.error_message}")
                                if result.recovery_commands:
                                    print("\nRecovery commands:")
                                    for cmd in result.recovery_commands:
                                        print(f"  {cmd}")
                                return 1

            # Now attempt the push
            if not safe_push():
                # If push still fails, check if we need to try the enhanced rebase approach
                print("Push failed. Checking if enhanced rebase is needed...")

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
                    print(
                        f"Repository is behind remote - attempting enhanced rebase onto {remote_ref}..."
                    )
                    result = enhanced_attempt_rebase(target_branch)

                    if result.success:
                        print("Enhanced rebase successful, attempting push again...")
                        if safe_push():
                            print("Successfully pushed after enhanced rebase")
                        else:
                            print(
                                "Push failed even after enhanced rebase. Manual intervention required."
                            )
                            return 1
                    else:
                        print(f"Enhanced rebase failed: {result.error_message}")
                        if result.recovery_commands:
                            print("\nRecovery commands:")
                            for cmd in result.recovery_commands:
                                print(f"  {cmd}")
                        return 1
                else:
                    print(
                        "Push failed for non-rebase reasons. Manual intervention required."
                    )
                    return 1
        if args.publish:
            _publish()
    except KeyboardInterrupt:
        logger.info("codeup main function interrupted by user")
        print("Aborting")
        from codeup.git_utils import interrupt_main

        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Unexpected error in codeup main: {e}")
        print(f"Unexpected error: {e}")
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
    """Dump stack traces of all threads to help debug hanging issues."""
    print("\n" + "=" * 80, file=sys.stderr)
    print("TIMEOUT: Dumping stack traces of all threads", file=sys.stderr)
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
        """Handle timeout by checking test output activity every 5 minutes."""
        while True:
            time.sleep(300)  # Check every 5 minutes = 300 seconds

            current_time = time.time()
            time_since_last_activity = current_time - last_activity_time[0]

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
        print("Aborting", file=sys.stderr)
        # Give worker thread a moment to clean up
        worker_thread.join(timeout=1.0)
        return 1


if __name__ == "__main__":
    sys.exit(main())
