"""Comprehensive shebang parsing unit tests.

This test module validates the ShebangProcessor's ability to correctly parse
20 diverse shebang patterns using lexical parsing. These tests drive the
implementation to ensure accurate handling of modern shebang styles.
"""

import pytest
from src.codeup.shebang_processor import ShebangProcessor, ShebangResult


class TestShebangProcessorComprehensive:
    """Test comprehensive shebang parsing with 20 diverse patterns."""

    def setup_method(self):
        """Set up ShebangProcessor instance for each test."""
        self.processor = ShebangProcessor()

    @pytest.mark.parametrize("shebang_line,expected_program,expected_args", [
        # Standard interpreters
        ("#!/bin/bash", "bash", []),
        ("#!/usr/bin/env python", "python", []),

        # UV patterns with -S flag
        ("#!/usr/bin/env -S uv run", "uv", ["run"]),
        ("#!/usr/bin/env -S uv run --python 3.12", "uv", ["run", "--python", "3.12"]),

        # Python with flags
        ("#!/usr/bin/env -S python -u", "python", ["-u"]),
        ("#!/usr/bin/env -S python -O", "python", ["-O"]),
        ("#!/usr/bin/python3 -u -O", "python3", ["-u", "-O"]),

        # Node.js and Deno
        ("#!/usr/bin/env -S node --experimental-modules", "node", ["--experimental-modules"]),
        ("#!/usr/bin/env -S deno run --allow-net", "deno", ["run", "--allow-net"]),

        # Shell with flags
        ("#!/bin/sh -e", "sh", ["-e"]),

        # Ruby with warnings
        ("#!/usr/bin/env ruby -w", "ruby", ["-w"]),

        # Rust tooling
        ("#!/usr/bin/env -S rust-script --edition 2021", "rust-script", ["--edition", "2021"]),
        ("#!/usr/bin/env -S cargo +nightly run", "cargo", ["+nightly", "run"]),

        # Julia with threading
        ("#!/usr/bin/env -S julia --threads=auto", "julia", ["--threads=auto"]),

        # R with vanilla mode
        ("#!/usr/bin/env -S R --vanilla", "R", ["--vanilla"]),

        # PHP without ini
        ("#!/usr/bin/env -S php -n", "php", ["-n"]),

        # Go run command
        ("#!/usr/bin/env -S go run", "go", ["run"]),

        # .NET script
        ("#!/usr/bin/env -S dotnet script", "dotnet", ["script"]),

        # PowerShell without profile
        ("#!/usr/bin/env -S pwsh -NoProfile", "pwsh", ["-NoProfile"]),

        # Zig run command
        ("#!/usr/bin/env -S zig run", "zig", ["run"]),
    ])
    def test_lex_parse_shebang_patterns(self, shebang_line, expected_program, expected_args):
        """Test lexical parsing of diverse shebang patterns."""
        result = self.processor.lex_parse_shebang(shebang_line)

        assert result is not None, f"Failed to parse shebang: {shebang_line}"
        assert isinstance(result, ShebangResult), f"Expected ShebangResult, got {type(result)}"

        assert result.program == expected_program, (
            f"Program mismatch for '{shebang_line}': "
            f"expected '{expected_program}', got '{result.program}'"
        )
        assert result.args == expected_args, (
            f"Args mismatch for '{shebang_line}': "
            f"expected {expected_args}, got {result.args}"
        )

    def test_invalid_shebang_lines(self):
        """Test handling of invalid shebang patterns."""
        invalid_shebangs = [
            "",  # Empty string
            "not a shebang",  # No shebang prefix
            "#!",  # Just shebang prefix
            "#!/",  # Incomplete path
        ]

        for invalid_shebang in invalid_shebangs:
            result = self.processor.lex_parse_shebang(invalid_shebang)
            assert result is None, f"Should return None for invalid shebang: '{invalid_shebang}'"

    def test_whitespace_handling(self):
        """Test proper handling of whitespace in shebang lines."""
        test_cases = [
            ("#!/bin/bash   ", "bash", []),  # Trailing whitespace
            ("#!/usr/bin/env  python", "python", []),  # Extra spaces
            ("#!/usr/bin/env -S  python  -u", "python", ["-u"]),  # Multiple spaces
        ]

        for shebang_line, expected_program, expected_args in test_cases:
            result = self.processor.lex_parse_shebang(shebang_line)
            assert result is not None
            assert result.program == expected_program
            assert result.args == expected_args

    def test_complex_quoted_arguments(self):
        """Test handling of quoted arguments in shebang lines."""
        test_cases = [
            ('#!/usr/bin/env -S python -c "import sys; print(sys.version)"',
             "python", ["-c", "import sys; print(sys.version)"]),
            ("#!/usr/bin/env -S node --eval 'console.log(\"hello\")'",
             "node", ["--eval", 'console.log("hello")']),
        ]

        for shebang_line, expected_program, expected_args in test_cases:
            result = self.processor.lex_parse_shebang(shebang_line)
            assert result is not None
            assert result.program == expected_program
            assert result.args == expected_args