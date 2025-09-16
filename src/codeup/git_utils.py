"""Git utility functions for codeup."""

import _thread
import logging
import os
import sys
from typing import List, Tuple

from codeup.running_process import run_command_with_streaming_and_capture

logger = logging.getLogger(__name__)


def safe_git_commit(message: str) -> int:
    """Safely execute git commit with proper UTF-8 encoding."""
    try:
        print(f'Running: git commit -m "{message}"')
        exit_code, _, _ = run_command_with_streaming_and_capture(
            ["git", "commit", "-m", message],
            capture_output=False,  # Let output go to console directly
        )
        if exit_code != 0:
            print(f"Error: git commit returned {exit_code}")
        return exit_code
    except KeyboardInterrupt:
        logger.info("safe_git_commit interrupted by user")
        _thread.interrupt_main()
        return 130
    except Exception as e:
        logger.error(f"Error in safe_git_commit: {e}")
        print(f"Error executing git commit: {e}", file=sys.stderr)
        return 1


def get_git_status() -> str:
    """Get git status output."""
    exit_code, stdout, stderr = run_command_with_streaming_and_capture(
        ["git", "status"], quiet=True, check=True
    )
    return stdout


def get_git_diff_cached() -> str:
    """Get staged changes diff."""
    try:
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "diff", "--cached"],
            quiet=True,
            check=True,
        )
        return stdout.strip()
    except KeyboardInterrupt:
        logger.info("get_git_diff_cached interrupted by user")
        _thread.interrupt_main()
        return ""
    except Exception as e:
        logger.error(f"Error getting staged diff: {e}")
        return ""


def get_git_diff() -> str:
    """Get unstaged changes diff."""
    try:
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "diff"],
            quiet=True,
            check=True,
        )
        return stdout.strip()
    except KeyboardInterrupt:
        logger.info("get_git_diff interrupted by user")
        _thread.interrupt_main()
        return ""
    except Exception as e:
        logger.error(f"Error getting diff: {e}")
        return ""


def get_staged_files() -> List[str]:
    """Get list of staged file names."""
    try:
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "diff", "--cached", "--name-only"],
            quiet=True,
            check=True,
        )
        return [f.strip() for f in stdout.splitlines() if f.strip()]
    except KeyboardInterrupt:
        logger.info("get_staged_files interrupted by user")
        _thread.interrupt_main()
        return []
    except Exception as e:
        logger.error(f"Error getting staged files: {e}")
        return []


def get_unstaged_files() -> List[str]:
    """Get list of unstaged file names."""
    try:
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "diff", "--name-only"],
            quiet=True,
            check=True,
        )
        return [f.strip() for f in stdout.splitlines() if f.strip()]
    except KeyboardInterrupt:
        logger.info("get_unstaged_files interrupted by user")
        _thread.interrupt_main()
        return []
    except Exception as e:
        logger.error(f"Error getting unstaged files: {e}")
        return []


def get_untracked_files() -> List[str]:
    """Get list of untracked files."""
    exit_code, stdout, stderr = run_command_with_streaming_and_capture(
        ["git", "ls-files", "--others", "--exclude-standard"],
        quiet=True,
        check=True,
    )
    return [f.strip() for f in stdout.splitlines() if f.strip()]


def get_main_branch() -> str:
    """Get the main branch name (main, master, etc.)."""
    try:
        # Try to get the default branch from remote
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            quiet=True,
        )
        if exit_code == 0:
            return stdout.strip().split("/")[-1]
    except KeyboardInterrupt:
        logger.info("get_main_branch interrupted by user")
        _thread.interrupt_main()
        return "main"
    except Exception as e:
        logger.error(f"Error getting main branch: {e}")
        pass

    # Fallback: check common branch names
    for branch in ["main", "master"]:
        try:
            exit_code, stdout, stderr = run_command_with_streaming_and_capture(
                ["git", "rev-parse", "--verify", f"origin/{branch}"],
                quiet=True,
            )
            if exit_code == 0:
                return branch
        except KeyboardInterrupt:
            logger.info("get_main_branch loop interrupted by user")
            _thread.interrupt_main()
            return "main"
        except Exception as e:
            logger.error(f"Error checking branch {branch}: {e}")
            continue

    return "main"  # Default fallback


def get_current_branch() -> str:
    """Get the current branch name."""
    exit_code, stdout, stderr = run_command_with_streaming_and_capture(
        ["git", "branch", "--show-current"],
        quiet=True,
        check=True,
    )
    return stdout.strip()


def get_remote_branch_hash(main_branch: str) -> str:
    """Get the hash of the remote main branch."""
    try:
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "rev-parse", f"origin/{main_branch}"],
            quiet=True,
            check=True,
        )
        return stdout.strip()
    except KeyboardInterrupt:
        logger.info("get_remote_branch_hash interrupted by user")
        _thread.interrupt_main()
        return ""
    except Exception as e:
        logger.error(f"Error getting remote branch hash: {e}")
        return ""


def get_merge_base(main_branch: str) -> str:
    """Get the merge base between HEAD and the remote main branch."""
    try:
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "merge-base", "HEAD", f"origin/{main_branch}"],
            quiet=True,
            check=True,
        )
        return stdout.strip()
    except KeyboardInterrupt:
        logger.info("get_merge_base interrupted by user")
        _thread.interrupt_main()
        return ""
    except Exception as e:
        logger.error(f"Error getting merge base: {e}")
        return ""


def check_rebase_needed(main_branch: str) -> bool:
    """Check if current branch is behind the remote main branch."""
    try:
        remote_hash = get_remote_branch_hash(main_branch)
        merge_base = get_merge_base(main_branch)
        return merge_base != remote_hash
    except KeyboardInterrupt:
        logger.info("check_rebase_needed interrupted by user")
        _thread.interrupt_main()
        return False
    except Exception as e:
        logger.error(f"Error checking rebase needed: {e}")
        return False


def attempt_rebase(main_branch: str) -> Tuple[bool, bool]:
    """
    Attempt a rebase and handle conflicts properly.

    Returns:
        Tuple[bool, bool]: (success, had_conflicts)
        - success: True if rebase completed successfully
        - had_conflicts: True if conflicts were encountered (and rebase was aborted)
    """
    try:
        # Attempt the actual rebase
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "rebase", f"origin/{main_branch}"],
            quiet=True,
        )

        if exit_code == 0:
            # Rebase succeeded
            logger.info(f"Successfully rebased onto origin/{main_branch}")
            return True, False
        else:
            # Rebase failed, check if it's due to conflicts
            stderr_lower = stderr.lower()
            stdout_lower = stdout.lower()

            if (
                "conflict" in stderr_lower
                or "conflict" in stdout_lower
                or "failed to merge" in stderr_lower
                or "failed to merge" in stdout_lower
            ):
                logger.info("Rebase failed due to conflicts, aborting rebase")
                # Abort the rebase to return to clean state
                abort_exit_code, abort_stdout, abort_stderr = (
                    run_command_with_streaming_and_capture(
                        ["git", "rebase", "--abort"],
                        quiet=True,
                    )
                )

                if abort_exit_code != 0:
                    logger.error(f"Failed to abort rebase: {abort_stderr}")
                    print(
                        f"Error: Failed to abort rebase: {abort_stderr}",
                        file=sys.stderr,
                    )

                return False, True
            else:
                # Rebase failed for other reasons
                logger.error(f"Rebase failed: {stderr}")
                print(f"Rebase failed: {stderr}", file=sys.stderr)
                return False, False

    except KeyboardInterrupt:
        logger.info("attempt_rebase interrupted by user")
        _thread.interrupt_main()
        return False, False
    except Exception as e:
        logger.error(f"Error attempting rebase: {e}")
        print(f"Error attempting rebase: {e}", file=sys.stderr)
        return False, False


def git_push() -> Tuple[bool, str]:
    """
    Attempt git push.

    Returns:
        Tuple[bool, str]: (success, error_message)
    """
    try:
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "push"],
            quiet=True,
        )
        return exit_code == 0, stderr
    except KeyboardInterrupt:
        logger.info("git_push interrupted by user")
        _thread.interrupt_main()
        return False, "Interrupted by user"
    except Exception as e:
        logger.error(f"Error during git push: {e}")
        return False, str(e)


def has_changes_to_commit() -> bool:
    """Check if there are any changes (staged, unstaged, or untracked) to commit."""
    try:
        # Check for staged changes
        staged_files = get_staged_files()
        if staged_files:
            return True

        # Check for unstaged changes
        unstaged_files = get_unstaged_files()
        if unstaged_files:
            return True

        # Check for untracked files
        untracked_files = get_untracked_files()
        if untracked_files:
            return True

        return False

    except KeyboardInterrupt:
        logger.info("has_changes_to_commit interrupted by user")
        _thread.interrupt_main()
        return False
    except Exception as e:
        logger.error(f"Error checking for changes: {e}")
        return False


def find_git_directory() -> str:
    """Traverse up to 3 levels to find a directory with a .git folder."""
    current_dir = os.getcwd()
    for _ in range(3):
        if os.path.exists(os.path.join(current_dir, ".git")):
            return current_dir
        parent_dir = os.path.dirname(current_dir)
        if current_dir == parent_dir:
            break
        current_dir = parent_dir
    return ""


def git_add_all() -> int:
    """Run 'git add .' command."""
    try:
        print("Running: git add .")
        exit_code, _, _ = run_command_with_streaming_and_capture(
            ["git", "add", "."],
            capture_output=False,
        )
        if exit_code != 0:
            print(f"Error: git add . returned {exit_code}")
        return exit_code
    except KeyboardInterrupt:
        logger.info("git_add_all interrupted by user")
        _thread.interrupt_main()
        return 130
    except Exception as e:
        logger.error(f"Error in git_add_all: {e}")
        print(f"Error executing git add .: {e}", file=sys.stderr)
        return 1


def git_add_file(filename: str) -> int:
    """Run 'git add <filename>' command."""
    try:
        print(f"Running: git add {filename}")
        exit_code, _, _ = run_command_with_streaming_and_capture(
            ["git", "add", filename],
            capture_output=False,
        )
        if exit_code != 0:
            print(f"Error: git add {filename} returned {exit_code}")
        return exit_code
    except KeyboardInterrupt:
        logger.info("git_add_file interrupted by user")
        _thread.interrupt_main()
        return 130
    except Exception as e:
        logger.error(f"Error in git_add_file: {e}")
        print(f"Error executing git add {filename}: {e}", file=sys.stderr)
        return 1


def git_fetch() -> int:
    """Run 'git fetch' command."""
    try:
        print("Running: git fetch")
        exit_code, _, _ = run_command_with_streaming_and_capture(
            ["git", "fetch"],
            capture_output=False,
        )
        if exit_code != 0:
            print(f"Error: git fetch returned {exit_code}")
        return exit_code
    except KeyboardInterrupt:
        logger.info("git_fetch interrupted by user")
        _thread.interrupt_main()
        return 130
    except Exception as e:
        logger.error(f"Error in git_fetch: {e}")
        print(f"Error executing git fetch: {e}", file=sys.stderr)
        return 1


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
