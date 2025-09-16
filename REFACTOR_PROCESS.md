# Process Refactor Documentation

This document catalogs all current subprocess and os.system usage in the codebase and outlines the refactoring plan to standardize on RunningProcess for streaming output.

## Current Subprocess/OS.system Usage Analysis

### Main Application Code (`src/codeup/main.py`)

#### Git Operations with Capture Output
1. **Line 143-149**: `git_commit_safe()` - Git commit with UTF-8 handling
   - `subprocess.run(["git", "commit", "-m", message], encoding="utf-8", capture_output=False)`
   - **Purpose**: Execute git commit, output goes directly to console
   - **Pattern**: Non-capturing, direct console output

2. **Lines 534-540**: `generate_ai_commit_message()` - Get staged diff
   - `subprocess.run(["git", "diff", "--cached"], capture_output=True, text=True, check=True, encoding="utf-8")`
   - **Purpose**: Capture git diff output for AI processing
   - **Pattern**: Capturing, text processing required

3. **Lines 546-549**: `generate_ai_commit_message()` - Get regular diff fallback
   - `subprocess.run(["git", "diff"], capture_output=True, text=True, check=True, encoding="utf-8")`
   - **Purpose**: Fallback diff capture when no staged changes
   - **Pattern**: Capturing, text processing required

4. **Lines 755-757**: `get_git_status()`
   - `subprocess.run(["git", "status"], capture_output=True, text=True, check=True, encoding="utf-8")`
   - **Purpose**: Get git status for processing
   - **Pattern**: Capturing, return stdout

5. **Lines 765-771**: `has_changes_to_commit()` - Check staged changes
   - `subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True, check=True, encoding="utf-8")`
   - **Purpose**: Check for staged file changes
   - **Pattern**: Capturing, boolean logic based on output

6. **Lines 776-779**: `has_changes_to_commit()` - Check unstaged changes
   - `subprocess.run(["git", "diff", "--name-only"], capture_output=True, text=True, check=True, encoding="utf-8")`
   - **Purpose**: Check for unstaged file changes
   - **Pattern**: Capturing, boolean logic based on output

7. **Lines 804**: `get_remote_hash()`
   - `subprocess.run(["git", "rev-parse", "origin/main"], capture_output=True, text=True, check=True, encoding="utf-8")`
   - **Purpose**: Get remote commit hash
   - **Pattern**: Capturing, single value return

8. **Lines 818**: `safe_rebase_main()` - Check for conflicts
   - `subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True, encoding="utf-8")`
   - **Purpose**: Check git status for conflicts
   - **Pattern**: Capturing, conflict detection

9. **Lines 837**: `safe_rebase_main()` - Get rebase conflicts
   - `subprocess.run(["git", "diff", "--name-only", "--diff-filter=U"], capture_output=True, text=True, check=True, encoding="utf-8")`
   - **Purpose**: List unmerged files during rebase
   - **Pattern**: Capturing, conflict file listing

10. **Lines 858**: `check_remote_changes()`
    - `subprocess.run(["git", "fetch"], capture_output=True, text=True, check=True, encoding="utf-8")`
    - **Purpose**: Fetch from remote
    - **Pattern**: Capturing, network operation

11. **Lines 871-875**: `check_remote_changes()` - Get remote hash
    - `subprocess.run(["git", "rev-parse", f"origin/{current_branch}"], capture_output=True, text=True, check=True, encoding="utf-8")`
    - **Purpose**: Get remote branch hash
    - **Pattern**: Capturing, hash comparison

12. **Lines 880-884**: `check_remote_changes()` - Get merge base
    - `subprocess.run(["git", "merge-base", "HEAD", f"origin/{current_branch}"], capture_output=True, text=True, check=True, encoding="utf-8")`
    - **Purpose**: Find common ancestor
    - **Pattern**: Capturing, merge base detection

13. **Lines 910**: `push_changes()`
    - `subprocess.run(["git", "push"], capture_output=True, text=True, check=True, encoding="utf-8")`
    - **Purpose**: Push changes to remote
    - **Pattern**: Capturing, but could benefit from streaming

14. **Lines 934**: `safe_rebase_main()` - Abort rebase
    - `subprocess.run(["git", "rebase", "--abort"], capture_output=True, text=True, check=True, encoding="utf-8")`
    - **Purpose**: Abort failed rebase
    - **Pattern**: Capturing, error recovery

15. **Lines 1017**: `run_uvx_tool()`
    - `subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8")`
    - **Purpose**: Run UV tools (lint/test)
    - **Pattern**: Capturing, but needs streaming for long operations

16. **Lines 1043**: `main()` - Run bash scripts
    - `subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8")`
    - **Purpose**: Execute ./lint and ./test scripts
    - **Pattern**: Capturing, but needs streaming for user feedback

### Test Files

#### `tests/test_cli.py`
- **Line 18**: `os.system(COMMAND)`
  - **Purpose**: Test CLI execution
  - **Pattern**: Direct system call, exit code checking

#### Test Helper Subprocess Usage
Multiple test files use subprocess.run for test setup and verification:
- Git repository initialization
- Test file creation
- Git operations for test scenarios
- Command execution verification

## Current RunningProcess Implementation

The `src/codeup/running_process.py` module provides:

### Key Functions
1. `stream_process_output(process)` - Real-time output streaming
2. `run_command_with_streaming()` - Command execution with streaming
3. `run_command_with_timeout()` - Command with timeout and streaming
4. `ProcessManager` class - Context manager for process lifecycle

### Streaming Capabilities
- **Real-time stdout/stderr streaming**: ✅
- **UTF-8 encoding support**: ✅
- **Keyboard interrupt handling**: ✅
- **Timeout support**: ✅
- **Cross-platform compatibility**: ✅
- **Context manager pattern**: ✅
- **Return exit codes**: ✅

## Refactoring Strategy

### Categories of Usage

#### Category 1: Direct Console Output (No Capture Needed)
**Current Pattern**: `subprocess.run(..., capture_output=False)`
**Target**: `run_command_with_streaming()`

Examples:
- `git_commit_safe()` - Git commits should show output in real-time

#### Category 2: Output Capture for Processing
**Current Pattern**: `subprocess.run(..., capture_output=True)`
**Challenge**: Need both streaming AND capture
**Solution**: Enhanced RunningProcess with capture capability

Examples:
- Git diff operations for AI processing
- Git status parsing
- Hash retrieval operations

#### Category 3: Long-Running Operations Needing Streaming
**Current Pattern**: `subprocess.run(..., capture_output=True)`
**Target**: `run_command_with_streaming()` + result capture
**Benefit**: User sees progress during lint/test execution

Examples:
- `./lint` script execution
- `./test` script execution
- `uvx` tool execution

#### Category 4: Quick Info Retrieval
**Current Pattern**: `subprocess.run(..., capture_output=True)`
**Target**: Enhanced RunningProcess with quiet mode
**Consideration**: May not need streaming for quick operations

Examples:
- Remote hash checking
- Git status porcelain checks
- File change detection

## Implementation Plan

### Phase 1: Enhance RunningProcess
Add capture capabilities while maintaining streaming:

```python
def run_command_with_streaming_and_capture(
    cmd: List[str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    shell: bool = False,
    quiet: bool = False,  # Suppress streaming for quick operations
    capture_output: bool = True,  # Capture stdout/stderr for return
) -> Tuple[int, str, str]:  # (exit_code, stdout, stderr)
    """
    Run a command with optional streaming and output capture.

    Args:
        cmd: Command and arguments as a list
        cwd: Working directory for the command
        env: Environment variables
        shell: Whether to use shell
        quiet: If True, suppress real-time streaming (for quick operations)
        capture_output: If True, capture and return stdout/stderr

    Returns:
        Tuple of (exit_code, stdout, stderr)
        If capture_output=False, stdout and stderr will be empty strings
    """
```

### Enhanced RunningProcess Design

#### Key New Functions

1. **`run_command_with_streaming_and_capture()`**
   - Combines streaming with output capture
   - Quiet mode for operations that don't need streaming
   - Returns both exit code and captured output

2. **Enhanced `ProcessManager` class**
   - Add `capture_output` parameter to constructor
   - Store captured stdout/stderr as attributes
   - Provide `get_output()` method for accessing captured content

3. **Streaming with Capture Implementation**
   ```python
   def stream_and_capture_output(process: subprocess.Popen[str], quiet: bool = False) -> Tuple[int, str, str]:
       """Stream output in real-time while also capturing it."""
       stdout_lines = []
       stderr_lines = []

       try:
           while True:
               if process.poll() is not None:
                   break

               # Read and optionally print stdout
               if process.stdout:
                   line = process.stdout.readline()
                   if line:
                       stdout_lines.append(line)
                       if not quiet:
                           print(line.rstrip(), flush=True)

               # Read and optionally print stderr
               if process.stderr:
                   line = process.stderr.readline()
                   if line:
                       stderr_lines.append(line)
                       if not quiet:
                           print(line.rstrip(), file=sys.stderr, flush=True)

               time.sleep(0.01)

           # Capture remaining output
           if process.stdout:
               for line in process.stdout:
                   stdout_lines.append(line)
                   if not quiet:
                       print(line.rstrip(), flush=True)

           if process.stderr:
               for line in process.stderr:
                   stderr_lines.append(line)
                   if not quiet:
                       print(line.rstrip(), file=sys.stderr, flush=True)

           exit_code = process.wait()
           stdout = ''.join(stdout_lines)
           stderr = ''.join(stderr_lines)

           return exit_code, stdout, stderr

       except KeyboardInterrupt:
           if not quiet:
               print("\nTerminating process...", file=sys.stderr)
           process.terminate()
           try:
               process.wait(timeout=10)
           except subprocess.TimeoutExpired:
               process.kill()
               process.wait()
           return 130, ''.join(stdout_lines), ''.join(stderr_lines)
   ```

#### Usage Patterns for Different Categories

**Category 1: Direct Streaming (No Capture)**
```python
# Current: subprocess.run(["git", "commit", "-m", message], capture_output=False)
# New:
exit_code, _, _ = run_command_with_streaming_and_capture(
    ["git", "commit", "-m", message],
    capture_output=False
)
```

**Category 2: Streaming + Capture for Processing**
```python
# Current: result = subprocess.run(["git", "diff", "--cached"], capture_output=True, text=True)
# New:
exit_code, stdout, stderr = run_command_with_streaming_and_capture(
    ["git", "diff", "--cached"],
    quiet=True  # Quick operations don't need streaming
)
diff_text = stdout.strip()
```

**Category 3: Long Operations with Streaming + Capture**
```python
# Current: subprocess.run(cmd, capture_output=True, text=True, check=True)
# New:
exit_code, stdout, stderr = run_command_with_streaming_and_capture(
    cmd,
    quiet=False  # Show progress to user
)
if exit_code != 0:
    raise subprocess.CalledProcessError(exit_code, cmd, output=stdout, stderr=stderr)
```

**Category 4: Quick Info Retrieval (Quiet)**
```python
# Current: subprocess.run(["git", "status"], capture_output=True, text=True, check=True)
# New:
exit_code, stdout, stderr = run_command_with_streaming_and_capture(
    ["git", "status"],
    quiet=True
)
return stdout
```

### Phase 2: Replace Non-Capturing Operations
Convert Category 1 usages:
- `git_commit_safe()` (main.py:143-149)

**Implementation**:
```python
# Before
result = subprocess.run(
    ["git", "commit", "-m", message],
    encoding="utf-8",
    errors="replace",
    text=True,
    capture_output=False,
)

# After
exit_code, _, _ = run_command_with_streaming_and_capture(
    ["git", "commit", "-m", message],
    capture_output=False
)
```

### Phase 3: Replace Long-Running Operations
Convert Category 3 usages:
- `run_uvx_tool()` (main.py:1017)
- Bash script execution in `main()` (main.py:1043)

**Implementation**:
```python
# Before
result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8")

# After
exit_code, stdout, stderr = run_command_with_streaming_and_capture(
    cmd,
    quiet=False  # Show real-time progress for lint/test operations
)
if exit_code != 0:
    # Preserve existing error handling
    raise subprocess.CalledProcessError(exit_code, cmd, output=stdout, stderr=stderr)
```

### Phase 4: Replace Capturing Operations
Convert Category 2 and 4 usages with appropriate quiet mode:

**Git Diff Operations** (Category 2):
- Lines 534-540: `generate_ai_commit_message()` staged diff
- Lines 546-549: `generate_ai_commit_message()` regular diff

```python
# Before
staged_result = subprocess.run(
    ["git", "diff", "--cached"],
    capture_output=True,
    text=True,
    check=True,
    encoding="utf-8",
)

# After
exit_code, stdout, stderr = run_command_with_streaming_and_capture(
    ["git", "diff", "--cached"],
    quiet=True  # No need to stream diff output
)
if exit_code != 0:
    raise subprocess.CalledProcessError(exit_code, ["git", "diff", "--cached"], output=stdout, stderr=stderr)
diff_text = stdout.strip()
```

**Git Status Operations** (Category 4):
- Line 755: `get_git_status()`
- Lines 765-771: `has_changes_to_commit()` staged changes
- Lines 776-779: `has_changes_to_commit()` unstaged changes
- Line 818: `safe_rebase_main()` conflict detection

**Git Hash/Remote Operations** (Category 4):
- Line 804: `get_remote_hash()`
- Lines 871-875: `check_remote_changes()` remote hash
- Lines 880-884: `check_remote_changes()` merge base
- Line 858: `check_remote_changes()` fetch
- Line 910: `push_changes()`

### Phase 5: Test Infrastructure
Update test files to use RunningProcess where appropriate:

**CLI Tests** (`tests/test_cli.py`):
```python
# Before
rtn = os.system(COMMAND)

# After
exit_code, _, _ = run_command_with_streaming_and_capture(
    COMMAND.split(),  # Convert string to list
    quiet=True  # Test execution doesn't need streaming
)
```

**Keep subprocess.run for**:
- Test setup operations (git init, file creation)
- Verification of test conditions
- Test isolation (don't change test behavior)

## Benefits of Refactoring

1. **Consistent User Experience**: All long operations show real-time progress
2. **Better Error Handling**: Unified error handling and keyboard interrupt support
3. **UTF-8 Consistency**: Centralized encoding handling
4. **Maintainability**: Single subprocess abstraction layer
5. **Timeout Support**: Built-in timeout capabilities for all operations
6. **Cross-platform**: Consistent behavior across Windows/Unix

## Migration Checklist

- [ ] Enhance RunningProcess with capture capabilities
- [ ] Add quiet mode for quick operations
- [ ] Convert git commit operations (streaming)
- [ ] Convert lint/test script execution (streaming + capture)
- [ ] Convert UV tool execution (streaming + capture)
- [ ] Convert git diff operations (quiet capture)
- [ ] Convert git status operations (quiet capture)
- [ ] Convert hash retrieval operations (quiet capture)
- [ ] Update CLI tests to use RunningProcess
- [ ] Add comprehensive tests for new RunningProcess features
- [ ] Update documentation and error handling patterns

## Risk Assessment

**Low Risk**:
- Category 1 operations (direct streaming)
- Long-running operations that benefit from streaming

**Medium Risk**:
- Operations that need both streaming and capture
- Quick operations that might be slowed by streaming overhead

**High Risk**:
- Test infrastructure changes
- Git operations with complex error handling (rebase, conflicts)

**Mitigation**:
- Implement quiet mode for operations that don't need streaming
- Extensive testing of git operations
- Gradual rollout with fallback capabilities
- Maintain existing error handling patterns

## Transformation Summary

### RunningProcess Enhancement Requirements

1. **New Function**: `run_command_with_streaming_and_capture()`
   - Parameters: `cmd`, `cwd`, `env`, `shell`, `quiet`, `capture_output`
   - Returns: `Tuple[int, str, str]` (exit_code, stdout, stderr)
   - Features: Optional streaming, output capture, UTF-8 encoding, keyboard interrupt handling

2. **Core Implementation**: `stream_and_capture_output()`
   - Dual functionality: streaming + capture
   - Quiet mode to suppress streaming for quick operations
   - Maintains existing keyboard interrupt behavior (exit code 130)

3. **Enhanced ProcessManager**
   - Add capture capabilities as instance attributes
   - Provide `get_output()` method for captured content

### Migration Mapping

| Current Pattern | New Pattern | Streaming | Capture | Use Case |
|----------------|-------------|-----------|---------|----------|
| `subprocess.run(..., capture_output=False)` | `run_command_with_streaming_and_capture(..., capture_output=False)` | ✅ | ❌ | Git commits, user-facing operations |
| `subprocess.run(..., capture_output=True)` (quick) | `run_command_with_streaming_and_capture(..., quiet=True)` | ❌ | ✅ | Git status, diffs, hashes |
| `subprocess.run(..., capture_output=True)` (long) | `run_command_with_streaming_and_capture(..., quiet=False)` | ✅ | ✅ | Lint, test, build operations |
| `os.system(...)` | `run_command_with_streaming_and_capture(cmd.split(), quiet=True)` | ❌ | ✅ | CLI tests |

### Expected Outcome

After refactoring:
- **16 subprocess.run calls** in main.py → **1 unified function**
- **1 os.system call** in tests → **unified function**
- **Improved UX**: Real-time feedback for long operations (lint, test, builds)
- **Maintained functionality**: All existing error handling and return values preserved
- **Enhanced reliability**: Consistent UTF-8 handling and keyboard interrupt support
- **Better testing**: Easier to mock and test process execution

### Validation Checklist

- [ ] All existing functionality preserved
- [ ] Real-time streaming for long operations (lint, test)
- [ ] Silent execution for quick operations (git status, diff)
- [ ] Proper error handling and exit codes
- [ ] UTF-8 encoding consistency
- [ ] Keyboard interrupt handling (Ctrl+C)
- [ ] Cross-platform compatibility
- [ ] Test coverage for new functionality