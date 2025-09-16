"""Cross-platform shebang processing for script execution.

This module provides lexical parsing of shebang lines to handle modern
patterns like UV's '#!/usr/bin/env -S uv run --python 3.12' accurately.
"""

import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class ShebangResult:
    """Result of shebang parsing containing program and arguments."""

    program: str
    args: List[str]


class ShebangProcessor:
    """Handles lexical shebang parsing and cross-platform script execution."""

    def __init__(self):
        """Initialize the ShebangProcessor."""
        self._bash_exe = None
        if sys.platform == "win32":
            self._bash_exe = self._find_bash_executable()

    def lex_parse_shebang(self, shebang_line: str) -> Optional[ShebangResult]:
        """Lexically parse shebang line using shlex for accurate token extraction.

        Args:
            shebang_line: The shebang line to parse (e.g., "#!/usr/bin/env -S uv run")

        Returns:
            ShebangResult or None if parsing fails

        Examples:
            >>> processor = ShebangProcessor()
            >>> processor.lex_parse_shebang("#!/usr/bin/env -S uv run --python 3.12")
            ShebangResult(program='uv', args=['run', '--python', '3.12'])
            >>> processor.lex_parse_shebang("#!/bin/bash")
            ShebangResult(program='bash', args=[])
        """
        if not shebang_line or not shebang_line.startswith("#!"):
            return None

        # Remove the #! prefix and strip whitespace
        command_line = shebang_line[2:].strip()
        if not command_line:
            return None

        try:
            # Use shlex to properly tokenize the command line
            tokens = shlex.split(command_line)
            if not tokens:
                return None

            # Handle different shebang patterns
            if len(tokens) == 1:
                # Simple case: #!/bin/bash or #!/usr/bin/python
                program = Path(tokens[0]).name
                # Handle edge case where program is empty (e.g., "#!/")
                if not program:
                    return None
                return ShebangResult(program=program, args=[])

            # Check for /usr/bin/env patterns
            if tokens[0].endswith("/env"):
                return self._parse_env_shebang(tokens[1:])
            else:
                # Direct interpreter with args: #!/usr/bin/python3 -u -O
                program = Path(tokens[0]).name
                args = tokens[1:]
                return ShebangResult(program=program, args=args)

        except ValueError:
            # shlex.split can raise ValueError for malformed input
            return None

    def _parse_env_shebang(self, env_args: List[str]) -> Optional[ShebangResult]:
        """Parse env-based shebang arguments.

        Args:
            env_args: Arguments after /usr/bin/env

        Returns:
            ShebangResult or None if parsing fails
        """
        if not env_args:
            return None

        # Handle -S flag for env
        if env_args[0] == "-S":
            if len(env_args) < 2:
                return None
            # After -S, the next token is the program
            program = env_args[1]
            args = env_args[2:]
            return ShebangResult(program=program, args=args)
        else:
            # Standard env usage: /usr/bin/env python
            program = env_args[0]
            args = env_args[1:]
            return ShebangResult(program=program, args=args)

    def _find_bash_executable(self) -> Optional[str]:
        """Find bash executable on Windows.

        Returns:
            Path to bash executable or None if not found
        """
        # Common locations for bash on Windows
        possible_paths = [
            "bash",  # If in PATH
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\msys64\usr\bin\bash.exe",
            r"C:\msys32\usr\bin\bash.exe",
            r"C:\cygwin64\bin\bash.exe",
            r"C:\cygwin\bin\bash.exe",
        ]

        for path in possible_paths:
            try:
                result = subprocess.run(
                    [path, "--version"], capture_output=True, timeout=5
                )
                if result.returncode == 0:
                    return path
            except (subprocess.SubprocessError, FileNotFoundError, OSError):
                continue

        return None

    def resolve_interpreter(self, interpreter: str) -> str:
        """Resolve interpreter path to Windows-compatible executable.

        Args:
            interpreter: The interpreter name (e.g., 'python', 'bash')

        Returns:
            Resolved interpreter path
        """
        if sys.platform != "win32":
            return interpreter

        # Special handling for common interpreters on Windows
        if interpreter in ("bash", "sh"):
            if self._bash_exe:
                return self._bash_exe
            return interpreter
        elif interpreter in ("python", "python3"):
            return sys.executable
        else:
            return interpreter

    def parse_shebang(self, script_path: str) -> Optional[ShebangResult]:
        """Parse the shebang line from a script file using lexical parsing.

        Args:
            script_path: Path to the script file

        Returns:
            ShebangResult or None if no shebang found
        """
        try:
            with open(script_path, encoding="utf-8") as f:
                first_line = f.readline().strip()
                return self.lex_parse_shebang(first_line)
        except (OSError, UnicodeDecodeError):
            return None

    def get_execution_command(
        self, script_path: str, script_args: Optional[List[str]] = None
    ) -> List[str]:
        """Get the command needed to execute the script on current platform.

        Args:
            script_path: Path to the script file
            script_args: Additional arguments to pass to the script

        Returns:
            Command list ready for subprocess execution
        """
        if script_args is None:
            script_args = []

        shebang_result = self.parse_shebang(script_path)
        if not shebang_result:
            # No shebang found, try direct execution
            return [script_path] + script_args

        resolved_program = self.resolve_interpreter(shebang_result.program)

        return [resolved_program] + shebang_result.args + [script_path] + script_args

    def execute_script(
        self, script_path: str, script_args: Optional[List[str]] = None, **kwargs
    ) -> int:
        """Execute script with cross-platform shebang handling.

        Args:
            script_path: Path to the script file
            script_args: Additional arguments to pass to the script
            **kwargs: Additional keyword arguments for subprocess.run

        Returns:
            Exit code from script execution
        """
        command = self.get_execution_command(script_path, script_args)

        try:
            result = subprocess.run(command, **kwargs)
            return result.returncode
        except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
            # Log error and return non-zero exit code
            print(f"Error executing script {script_path}: {e}", file=sys.stderr)
            return 1
