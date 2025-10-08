"""Git utility functions for codeup."""

import _thread
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from running_process import RunningProcess
from running_process.output_formatter import NullOutputFormatter

logger = logging.getLogger(__name__)


def _run_git_command(
    cmd: list[str],
    quiet: bool = False,
    capture_output: bool = True,
    cwd: str | None = None,
) -> tuple[int, str, str]:
    """Run a git command using RunningProcess and return (exit_code, stdout, stderr)."""
    stdout_lines = []

    rp = RunningProcess(
        command=cmd,
        cwd=Path(cwd) if cwd else None,
        auto_run=True,
        check=False,
        output_formatter=NullOutputFormatter(),
    )

    try:
        for line in rp.line_iter(
            timeout=600.0
        ):  # 10 minute timeout for long operations
            if capture_output:
                stdout_lines.append(line)
            if not quiet:
                print(line, flush=True)
    except KeyboardInterrupt:
        rp.kill()
        interrupt_main()
        raise
    except TimeoutError as e:
        import traceback

        logger.error(f"Timeout waiting for git command output: {e}")
        logger.error(f"Git command that timed out: {cmd}")
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


def interrupt_main() -> None:
    """Utility function to properly handle KeyboardInterrupt by calling _thread.interrupt_main()."""
    _thread.interrupt_main()


@dataclass(frozen=True)
class RebaseResult:
    """Result of an enhanced rebase operation with comprehensive safety information."""

    success: bool
    had_conflicts: bool
    backup_ref: str
    error_message: str
    recovery_commands: list[str]


def safe_git_commit(message: str) -> int:
    """Safely execute git commit with proper UTF-8 encoding."""
    try:
        from codeup.console import dim, error

        dim(f'Running: git commit -m "{message}"')
        exit_code, _, _ = _run_git_command(
            ["git", "commit", "-m", message],
            capture_output=False,  # Let output go to console directly
        )
        if exit_code != 0:
            error(f"git commit returned {exit_code}")
        return exit_code
    except KeyboardInterrupt:
        logger.info("safe_git_commit interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        from codeup.console import error

        logger.error(f"Error in safe_git_commit: {e}")
        error(f"Error executing git commit: {e}")
        return 1


def get_git_status() -> str:
    """Get git status output."""
    try:
        exit_code, stdout, stderr = _run_git_command(
            ["git", "status"],
            quiet=True,
        )
        return stdout
    except KeyboardInterrupt:
        logger.info("get_git_status interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error getting git status: {e}")
        return ""


def get_git_diff_cached() -> str:
    """Get staged changes diff."""
    try:
        exit_code, stdout, stderr = _run_git_command(
            ["git", "diff", "--cached"],
            quiet=True,  # Quiet for AI commit generation
        )
        return stdout.strip()
    except KeyboardInterrupt:
        logger.info("get_git_diff_cached interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error getting staged diff: {e}")
        return ""


def get_git_diff() -> str:
    """Get unstaged changes diff."""
    try:
        exit_code, stdout, stderr = _run_git_command(
            ["git", "diff"],
            quiet=True,  # Quiet for AI commit generation
        )
        return stdout.strip()
    except KeyboardInterrupt:
        logger.info("get_git_diff interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error getting diff: {e}")
        return ""


def get_staged_files() -> list[str]:
    """Get list of staged file names."""
    try:
        exit_code, stdout, stderr = _run_git_command(
            ["git", "diff", "--cached", "--name-only"],
            quiet=True,
        )
        # Filter out git warnings (lines starting with "warning:")
        return [
            f.strip()
            for f in stdout.splitlines()
            if f.strip() and not f.strip().startswith("warning:")
        ]
    except KeyboardInterrupt:
        logger.info("get_staged_files interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error getting staged files: {e}")
        return []


def get_unstaged_files() -> list[str]:
    """Get list of unstaged file names."""
    try:
        exit_code, stdout, stderr = _run_git_command(
            ["git", "diff", "--name-only"],
            quiet=True,
        )
        # Filter out git warnings (lines starting with "warning:")
        return [
            f.strip()
            for f in stdout.splitlines()
            if f.strip() and not f.strip().startswith("warning:")
        ]
    except KeyboardInterrupt:
        logger.info("get_unstaged_files interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error getting unstaged files: {e}")
        return []


def get_untracked_files() -> list[str]:
    """Get list of untracked files."""
    try:
        exit_code, stdout, stderr = _run_git_command(
            ["git", "ls-files", "--others", "--exclude-standard"],
            quiet=True,
        )

        return [f.strip() for f in stdout.splitlines() if f.strip()]
    except KeyboardInterrupt:
        logger.info("get_untracked_files interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error getting untracked files: {e}")
        return []


def get_main_branch() -> str:
    """Get the main branch name (main, master, etc.)."""
    try:
        # Try to get the default branch from remote
        exit_code, stdout, stderr = _run_git_command(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            quiet=True,
        )
        if exit_code == 0:
            return stdout.strip().split("/")[-1]
    except KeyboardInterrupt:
        logger.info("get_main_branch interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error getting main branch: {e}")
        pass

    # Fallback: check common branch names
    for branch in ["main", "master"]:
        try:
            exit_code, stdout, stderr = _run_git_command(
                ["git", "rev-parse", "--verify", f"origin/{branch}"],
                quiet=True,
            )
            if exit_code == 0:
                return branch
        except KeyboardInterrupt:
            logger.info("get_main_branch loop interrupted by user")
            interrupt_main()
            raise
        except Exception as e:
            logger.error(f"Error checking branch {branch}: {e}")
            continue

    return "main"  # Default fallback


def get_current_branch() -> str:
    """Get the current branch name."""
    try:
        from codeup.console import dim

        dim("Running: git branch --show-current")
        exit_code, stdout, stderr = _run_git_command(
            ["git", "branch", "--show-current"],
            quiet=False,  # Enable streaming to see what's happening
        )
        return stdout.strip()
    except KeyboardInterrupt:
        logger.info("get_current_branch interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error getting current branch: {e}")
        return ""


def get_upstream_branch() -> str:
    """Get the upstream tracking branch for the current branch."""
    try:
        exit_code, stdout, stderr = _run_git_command(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            quiet=True,
        )
        if exit_code == 0:
            return stdout.strip()
        else:
            return ""
    except KeyboardInterrupt:
        logger.info("get_upstream_branch interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error getting upstream branch: {e}")
        return ""


def get_remote_branch_hash(target_branch: str) -> str:
    """Get the hash of the remote target branch."""
    try:
        # Handle both origin/branch format and just branch format
        remote_ref = (
            target_branch
            if target_branch.startswith("origin/")
            else f"origin/{target_branch}"
        )
        exit_code, stdout, stderr = _run_git_command(
            ["git", "rev-parse", remote_ref],
            quiet=False,
        )
        return stdout.strip()
    except KeyboardInterrupt:
        logger.info("get_remote_branch_hash interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error getting remote branch hash: {e}")
        return ""


def get_merge_base(target_branch: str) -> str:
    """Get the merge base between HEAD and the remote target branch."""
    try:
        # Handle both origin/branch format and just branch format
        remote_ref = (
            target_branch
            if target_branch.startswith("origin/")
            else f"origin/{target_branch}"
        )
        exit_code, stdout, stderr = _run_git_command(
            ["git", "merge-base", "HEAD", remote_ref],
            quiet=False,
        )
        return stdout.strip()
    except KeyboardInterrupt:
        logger.info("get_merge_base interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error getting merge base: {e}")
        return ""


def check_rebase_needed(target_branch: str) -> bool:
    """Check if current branch is behind the remote target branch."""
    try:
        remote_hash = get_remote_branch_hash(target_branch)
        merge_base = get_merge_base(target_branch)
        return merge_base != remote_hash
    except KeyboardInterrupt:
        logger.info("check_rebase_needed interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error checking rebase needed: {e}")
        return False


def attempt_rebase(target_branch: str) -> tuple[bool, bool]:
    """
    Attempt a rebase and handle conflicts properly.

    Returns:
        Tuple[bool, bool]: (success, had_conflicts)
        - success: True if rebase completed successfully
        - had_conflicts: True if conflicts were encountered (and rebase was aborted)
    """
    try:
        # Handle both origin/branch format and just branch format
        remote_ref = (
            target_branch
            if target_branch.startswith("origin/")
            else f"origin/{target_branch}"
        )

        # Attempt the actual rebase
        exit_code, stdout, stderr = _run_git_command(
            ["git", "rebase", remote_ref],
            quiet=False,
        )

        if exit_code == 0:
            # Rebase succeeded
            logger.info(f"Successfully rebased onto {remote_ref}")
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
                abort_exit_code, abort_stdout, abort_stderr = _run_git_command(
                    ["git", "rebase", "--abort"],
                    quiet=False,
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
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error attempting rebase: {e}")
        print(f"Error attempting rebase: {e}", file=sys.stderr)
        return False, False


def git_push() -> tuple[bool, str]:
    """
    Attempt git push. Sets upstream tracking for new branches automatically.

    Returns:
        Tuple[bool, str]: (success, error_message)
    """
    try:
        current_branch = get_current_branch()
        upstream_branch = get_upstream_branch()

        # If no upstream is set, try to push with --set-upstream
        if not upstream_branch:
            print(
                f"No upstream set for branch '{current_branch}', setting upstream to origin/{current_branch}"
            )
            exit_code, stdout, stderr = _run_git_command(
                ["git", "push", "--set-upstream", "origin", current_branch],
                quiet=False,
            )
        else:
            # Normal push when upstream is already set
            exit_code, stdout, stderr = _run_git_command(
                ["git", "push"],
                quiet=False,
            )

        return exit_code == 0, stderr
    except KeyboardInterrupt:
        logger.info("git_push interrupted by user")
        interrupt_main()
        raise
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
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error checking for changes: {e}")
        return False


def has_unpushed_commits() -> bool:
    """Check if there are any unpushed commits on the current branch."""
    try:
        upstream_branch = get_upstream_branch()
        if not upstream_branch:
            # No upstream branch set, can't determine unpushed commits
            return False

        # Count commits that are in HEAD but not in upstream
        exit_code, stdout, stderr = _run_git_command(
            ["git", "rev-list", "--count", f"{upstream_branch}..HEAD"],
            quiet=True,
        )

        if exit_code != 0:
            logger.error(f"Failed to check unpushed commits: {stderr}")
            return False

        try:
            unpushed_count = int(stdout.strip())
            return unpushed_count > 0
        except ValueError as e:
            logger.error(
                f"Failed to parse unpushed commit count: {stdout.strip()!r}, error: {e}"
            )
            return False

    except KeyboardInterrupt:
        logger.info("has_unpushed_commits interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error checking for unpushed commits: {e}")
        return False


def get_unpushed_commit_files() -> list[str]:
    """Get list of files changed in unpushed commits."""
    try:
        upstream_branch = get_upstream_branch()
        if not upstream_branch:
            return []

        # Get files changed in unpushed commits
        exit_code, stdout, stderr = _run_git_command(
            ["git", "diff", "--name-only", f"{upstream_branch}..HEAD"],
            quiet=True,
        )

        if exit_code != 0:
            logger.error(f"Failed to get unpushed commit files: {stderr}")
            return []

        # Filter out git warnings (lines starting with "warning:")
        return [
            f.strip()
            for f in stdout.splitlines()
            if f.strip() and not f.strip().startswith("warning:")
        ]

    except KeyboardInterrupt:
        logger.info("get_unpushed_commit_files interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error getting unpushed commit files: {e}")
        return []


def has_modified_tracked_files() -> bool:
    """Check if there are any modified files that are already tracked by git."""
    try:
        # Get unstaged changes to tracked files
        unstaged_files = get_unstaged_files()
        if unstaged_files:
            return True

        # Get staged changes
        staged_files = get_staged_files()
        if staged_files:
            return True

        return False

    except KeyboardInterrupt:
        logger.info("has_modified_tracked_files interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error checking for modified tracked files: {e}")
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
        from codeup.console import dim, error

        dim("Running: git add .")
        exit_code, _, _ = _run_git_command(
            ["git", "add", "."],
            capture_output=False,
        )
        if exit_code != 0:
            error(f"git add . returned {exit_code}")
        return exit_code
    except KeyboardInterrupt:
        logger.info("git_add_all interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        from codeup.console import error

        logger.error(f"Error in git_add_all: {e}")
        error(f"Error executing git add .: {e}")
        return 1


def git_add_file(filename: str) -> int:
    """Run 'git add <filename>' command."""
    try:
        from codeup.console import dim, error

        dim(f"Running: git add {filename}")
        exit_code, _, _ = _run_git_command(
            ["git", "add", filename],
            capture_output=False,
        )
        if exit_code != 0:
            error(f"git add {filename} returned {exit_code}")
        return exit_code
    except KeyboardInterrupt:
        logger.info("git_add_file interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        from codeup.console import error

        logger.error(f"Error in git_add_file: {e}")
        error(f"Error executing git add {filename}: {e}")
        return 1


def git_fetch() -> int:
    """Run 'git fetch' command."""
    try:
        from codeup.console import dim, error

        dim("Running: git fetch")
        exit_code, _, _ = _run_git_command(
            ["git", "fetch"],
            capture_output=False,
        )
        if exit_code != 0:
            error(f"git fetch returned {exit_code}")
        return exit_code
    except KeyboardInterrupt:
        logger.info("git_fetch interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        from codeup.console import error

        logger.error(f"Error in git_fetch: {e}")
        error(f"Error executing git fetch: {e}")
        return 1


def safe_rebase_try() -> bool:
    """Attempt a safe rebase using proper git commands. Returns True if successful or no rebase needed."""
    try:
        from codeup.console import error, info, success

        current_branch = get_current_branch()
        upstream_branch = get_upstream_branch()
        main_branch = get_main_branch()

        # Determine the target branch for rebase
        if upstream_branch:
            # Use the upstream tracking branch if it exists
            target_branch = upstream_branch
            print(f"Current branch '{current_branch}' tracks '{upstream_branch}'")
        else:
            # Fallback to main branch behavior
            target_branch = main_branch
            print(
                f"Current branch '{current_branch}' has no upstream, using main branch '{main_branch}'"
            )

            # If we're on the main branch and no upstream, no rebase needed
            if current_branch == main_branch:
                return True

        # Check if rebase is needed
        if not check_rebase_needed(target_branch):
            success(f"Branch is already up to date with origin/{target_branch}")
            return True

        # Attempt the rebase directly - this will handle conflicts properly
        remote_ref = (
            target_branch
            if target_branch.startswith("origin/")
            else f"origin/{target_branch}"
        )
        print(f"Attempting rebase onto {remote_ref}...")
        rebase_success, had_conflicts = attempt_rebase(target_branch)

        if rebase_success:
            success(f"Successfully rebased onto {remote_ref}")
            return True
        elif had_conflicts:
            error(f"Cannot automatically rebase: conflicts detected with {remote_ref}")
            error(
                "Remote repository has conflicting changes that must be manually resolved."
            )
            info(f"Please run: git rebase {remote_ref}")
            info("Then resolve any conflicts manually.")
            return False
        else:
            error("Rebase failed for other reasons")
            return False

    except KeyboardInterrupt:
        logger.info("safe_rebase_try interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        from codeup.console import error

        logger.error(f"Error in safe_rebase_try: {e}")
        error(f"Error during safe rebase attempt: {e}")
        return False


def get_last_commit_message() -> str:
    """Get the most recent commit message."""
    try:
        exit_code, stdout, stderr = _run_git_command(
            ["git", "log", "-1", "--pretty=%B"],
            quiet=True,
        )
        if exit_code == 0:
            return stdout.strip()
        else:
            logger.warning(f"Failed to get last commit message: {stderr}")
            return ""
    except KeyboardInterrupt:
        logger.info("get_last_commit_message interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error getting last commit message: {e}")
        return ""


def safe_push() -> bool:
    """Attempt to push safely. Assumes rebase has already been handled if needed."""
    try:
        from codeup.console import error, info, success

        # Try a push - rebase should have been handled earlier in the workflow
        info("Attempting to push to remote...")
        push_success, stderr = git_push()

        if push_success:
            # Get the last commit message to display
            commit_msg = get_last_commit_message()
            if commit_msg:
                # Get first line only (in case of multi-line commits)
                first_line = commit_msg.split("\n")[0]
                # Truncate if too long
                if len(first_line) > 60:
                    first_line = first_line[:57] + "..."
                success(f"Successfully pushed to remote with commit: {first_line}")
            else:
                success("Successfully pushed to remote")
            return True
        else:
            error(f"Push failed: {stderr}")
            return False

    except KeyboardInterrupt:
        logger.info("safe_push interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        from codeup.console import error

        logger.error(f"Push error: {e}")
        error(f"Push error: {e}")
        return False


def capture_pre_rebase_state() -> str:
    """Capture current state for potential rollback."""
    try:
        exit_code, head_hash, _ = _run_git_command(
            ["git", "rev-parse", "HEAD"], quiet=True
        )
        if exit_code != 0:
            logger.error(f"Failed to capture pre-rebase state: exit code {exit_code}")
            return ""

        backup_ref = head_hash.strip()

        # CRITICAL: Validate backup reference exists
        exit_code, _, _ = _run_git_command(
            ["git", "cat-file", "-e", backup_ref], quiet=True
        )
        if exit_code != 0:
            logger.error(f"Backup reference {backup_ref} is invalid")
            return ""

        return backup_ref
    except KeyboardInterrupt:
        logger.info("capture_pre_rebase_state interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error capturing pre-rebase state: {e}")
        return ""


def verify_clean_working_directory() -> bool:
    """Verify working directory is clean before rebase."""
    try:
        exit_code, status_output, _ = _run_git_command(
            ["git", "status", "--porcelain"], quiet=True
        )
        if exit_code == 0:
            return len(status_output.strip()) == 0
        else:
            logger.error(
                f"Failed to check working directory status: exit code {exit_code}"
            )
            return False
    except KeyboardInterrupt:
        logger.info("verify_clean_working_directory interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error verifying clean working directory: {e}")
        return False


def emergency_rollback(backup_ref: str) -> bool:
    """Emergency rollback using reflog recovery."""
    if not backup_ref:
        logger.error("No backup reference available for emergency rollback")
        return False

    try:
        # CRITICAL: Check if rebase is in progress and abort first
        exit_code, status_output, _ = _run_git_command(
            ["git", "status", "--porcelain=v1"], quiet=True
        )
        if exit_code == 0 and "rebase in progress" in status_output.lower():
            logger.info("Aborting active rebase before emergency rollback")
            _run_git_command(["git", "rebase", "--abort"], quiet=False)

        print(f"Performing emergency rollback to {backup_ref[:8]}...")
        exit_code, _, stderr = _run_git_command(
            ["git", "reset", "--hard", backup_ref], quiet=False
        )
        if exit_code == 0:
            print("Emergency rollback completed successfully")
            return True
        else:
            logger.error(f"Emergency rollback failed: {stderr}")
            return False
    except KeyboardInterrupt:
        logger.info("emergency_rollback interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error during emergency rollback: {e}")
        return False


def verify_state_matches_backup(backup_ref: str) -> bool:
    """Verify current HEAD matches backup AND working directory is clean."""
    if not backup_ref:
        return False

    try:
        # Check HEAD hash
        exit_code, current_ref, _ = _run_git_command(
            ["git", "rev-parse", "HEAD"], quiet=True
        )
        if exit_code != 0 or current_ref.strip() != backup_ref:
            return False

        # CRITICAL: Also verify working directory is clean
        return verify_clean_working_directory()
    except KeyboardInterrupt:
        logger.info("verify_state_matches_backup interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error verifying state matches backup: {e}")
        return False


def execute_enhanced_abort(backup_ref: str) -> bool:
    """Enhanced rebase abort with state verification."""
    try:
        print("Aborting rebase and restoring clean state...")
        abort_exit_code, _, abort_stderr = _run_git_command(
            ["git", "rebase", "--abort"], quiet=False
        )

        if abort_exit_code == 0:
            if verify_state_matches_backup(backup_ref):
                print("Rebase aborted successfully, clean state restored")
                return True
            else:
                logger.warning(
                    "Rebase aborted but state verification failed, attempting emergency rollback"
                )
                return emergency_rollback(backup_ref)
        else:
            logger.error(f"Rebase abort failed: {abort_stderr}")
            print("Rebase abort failed, attempting emergency rollback...")
            return emergency_rollback(backup_ref)

    except KeyboardInterrupt:
        logger.info("execute_enhanced_abort interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error during enhanced abort: {e}")
        return emergency_rollback(backup_ref)


def generate_recovery_commands(backup_ref: str, target_branch: str) -> list[str]:
    """Generate recovery commands for manual intervention."""
    # Handle both origin/branch format and just branch format
    remote_ref = (
        target_branch
        if target_branch.startswith("origin/")
        else f"origin/{target_branch}"
    )
    commands = [
        "# Manual recovery options:",
        f"git reset --hard {backup_ref}  # Rollback to pre-rebase state",
        f"git rebase {remote_ref}  # Retry rebase manually",
        "git reflog  # View detailed history for recovery",
        "git status  # Check current state",
    ]

    if backup_ref:
        commands.insert(1, f"# Backup reference: {backup_ref[:8]}...")

    return commands


def generate_emergency_recovery_commands(backup_ref: str) -> list[str]:
    """Generate emergency recovery commands for critical failures."""
    commands = [
        "# Emergency recovery options:",
        "git status  # Check current repository state",
        "git reflog --oneline -10  # View recent ref changes",
    ]

    if backup_ref:
        commands.extend(
            [
                f"git reset --hard {backup_ref}  # Force rollback to backup state",
                f"# Backup reference: {backup_ref[:8]}...",
            ]
        )
    else:
        commands.extend(
            [
                "git reset --hard ORIG_HEAD  # Try rolling back to previous HEAD",
                "git fsck --lost-found  # Find any orphaned commits",
            ]
        )

    return commands


def detect_rebase_conflicts(stdout: str, stderr: str) -> bool:
    """Enhanced conflict detection for rebase operations."""
    conflict_indicators = [
        "conflict",
        "failed to merge",
        "merge conflict",
        "automatic merge failed",
        "resolve conflicts",
        "fix conflicts",
        # CRITICAL: Add missing patterns
        "CONFLICT (content)",
        "both modified",
        "both added",
        "added by us",
        "added by them",
        "deleted by us",
        "deleted by them",
    ]

    combined_output = (stdout + " " + stderr).lower()
    return any(indicator in combined_output for indicator in conflict_indicators)


def verify_rebase_success(target_branch: str) -> bool:
    """Verify that rebase completed successfully and working directory is clean."""
    try:
        if not verify_clean_working_directory():
            logger.warning("Working directory not clean after rebase")
            return False

        exit_code, _, _ = _run_git_command(
            ["git", "rev-parse", "--verify", "HEAD"], quiet=True
        )
        if exit_code != 0:
            logger.error("HEAD reference is invalid after rebase")
            return False

        return True
    except KeyboardInterrupt:
        logger.info("verify_rebase_success interrupted by user")
        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Error verifying rebase success: {e}")
        return False


def enhanced_attempt_rebase(target_branch: str) -> RebaseResult:
    """Enhanced rebase with comprehensive safety mechanisms."""
    backup_ref = ""

    try:
        # Phase 1: Pre-rebase safety capture
        print("Capturing pre-rebase state for safety...")
        backup_ref = capture_pre_rebase_state()
        if not backup_ref:
            return RebaseResult(
                success=False,
                had_conflicts=False,
                backup_ref="",
                error_message="Failed to capture pre-rebase state",
                recovery_commands=["git status", "git reflog"],
            )

        # Phase 2: Verify clean working directory
        if not verify_clean_working_directory():
            return RebaseResult(
                success=False,
                had_conflicts=False,
                backup_ref=backup_ref,
                error_message="Working directory not clean",
                recovery_commands=["git status", "git stash", "git reset --hard HEAD"],
            )

        # Phase 3: Execute fetch to ensure we have latest remote refs
        print("Fetching latest changes from remote...")
        fetch_exit_code = git_fetch()
        if fetch_exit_code != 0:
            return RebaseResult(
                success=False,
                had_conflicts=False,
                backup_ref=backup_ref,
                error_message="Failed to fetch from remote",
                recovery_commands=generate_recovery_commands(backup_ref, target_branch),
            )

        # Phase 4: Execute atomic rebase
        # Handle both origin/branch format and just branch format
        remote_ref = (
            target_branch
            if target_branch.startswith("origin/")
            else f"origin/{target_branch}"
        )
        print(f"Attempting rebase onto {remote_ref}...")
        exit_code, stdout, stderr = _run_git_command(
            ["git", "rebase", remote_ref],
            quiet=False,
        )

        if exit_code == 0:
            # Success path - verify final state
            if verify_rebase_success(target_branch):
                print(f"Successfully rebased onto {remote_ref}")
                return RebaseResult(
                    success=True,
                    had_conflicts=False,
                    backup_ref=backup_ref,
                    error_message="",
                    recovery_commands=[],
                )
            else:
                # Rebase appeared successful but verification failed
                logger.warning("Rebase completed but verification failed")
                return RebaseResult(
                    success=False,
                    had_conflicts=False,
                    backup_ref=backup_ref,
                    error_message="Rebase completed but final state verification failed",
                    recovery_commands=generate_recovery_commands(
                        backup_ref, target_branch
                    ),
                )

        # Conflict detection with enhanced recovery
        if detect_rebase_conflicts(stdout, stderr):
            logger.info("Rebase conflicts detected, executing enhanced abort")
            recovery_success = execute_enhanced_abort(backup_ref)

            if recovery_success:
                print("Conflicts detected and clean state restored")
            else:
                print(
                    "Conflicts detected but recovery failed - manual intervention required"
                )

            return RebaseResult(
                success=False,
                had_conflicts=True,
                backup_ref=backup_ref,
                error_message="Rebase conflicts detected",
                recovery_commands=generate_recovery_commands(backup_ref, target_branch),
            )
        else:
            # Rebase failed for other reasons
            logger.error(f"Rebase failed: exit code {exit_code}, stderr: {stderr}")
            recovery_success = execute_enhanced_abort(backup_ref)

            return RebaseResult(
                success=False,
                had_conflicts=False,
                backup_ref=backup_ref,
                error_message=f"Rebase failed: {stderr}",
                recovery_commands=generate_recovery_commands(backup_ref, target_branch),
            )

    except KeyboardInterrupt:
        logger.info("enhanced_attempt_rebase interrupted by user")
        interrupt_main()
        # Attempt emergency recovery on interrupt
        try:
            emergency_rollback(backup_ref)
        except Exception as e:
            logger.warning(f"Emergency rollback failed during interrupt: {e}")
            # Continue with interrupt propagation despite rollback failure
        raise
    except Exception as e:
        logger.error(f"Unexpected error during enhanced rebase: {e}")
        # Emergency rollback for any unexpected failures
        emergency_rollback(backup_ref)
        return RebaseResult(
            success=False,
            had_conflicts=False,
            backup_ref=backup_ref,
            error_message=f"Rebase failed: {e}",
            recovery_commands=generate_emergency_recovery_commands(backup_ref),
        )
