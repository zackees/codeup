import argparse
import json
import logging
import os
import sys

from appdirs import user_config_dir  # type: ignore

logger = logging.getLogger(__name__)


def get_config_path() -> str:
    env_path = user_config_dir("zcmds", "zcmds", roaming=True)
    config_file = os.path.join(env_path, "openai.json")
    return config_file


def save_config(config: dict) -> None:
    config_file = get_config_path()
    # make all subdirs of config_file
    os.makedirs(os.path.dirname(config_file), exist_ok=True)
    with open(config_file, "w") as f:
        json.dump(config, f)


def create_or_load_config() -> dict:
    config_file = get_config_path()
    try:
        with open(config_file) as f:
            config = json.loads(f.read())
        return config
    except OSError as e:
        logger.warning(f"Could not load config file: {e}")
        save_config({})
        return {}


def get_anthropic_api_key() -> str | None:
    """Get Anthropic API key from various sources in order of preference."""
    # Use the new keyring module which has config_manager parameter
    import codeup.config as config_module
    from codeup.keyring import get_anthropic_api_key as keyring_get_anthropic_key

    return keyring_get_anthropic_key(config_module)


def get_openai_api_key() -> str | None:
    """Get OpenAI API key from various sources in order of preference."""
    # Use the new keyring module which has config_manager parameter
    import codeup.config as config_module
    from codeup.keyring import get_openai_api_key as keyring_get_openai_key

    return keyring_get_openai_key(config_module)


def _set_key_in_keyring(service: str, key_name: str, api_key: str) -> bool:
    """Set API key in system keyring. Returns True if successful."""
    from codeup.keyring import KeyringManager

    keyring_manager = KeyringManager(service)
    if keyring_manager.set_password(key_name, api_key):
        return True
    else:
        if not keyring_manager.is_keyring_available():
            print("Error: keyring not available. Install with: pip install keyring")
        return False


def _set_key_in_config(key_name: str, api_key: str) -> bool:
    """Set API key in config file. Returns True if successful."""
    try:
        config = create_or_load_config()
        config[key_name] = api_key
        save_config(config)
        return True
    except Exception as e:
        logger.error(f"Error storing key in config: {e}")
        print(f"Error storing key in config: {e}")
        return False


def _determine_key_source(config_key: str, env_var: str, key_value: str | None) -> str:
    """Determine the source of an API key."""
    if key_value is None:
        return "none"

    # Check if it matches environment variable
    if key_value == os.environ.get(env_var):
        return "environment variable"

    # Check if it's in config file
    config = create_or_load_config()
    if config_key in config and config[config_key] == key_value:
        return "config file"

    # Otherwise assume it's from keyring
    return "keyring"


def _show_key_status(key_name: str, source: str, key_value: str | None) -> None:
    """Show masked key status."""
    if key_value:
        masked_key = (
            key_value[:8] + "..." + key_value[-4:] if len(key_value) > 12 else "***"
        )
        print(f"{key_name}: {masked_key} (from {source})")
    else:
        print(f"{key_name}: Not set")


def main() -> int:
    """Main function for openaicfg command - unified AI API key management."""
    parser = argparse.ArgumentParser(
        prog="openaicfg",
        description="Manage OpenAI and Anthropic API keys securely",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  openaicfg --set-key-anthropic sk-ant-...     Set Anthropic key in keyring (secure)
  openaicfg --set-key-openai sk-...           Set OpenAI key in keyring (secure)
  openaicfg --set-key-anthropic sk-ant-... --use-config  Store in config file instead
  openaicfg --show-keys                       Show current key status
        """,
    )

    parser.add_argument(
        "--set-key-anthropic",
        type=str,
        metavar="KEY",
        help="Set Anthropic API key",
    )

    parser.add_argument(
        "--set-key-openai",
        type=str,
        metavar="KEY",
        help="Set OpenAI API key",
    )

    parser.add_argument(
        "--use-config",
        action="store_true",
        help="Store key in config file instead of keyring",
    )

    parser.add_argument(
        "--show-keys",
        action="store_true",
        help="Show current API key status (masked for security)",
    )

    args = parser.parse_args()

    # Show keys status
    if args.show_keys:
        print("API Key Status:")
        print("-" * 40)

        # Check OpenAI key
        openai_key = get_openai_api_key()
        source = _determine_key_source("openai_key", "OPENAI_API_KEY", openai_key)
        _show_key_status("OpenAI", source, openai_key)

        # Check Anthropic key
        anthropic_key = get_anthropic_api_key()
        source = _determine_key_source(
            "anthropic_key", "ANTHROPIC_API_KEY", anthropic_key
        )
        _show_key_status("Anthropic", source, anthropic_key)
        return 0

    # Set Anthropic key
    if args.set_key_anthropic:
        import codeup.config as config_module
        from codeup.keyring import set_anthropic_api_key

        if set_anthropic_api_key(
            args.set_key_anthropic,
            prefer_config=args.use_config,
            config_manager=config_module,
        ):
            return 0
        return 1

    # Set OpenAI key
    if args.set_key_openai:
        import codeup.config as config_module
        from codeup.keyring import set_openai_api_key

        if set_openai_api_key(
            args.set_key_openai,
            prefer_config=args.use_config,
            config_manager=config_module,
        ):
            return 0
        return 1

    # If no specific action, show help
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
