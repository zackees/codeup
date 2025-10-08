"""Console output utilities with color support."""

import sys

from colorama import Fore, Style, init

# Initialize colorama for cross-platform support
init(autoreset=True)


def success(message: str) -> None:
    """Print a success message in green."""
    print(f"{Fore.GREEN}{message}{Style.RESET_ALL}")


def info(message: str) -> None:
    """Print an informational message in cyan."""
    print(f"{Fore.CYAN}{message}{Style.RESET_ALL}")


def warning(message: str) -> None:
    """Print a warning message in yellow."""
    print(f"{Fore.YELLOW}{message}{Style.RESET_ALL}")


def error(message: str, file=None) -> None:
    """Print an error message in red."""
    if file is None:
        file = sys.stderr
    print(f"{Fore.RED}{message}{Style.RESET_ALL}", file=file)


def dim(message: str) -> None:
    """Print a dimmed message (low-emphasis info)."""
    print(f"{Style.DIM}{message}{Style.RESET_ALL}")


def status_header(message: str) -> None:
    """Print a status header (bright white/bold)."""
    print(f"{Style.BRIGHT}{message}{Style.RESET_ALL}")


def git_status_summary(
    staged: list[str],
    unstaged: list[str],
    untracked: list[str],
    unpushed_count: int = 0,
) -> None:
    """Print a clean, color-coded git status summary.

    Args:
        staged: List of staged files
        unstaged: List of unstaged files
        untracked: List of untracked files
        unpushed_count: Number of unpushed commits
    """
    has_changes = bool(staged or unstaged or untracked or unpushed_count)

    if not has_changes:
        success("✓ Working tree clean, no changes to commit")
        return

    # Show summary counts
    parts = []
    if unpushed_count:
        parts.append(
            f"{unpushed_count} unpushed commit{'s' if unpushed_count != 1 else ''}"
        )
    if staged:
        parts.append(f"{len(staged)} staged")
    if unstaged:
        parts.append(f"{len(unstaged)} modified")
    if untracked:
        parts.append(f"{len(untracked)} untracked")

    status_header(f"Status: {', '.join(parts)}")
    print()  # Add blank line for readability

    # Show detailed file lists with color coding
    if staged:
        success("✓ Staged files (ready to commit):")
        for file in staged:
            print(f"  {Fore.GREEN}● {file}{Style.RESET_ALL}")
        print()

    if unstaged:
        info("⚡ Modified files (not staged):")
        for file in unstaged:
            print(f"  {Fore.CYAN}● {file}{Style.RESET_ALL}")
        print()

    if untracked:
        warning("? Untracked files (need to add):")
        for file in untracked:
            print(f"  {Fore.YELLOW}● {file}{Style.RESET_ALL}")
        print()
