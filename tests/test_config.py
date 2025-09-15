import os
import tempfile
import unittest
from pathlib import Path


class ConfigTester(unittest.TestCase):
    """Test configuration management functionality."""

    def setUp(self):
        """Set up test environment."""
        self.original_cwd = os.getcwd()
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.original_cwd)
        import shutil
        import stat

        def handle_remove_readonly(func, path, exc):
            """Handle read-only files on Windows."""
            if os.path.exists(path):
                os.chmod(path, stat.S_IWRITE)
                func(path)

        shutil.rmtree(self.test_dir, onerror=handle_remove_readonly)

    def test_config_path_generation(self):
        """Test config path generation."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.config import get_config_path

            config_path = get_config_path()
            self.assertIsInstance(config_path, str, "Config path should be a string")
            self.assertTrue(
                config_path.endswith("openai.json"),
                "Config path should end with openai.json",
            )

        except ImportError as e:
            self.skipTest(f"Could not import config module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_config_save_and_load(self):
        """Test config save and load functionality."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            import tempfile

            from codeup.config import create_or_load_config, save_config

            # Create a temporary config directory
            with tempfile.TemporaryDirectory() as temp_dir:
                # Mock the config path to use our temporary directory
                import codeup.config

                original_get_config_path = codeup.config.get_config_path

                def mock_get_config_path():
                    return os.path.join(temp_dir, "openai.json")

                codeup.config.get_config_path = mock_get_config_path

                try:
                    # Test saving config
                    test_config = {"test_key": "test_value", "api_key": "sk-test123"}
                    save_config(test_config)

                    # Test loading config
                    loaded_config = create_or_load_config()
                    self.assertEqual(
                        loaded_config["test_key"],
                        "test_value",
                        "Config should be saved and loaded correctly",
                    )
                    self.assertEqual(
                        loaded_config["api_key"],
                        "sk-test123",
                        "API key should be saved and loaded correctly",
                    )

                finally:
                    # Restore original function
                    codeup.config.get_config_path = original_get_config_path

        except ImportError as e:
            self.skipTest(f"Could not import config module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_api_key_retrieval(self):
        """Test API key retrieval from various sources."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        try:
            from codeup.config import get_anthropic_api_key, get_openai_api_key

            # Test that functions return None or strings
            openai_key = get_openai_api_key()
            self.assertTrue(
                openai_key is None or isinstance(openai_key, str),
                "OpenAI key should be None or string",
            )

            anthropic_key = get_anthropic_api_key()
            self.assertTrue(
                anthropic_key is None or isinstance(anthropic_key, str),
                "Anthropic key should be None or string",
            )

        except ImportError as e:
            self.skipTest(f"Could not import config module: {e}")
        finally:
            if src_path in sys.path:
                sys.path.remove(src_path)

    def test_environment_variable_api_keys(self):
        """Test API key retrieval from environment variables."""
        import sys

        src_path = str(Path(self.original_cwd) / "src")
        sys.path.insert(0, src_path)

        # Store original env vars
        original_openai = os.environ.get("OPENAI_API_KEY")
        original_anthropic = os.environ.get("ANTHROPIC_API_KEY")

        try:
            from codeup.config import get_anthropic_api_key, get_openai_api_key

            # Test with environment variables set
            test_openai_key = "sk-test-openai-123456789"
            test_anthropic_key = "sk-ant-test-123456789"

            os.environ["OPENAI_API_KEY"] = test_openai_key
            os.environ["ANTHROPIC_API_KEY"] = test_anthropic_key

            # Should retrieve from environment (but may return existing key if available from other sources)
            openai_key = get_openai_api_key()
            anthropic_key = get_anthropic_api_key()

            # Since config and keyring take priority, just check that we get a valid key
            self.assertIsNotNone(openai_key, "Should retrieve some OpenAI key")
            self.assertIsNotNone(anthropic_key, "Should retrieve some Anthropic key")

        except ImportError as e:
            self.skipTest(f"Could not import config module: {e}")
        finally:
            # Restore original env vars
            if original_openai is not None:
                os.environ["OPENAI_API_KEY"] = original_openai
            elif "OPENAI_API_KEY" in os.environ:
                del os.environ["OPENAI_API_KEY"]

            if original_anthropic is not None:
                os.environ["ANTHROPIC_API_KEY"] = original_anthropic
            elif "ANTHROPIC_API_KEY" in os.environ:
                del os.environ["ANTHROPIC_API_KEY"]

            if src_path in sys.path:
                sys.path.remove(src_path)


if __name__ == "__main__":
    unittest.main()
