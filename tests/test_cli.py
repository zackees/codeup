"""
Unit test file.
"""

import unittest

from codeup.running_process import run_command_with_streaming_and_capture

COMMAND = "codeup"


class MainTester(unittest.TestCase):
    """Main tester class."""

    def test_imports(self) -> None:
        """Test command line interface (CLI)."""
        # Test that codeup exits with code 1 when no changes to commit (expected behavior)
        exit_code, stdout, stderr = run_command_with_streaming_and_capture(
            [COMMAND], quiet=True
        )
        # codeup should exit 1 when no changes to commit
        self.assertEqual(1, exit_code)


if __name__ == "__main__":
    unittest.main()
