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

from codeup.aicommit import ai_commit_or_prompt_for_commit_message
from codeup.args import Args
from codeup.git_utils import (
    attempt_rebase,
    check_rebase_needed,
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
from codeup.keyring import set_anthropic_api_key, set_openai_api_key
from codeup.running_process import (
    run_command_with_timeout,
)
from codeup.utils import (
    _exec,
    _publish,
    _to_exec_str,
    check_environment,
    configure_logging,
    get_answer_yes_or_no,
    is_uv_project,
)

# Logger will be configured in main() based on --log flag
logger = logging.getLogger(__name__)


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


IS_UV_PROJECT = is_uv_project()


def main() -> int:
    """Run git status, lint, test, add, and commit."""

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
