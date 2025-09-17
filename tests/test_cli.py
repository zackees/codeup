"""
Unit test file.
"""

import unittest


class MainTester(unittest.TestCase):
    """Main tester class."""

    def test_imports(self) -> None:
        """Test that the codeup package structure is correct."""
        import os

        # Find the source directory - this should be very fast
        current_dir = os.path.dirname(os.path.abspath(__file__))
        src_dir = os.path.join(os.path.dirname(current_dir), "src", "codeup")

        # Verify key files exist - just file system checks, no imports
        key_files = ["main.py", "args.py", "config.py", "__init__.py"]
        for file_name in key_files:
            file_path = os.path.join(src_dir, file_name)
            self.assertTrue(
                os.path.exists(file_path), f"{file_name} should exist in codeup package"
            )

        # Verify these files are not empty (basic sanity check)
        for file_name in key_files:
            file_path = os.path.join(src_dir, file_name)
            self.assertGreater(
                os.path.getsize(file_path), 0, f"{file_name} should not be empty"
            )


if __name__ == "__main__":
    unittest.main()
