#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "psutil>=5.9.0",
# ]
# ///

"""
Script to find and kill processes that have locks on codeup.exe and then delete the file.
Uses UV script mode with embedded psutil dependency.
"""

import os
import sys
import time
import psutil
from pathlib import Path

def find_processes_using_file(file_path):
    """Find all processes that have the given file open."""
    processes = []
    file_path = Path(file_path).resolve()

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Get all open files for this process
            for f in proc.open_files():
                if Path(f.path).resolve() == file_path:
                    processes.append(proc)
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # Process might have died or we don't have permission
            continue

    return processes

def kill_process_tree(pid):
    """Kill a process and all its children."""
    try:
        parent = psutil.Process(pid)
        # Kill all children first
        children = parent.children(recursive=True)
        for child in children:
            try:
                print(f"Killing child process {child.pid} ({child.name()})")
                child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Kill the parent
        print(f"Killing parent process {pid} ({parent.name()})")
        parent.kill()

        # Wait for processes to actually die
        psutil.wait_procs(children + [parent], timeout=3)
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        print(f"Could not kill process {pid}: {e}")
        return False

def main():
    # Use relative path from script location
    script_dir = Path(__file__).parent
    codeup_exe_path = script_dir / ".venv" / "Scripts" / "codeup.exe"

    print(f"Looking for processes using: {codeup_exe_path}")

    # Check if file exists
    if not codeup_exe_path.exists():
        print("File doesn't exist, nothing to do.")
        return 0

    # Find processes using the file
    processes = find_processes_using_file(codeup_exe_path)

    if not processes:
        print("No processes found using the file.")
        # Try to delete it anyway
        try:
            codeup_exe_path.unlink()
            print("Successfully deleted the file.")
            return 0
        except OSError as e:
            print(f"Could not delete file: {e}")
            return 1

    print(f"Found {len(processes)} process(es) using the file:")
    for proc in processes:
        try:
            print(f"  PID {proc.pid}: {proc.name()} - {' '.join(proc.cmdline())}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            print(f"  PID {proc.pid}: <process info unavailable>")

    # Kill the processes
    killed_any = False
    for proc in processes:
        try:
            if kill_process_tree(proc.pid):
                killed_any = True
        except Exception as e:
            print(f"Error killing process {proc.pid}: {e}")

    if killed_any:
        # Wait a moment for file handles to be released
        time.sleep(1)

    # Try to delete the file
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            codeup_exe_path.unlink()
            print("Successfully deleted the file.")
            return 0
        except OSError as e:
            print(f"Attempt {attempt + 1}: Could not delete file: {e}")
            if attempt < max_attempts - 1:
                time.sleep(1)

    print("Failed to delete the file after all attempts.")
    return 1

if __name__ == "__main__":
    sys.exit(main())