"""Git utility functions for codeup."""

import _thread
import logging
import os
import sys
from dataclasses import dataclass

from codeup.running_process_adapter import run_command_with_streaming_and_capture

logger = logging.getLogger(__name__)


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
    print("Running: git status")
    exit_code, stdout, stderr = run_command_with_streaming_and_capture(
        ["git", "status"],
        quiet=False,
        check=True,  # Enable streaming to see what's happening
    )
    return stdout


def get_git_diff_cached() -> str:
    """Get staged changes diff."""
    try:
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "diff", "--cached"],
            quiet=True,  # Quiet for AI commit generation
            raw_output=True,  # Raw output for clean diff
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
            quiet=True,  # Quiet for AI commit generation
            raw_output=True,  # Raw output for clean diff
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


def get_staged_files() -> list[str]:
    """Get list of staged file names."""
    try:
        print("Running: git diff --cached --name-only")
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "diff", "--cached", "--name-only"],
            quiet=False,  # Enable streaming to see what's happening
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


def get_unstaged_files() -> list[str]:
    """Get list of unstaged file names."""
    try:
        print("Running: git diff --name-only")
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "diff", "--name-only"],
            quiet=False,  # Enable streaming to see what's happening
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


def get_untracked_files() -> list[str]:
    """Get list of untracked files."""
    print("Running: git ls-files --others --exclude-standard")
    exit_code, stdout, stderr = run_command_with_streaming_and_capture(
        ["git", "ls-files", "--others", "--exclude-standard"],
        quiet=False,  # Enable streaming to see what's happening
        check=True,
    )

    return [f.strip() for f in stdout.splitlines() if f.strip()]


def get_main_branch() -> str:
    """Get the main branch name (main, master, etc.)."""
    try:
        # Try to get the default branch from remote
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            quiet=False,
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
                quiet=False,
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
    print("Running: git branch --show-current")
    exit_code, stdout, stderr = run_command_with_streaming_and_capture(
        ["git", "branch", "--show-current"],
        quiet=False,  # Enable streaming to see what's happening
        check=True,
    )
    return stdout.strip()


def get_remote_branch_hash(main_branch: str) -> str:
    """Get the hash of the remote main branch."""
    try:
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "rev-parse", f"origin/{main_branch}"],
            quiet=False,
            check=True,
            raw_output=True,
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
            quiet=False,
            check=True,
            raw_output=True,
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


def attempt_rebase(main_branch: str) -> tuple[bool, bool]:
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
            quiet=False,
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
                        quiet=False,
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


def git_push() -> tuple[bool, str]:
    """
    Attempt git push.

    Returns:
        Tuple[bool, str]: (success, error_message)
    """
    try:
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "push"],
            quiet=False,
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


def capture_pre_rebase_state() -> str:
    """Capture current state for potential rollback."""
    try:
        exit_code, head_hash, _ = run_command_with_streaming_and_capture(
            ["git", "rev-parse", "HEAD"], quiet=True, raw_output=True
        )
        if exit_code != 0:
            logger.error(f"Failed to capture pre-rebase state: exit code {exit_code}")
            return ""

        backup_ref = head_hash.strip()

        # CRITICAL: Validate backup reference exists
        exit_code, _, _ = run_command_with_streaming_and_capture(
            ["git", "cat-file", "-e", backup_ref], quiet=True, raw_output=True
        )
        if exit_code != 0:
            logger.error(f"Backup reference {backup_ref} is invalid")
            return ""

        return backup_ref
    except KeyboardInterrupt:
        logger.info("capture_pre_rebase_state interrupted by user")
        _thread.interrupt_main()
        return ""
    except Exception as e:
        logger.error(f"Error capturing pre-rebase state: {e}")
        return ""


def verify_clean_working_directory() -> bool:
    """Verify working directory is clean before rebase."""
    try:
        exit_code, status_output, _ = run_command_with_streaming_and_capture(
            ["git", "status", "--porcelain"], quiet=True, raw_output=True
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
        _thread.interrupt_main()
        return False
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
        exit_code, status_output, _ = run_command_with_streaming_and_capture(
            ["git", "status", "--porcelain=v1"], quiet=True, raw_output=True
        )
        if exit_code == 0 and "rebase in progress" in status_output.lower():
            logger.info("Aborting active rebase before emergency rollback")
            run_command_with_streaming_and_capture(
                ["git", "rebase", "--abort"], quiet=False
            )

        print(f"Performing emergency rollback to {backup_ref[:8]}...")
        exit_code, _, stderr = run_command_with_streaming_and_capture(
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
        _thread.interrupt_main()
        return False
    except Exception as e:
        logger.error(f"Error during emergency rollback: {e}")
        return False


def verify_state_matches_backup(backup_ref: str) -> bool:
    """Verify current HEAD matches backup AND working directory is clean."""
    if not backup_ref:
        return False

    try:
        # Check HEAD hash
        exit_code, current_ref, _ = run_command_with_streaming_and_capture(
            ["git", "rev-parse", "HEAD"], quiet=True, raw_output=True
        )
        if exit_code != 0 or current_ref.strip() != backup_ref:
            return False

        # CRITICAL: Also verify working directory is clean
        return verify_clean_working_directory()
    except KeyboardInterrupt:
        logger.info("verify_state_matches_backup interrupted by user")
        _thread.interrupt_main()
        return False
    except Exception as e:
        logger.error(f"Error verifying state matches backup: {e}")
        return False


def execute_enhanced_abort(backup_ref: str) -> bool:
    """Enhanced rebase abort with state verification."""
    try:
        print("Aborting rebase and restoring clean state...")
        abort_exit_code, _, abort_stderr = run_command_with_streaming_and_capture(
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
        _thread.interrupt_main()
        return False
    except Exception as e:
        logger.error(f"Error during enhanced abort: {e}")
        return emergency_rollback(backup_ref)


def generate_recovery_commands(backup_ref: str, main_branch: str) -> list[str]:
    """Generate recovery commands for manual intervention."""
    commands = [
        "# Manual recovery options:",
        f"git reset --hard {backup_ref}  # Rollback to pre-rebase state",
        f"git rebase origin/{main_branch}  # Retry rebase manually",
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


def verify_rebase_success(main_branch: str) -> bool:
    """Verify that rebase completed successfully and working directory is clean."""
    try:
        if not verify_clean_working_directory():
            logger.warning("Working directory not clean after rebase")
            return False

        exit_code, _, _ = run_command_with_streaming_and_capture(
            ["git", "rev-parse", "--verify", "HEAD"], quiet=True, raw_output=True
        )
        if exit_code != 0:
            logger.error("HEAD reference is invalid after rebase")
            return False

        return True
    except KeyboardInterrupt:
        logger.info("verify_rebase_success interrupted by user")
        _thread.interrupt_main()
        return False
    except Exception as e:
        logger.error(f"Error verifying rebase success: {e}")
        return False


def enhanced_attempt_rebase(main_branch: str) -> RebaseResult:
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
                recovery_commands=generate_recovery_commands(backup_ref, main_branch),
            )

        # Phase 4: Execute atomic rebase
        print(f"Attempting rebase onto origin/{main_branch}...")
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            ["git", "rebase", f"origin/{main_branch}"],
            quiet=False,
        )

        if exit_code == 0:
            # Success path - verify final state
            if verify_rebase_success(main_branch):
                print(f"Successfully rebased onto origin/{main_branch}")
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
                        backup_ref, main_branch
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
                recovery_commands=generate_recovery_commands(backup_ref, main_branch),
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
                recovery_commands=generate_recovery_commands(backup_ref, main_branch),
            )

    except KeyboardInterrupt:
        logger.info("enhanced_attempt_rebase interrupted by user")
        _thread.interrupt_main()
        # Attempt emergency recovery on interrupt
        emergency_rollback(backup_ref)
        return RebaseResult(
            success=False,
            had_conflicts=False,
            backup_ref=backup_ref,
            error_message="Rebase interrupted by user",
            recovery_commands=generate_emergency_recovery_commands(backup_ref),
        )
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
