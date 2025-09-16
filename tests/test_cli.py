"""
Unit test file.
"""

import os
import sys
import unittest

COMMAND = "codeup"


class MainTester(unittest.TestCase):
    """Main tester class."""

    def test_imports(self) -> None:
        """Test command line interface (CLI)."""
        # Test that codeup exits with code 1 when no changes to commit (expected behavior)
        rtn = os.system(COMMAND)
        # os.system() returns the exit code shifted left by 8 bits on Unix systems
        # On Windows, it returns the exit code directly
        if sys.platform == "win32":
            expected_exit_code = 1
        else:
            expected_exit_code = 256  # 1 << 8
        self.assertEqual(
            expected_exit_code, rtn
        )  # codeup should exit 1 when no changes to commit


if __name__ == "__main__":
    unittest.main()
