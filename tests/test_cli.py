"""
Unit test file.
"""

import os
import unittest

COMMAND = "codeup"


class MainTester(unittest.TestCase):
    """Main tester class."""

    def test_imports(self) -> None:
        """Test command line interface (CLI)."""
        # Test that codeup exits with code 1 when no changes to commit (expected behavior)
        rtn = os.system(COMMAND)
        self.assertEqual(1, rtn)  # codeup should exit 1 when no changes to commit


if __name__ == "__main__":
    unittest.main()
