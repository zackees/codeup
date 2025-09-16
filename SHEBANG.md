# Shebang Processing Plan for Windows Cross-Platform Compatibility

## Current Issue Analysis

The codeup project has several shell scripts with shebang lines that cause execution issues on Windows. While Windows can execute `.py` files through file association, bash scripts (like `./lint` and `./test`) require special handling to process their shebang lines correctly.

### Affected Scripts
- `./lint` - Bash script with `#!/bin/bash` shebang for linting workflow
- `./test` - Bash script with `#!/bin/bash` shebang for testing workflow
- `./clean` - Bash script with `#!/bin/bash` shebang for cleanup
- `./install` - Bash script with `#!/bin/bash` shebang for installation
- `./upload_package.sh` - Bash script with `#!/bin/bash` shebang for publishing

### Current Implementation Problems

1. **Direct Execution Issues**: Windows cannot directly execute files with bash shebangs
2. **Complex Windows Bash Detection**: `utils.py:_find_bash_on_windows()` has elaborate bash discovery logic
3. **Mixed Command Execution**: The codebase uses `_to_exec_str()` and `_to_exec_args()` to handle cross-platform execution
4. **Shell Parameter Usage**: Commands are executed with `shell=True` which can be inconsistent

### Current Code Locations with Shebang Handling

#### main.py (lines 139-174, 217-235)
- Lint execution: `cmd = "./lint" + (" --verbose" if verbose else "")`
- Test execution: `test_cmd = "./test" + (" --verbose" if verbose else "")`
- Uses `_to_exec_str(cmd, bash=True)` and `run_command_with_timeout()`

#### utils.py (lines 107-193)
- `_find_bash_on_windows()`: Complex bash executable discovery
- `_to_exec_str()`: Command string conversion for Windows bash execution
- `_to_exec_args()`: Command argument list conversion
- `_exec()`: Main execution function with cross-platform handling

## Recommended Solution: Lexical Shebang Processing Library

### Option 1: Lexical Parser-based Shebang Processor (Recommended)

The current whitelist approach in the existing design will miss modern shebang styles like UV's `#!/usr/bin/env -S uv run` or other complex argument patterns. The solution is to implement lexical parsing for accurate shebang interpretation.

Create a custom shebang processor using lexical parsing with Python's standard library:

```python
import os
import sys
import shlex
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple, Dict

class ShebangProcessor:
    """Cross-platform shebang line processor with lexical parsing for script execution."""

    def lex_parse_shebang(self, shebang_line: str) -> Optional[Tuple[str, List[str]]]:
        """Lexically parse shebang line to extract interpreter and arguments."""

    def parse_shebang(self, script_path: str) -> Optional[Tuple[str, List[str]]]:
        """Parse shebang line and return interpreter and args using lexical parsing."""

    def get_command_for_script(self, script_path: str) -> List[str]:
        """Get the full command needed to execute a script."""

    def execute_script(self, script_path: str, args: List[str] = None) -> int:
        """Execute script with proper shebang handling."""
```

### Key Advantages of Lexical Parsing Approach

1. **Accurate Parsing**: Handles complex argument structures like `-S` flags and multiple arguments
2. **Future-Proof**: Supports new shebang patterns without code changes
3. **Exact Results**: Produces precise interpreter and argument extraction
4. **Standards Compliant**: Follows POSIX shebang parsing rules

### Option 2: Use py-launcher for Python scripts (Windows only)

Windows Python Launcher (`py.exe`) can handle Python shebangs, but doesn't help with bash scripts.

### Option 3: Third-party Libraries

Research showed limited options for comprehensive shebang processing. Most solutions use:
- `subprocess` with platform detection
- `sys.executable` for Python scripts
- Manual interpreter detection

## Implementation Plan

### Phase 0: Comprehensive Shebang Unit Testing (FIRST TASK)

**CRITICAL**: Before implementing the lexical parser, create a comprehensive unit test with 20 diverse shebang styles to validate the parsing accuracy. This test will drive the implementation and ensure we handle all edge cases.

Create `tests/test_shebang_comprehensive.py` with test cases covering:

1. `#!/bin/bash` - Standard bash
2. `#!/usr/bin/env python` - Standard Python via env
3. `#!/usr/bin/env -S uv run` - UV with -S flag
4. `#!/usr/bin/env -S uv run --python 3.12` - UV with multiple args
5. `#!/usr/bin/env -S python -u` - Python with unbuffered flag
6. `#!/usr/bin/env -S python -O` - Python with optimization
7. `#!/usr/bin/env -S node --experimental-modules` - Node with experimental features
8. `#!/usr/bin/env -S deno run --allow-net` - Deno with permissions
9. `#!/usr/bin/python3 -u -O` - Direct python with flags
10. `#!/bin/sh -e` - Shell with error exit
11. `#!/usr/bin/env ruby -w` - Ruby with warnings
12. `#!/usr/bin/env -S rust-script --edition 2021` - Rust script with edition
13. `#!/usr/bin/env -S cargo +nightly run` - Cargo with toolchain
14. `#!/usr/bin/env -S julia --threads=auto` - Julia with threading
15. `#!/usr/bin/env -S R --vanilla` - R with vanilla mode
16. `#!/usr/bin/env -S php -n` - PHP without ini
17. `#!/usr/bin/env -S go run` - Go run command
18. `#!/usr/bin/env -S dotnet script` - .NET script
19. `#!/usr/bin/env -S pwsh -NoProfile` - PowerShell without profile
20. `#!/usr/bin/env -S zig run` - Zig run command


##### Additional test cases

  Shells (Bash, sh)
   1. #!/bin/bash - Standard for Bash scripts.
   2. #!/bin/sh -e - Uses the basic POSIX shell and exits immediately if a
      command fails.
   3. #!/bin/bash -x - Executes the script in debug mode, printing each
      command.
   4. #!/usr/bin/env bash - Locates the bash interpreter in the user's
      PATH.
   5. #!/bin/bash -- - Signals the end of options, preventing script
      arguments from being treated as shell options.


  Python
   6. #!/usr/bin/env python3 - A portable way to run Python 3.
   7. #!/usr/bin/python3 -u - Runs Python with unbuffered binary stdout and
       stderr.
   8. #!/usr/bin/env -S python3 -u -O - Uses env -S to pass multiple flags
      (unbuffered and optimized).
   9. #!/usr/bin/env -S uv run - Executes the script using the uv virtual
      environment and package manager.
   10. #!/usr/bin/env -S uv run --python 3.12 - uv with a specific Python
       version.


  Node.js / Deno
   11. #!/usr/bin/env node - Standard for Node.js scripts.
   12. #!/usr/bin/env -S node --experimental-modules - Node.js with a
       feature flag enabled.
   13. #!/usr/bin/env -S deno run --allow-net - Runs a Deno script with
       specific permissions.


  Other Scripting Languages
   14. #!/usr/bin/env ruby -w - Runs Ruby with warnings enabled.
   15. #!/usr/bin/env perl -T - Runs Perl in "taint" mode for security
       checks.
   16. #!/usr/bin/env -S php -n - Runs PHP without loading the php.ini
       configuration file.
   17. #!/usr/bin/env Rscript - Runs an R script.
   18. #!/usr/bin/env -S R --vanilla - Runs R in a clean environment.


  Scripting with Compiled Languages
   19. #!/usr/bin/env -S go run - Compiles and runs a Go program.
   20. #!/usr/bin/env -S dotnet script - Executes a C# script using .NET.
   21. #!/usr/bin/env -S rust-script --edition 2021 - Runs a Rust script
       with a specific language edition.
   22. #!/usr/bin/env -S zig run - Compiles and runs a Zig program.
   23. #!/usr/bin/env -S java --source 11 - Runs a single-file Java program
       (Java 11+).


  System & Administrative
   24. #!/usr/bin/env -S pwsh -NoProfile - Runs a PowerShell script without
       loading profile configurations.
   25. #!/usr/bin/env -S julia --threads=auto - Runs a Julia script with
       automatic thread allocation.
   26. #!/bin/false - Prevents a file from being executed, immediately
       exiting with an error.


  Advanced / Polyglot
   27. #!/bin/sh\n"exec" "python" "$0" "$@" - A polyglot shebang that allows
        a script to be run by sh, which then executes it with python.

Each test case should assert the expected program mapping and argument extraction.

### Phase 1: Create Shebang Processor Module

Create `src/codeup/shebang_processor.py`:

```python
"""Cross-platform shebang processing for script execution."""

import os
import re
import sys
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple, Dict

class ShebangProcessor:
    """Handles lexical shebang parsing and cross-platform script execution."""

    def __init__(self):
        self._bash_exe = None
        if sys.platform == 'win32':
            self._bash_exe = self._find_bash_executable()

    def lex_parse_shebang(self, shebang_line: str) -> Optional[Tuple[str, List[str]]]:
        """Lexically parse shebang line using shlex for accurate token extraction."""

    def resolve_interpreter(self, interpreter: str) -> str:
        """Resolve interpreter path to Windows-compatible executable."""

    def parse_shebang(self, script_path: str) -> Optional[Tuple[str, List[str]]]:
        """Parse the shebang line from a script file using lexical parsing."""

    def get_execution_command(self, script_path: str, script_args: List[str] = None) -> List[str]:
        """Get the command needed to execute the script on current platform."""

    def execute_script(self, script_path: str, script_args: List[str] = None, **kwargs) -> int:
        """Execute script with cross-platform shebang handling."""
```

### Phase 2: Update Execution Functions

Modify `src/codeup/utils.py`:

1. **Replace** `_find_bash_on_windows()`, `_to_exec_str()`, `_to_exec_args()` with shebang processor
2. **Update** `_exec()` to use `ShebangProcessor.execute_script()`
3. **Simplify** command execution logic

### Phase 3: Update Main Workflow

Modify `src/codeup/main.py`:

1. **Replace** manual `./lint` and `./test` command building
2. **Use** `ShebangProcessor` for direct script execution
3. **Remove** bash-specific string manipulation

### Phase 4: Update Process Management

Modify `src/codeup/running_process.py`:

1. **Add** shebang-aware process execution functions
2. **Integrate** with `ShebangProcessor`
3. **Maintain** streaming output capabilities

### Phase 5: Testing

1. **Add** comprehensive tests for `ShebangProcessor`
2. **Test** on Windows with different bash installations (Git Bash, MSYS2, WSL)
3. **Ensure** backward compatibility on Unix systems
4. **Add** integration tests for `./lint` and `./test` execution

## Benefits of This Approach

1. **Unified Handling**: Single point of shebang processing logic
2. **Better Error Messages**: Clear feedback when interpreters are missing
3. **Extensible**: Easy to add support for new interpreters
4. **Testable**: Can unit test shebang parsing and command generation
5. **Maintainable**: Eliminates complex bash discovery and string manipulation
6. **Cross-platform**: Works consistently across Windows, macOS, and Linux

## Migration Strategy

1. **Implement** `ShebangProcessor` alongside existing code
2. **Update** one execution path at a time (lint, then test, then others)
3. **Keep** existing functions as fallbacks during transition
4. **Remove** legacy code after thorough testing
5. **Update** documentation with new execution model

## Fallback Strategy

If shebang processing fails:
1. **Try** direct execution (for systems with proper associations)
2. **Fall back** to current `_find_bash_on_windows()` logic
3. **Provide** clear error messages with suggestions for fixing interpreter issues

This approach provides a robust, maintainable solution for cross-platform script execution while preserving the existing functionality and improving error handling.



## Addendum:

No tuples! use @dataclass. Scan the shebang processor for tuples and replace. Then make this a rule in CLAUDE.ME