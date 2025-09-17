"""
Keyring abstraction for secure API key management.

This module provides a unified interface for storing and retrieving API keys
with multiple fallback mechanisms:
1. System keyring (primary, most secure)
2. Config file (fallback if keyring unavailable)
3. Environment variables (final fallback)
4. semi_secret library (guaranteed fallback for keyring functionality)

The semi_secret library is always available as it's a required dependency,
ensuring that keyring functionality never completely fails.
"""

import logging
import os
from pathlib import Path

from semi_secret import SecretStorage, generate_key

logger = logging.getLogger(__name__)


class KeyringManager:
    """Manages API keys with multiple storage backends and fallbacks."""

    def __init__(self, service_name: str = "zcmds"):
        self.service_name = service_name
        self._keyring_backend = None
        self._keyring_available = None

    def _get_keyring_backend(self):
        """Get keyring backend with fallback to semi_secret."""
        if self._keyring_backend is not None:
            return self._keyring_backend

        # Try standard keyring first
        try:
            import keyring

            self._keyring_backend = keyring
            self._keyring_available = True
            logger.debug("Using standard keyring backend")
            return self._keyring_backend
        except ImportError:
            logger.debug("Standard keyring not available, trying semi_secret")

        # Fallback to semi_secret
        class SemiSecretAdapter:
            """Adapter to make semi_secret compatible with keyring interface."""

            def __init__(self):
                # Create a default storage path in user's config directory
                config_dir = Path.home() / ".config" / "zcmds"
                config_dir.mkdir(parents=True, exist_ok=True)
                storage_path = config_dir / "keyring.dat"

                # Use a default key - in production this should be more secure
                key = generate_key()
                salt = "zcmds_keyring_salt"

                self.storage = SecretStorage(key, salt, storage_path)

            def get_password(self, service: str, username: str) -> str | None:
                try:
                    return self.storage.get(f"{service}:{username}")
                except Exception as e:
                    logger.debug(f"semi_secret get failed: {e}")
                    return None

            def set_password(self, service: str, username: str, password: str) -> None:
                self.storage.set(f"{service}:{username}", password)

            def delete_password(self, service: str, username: str) -> None:
                try:
                    self.storage.delete(f"{service}:{username}")
                except Exception as e:
                    logger.debug(f"semi_secret delete failed: {e}")

        self._keyring_backend = SemiSecretAdapter()
        self._keyring_available = True
        logger.debug("Using semi_secret keyring backend")
        return self._keyring_backend

    def is_keyring_available(self) -> bool:
        """Check if any keyring backend is available."""
        if self._keyring_available is not None:
            return self._keyring_available

        backend = self._get_keyring_backend()
        return backend is not None

    def get_password(self, username: str) -> str | None:
        """Get password from keyring backend."""
        backend = self._get_keyring_backend()
        if backend is None:
            return None

        try:
            return backend.get_password(self.service_name, username)
        except Exception as e:
            logger.debug(f"Error getting password from keyring: {e}")
            return None

    def set_password(self, username: str, password: str) -> bool:
        """Set password in keyring backend. Returns True if successful."""
        backend = self._get_keyring_backend()
        if backend is None:
            return False

        try:
            backend.set_password(self.service_name, username, password)
            return True
        except Exception as e:
            logger.error(f"Error setting password in keyring: {e}")
            return False

    def delete_password(self, username: str) -> bool:
        """Delete password from keyring backend. Returns True if successful."""
        backend = self._get_keyring_backend()
        if backend is None:
            return False

        try:
            backend.delete_password(self.service_name, username)
            return True
        except Exception as e:
            logger.debug(f"Error deleting password from keyring: {e}")
            return False


class APIKeyManager:
    """High-level API key management with multiple storage layers."""

    def __init__(
        self, config_manager=None, keyring_manager: KeyringManager | None = None
    ):
        self.keyring_manager = keyring_manager or KeyringManager()
        self.config_manager = config_manager

    def get_api_key(
        self, key_name: str, keyring_username: str, config_key: str, env_var: str
    ) -> str | None:
        """
        Get API key from multiple sources in order of preference:
        1. Config file (if config_manager provided)
        2. Keyring/keystore
        3. Environment variable
        """
        # 1. Check config file first (if available)
        if self.config_manager:
            try:
                config = self.config_manager.create_or_load_config()
                if config_key in config and config[config_key]:
                    logger.debug(f"Found {key_name} key in config file")
                    return config[config_key]
            except Exception as e:
                logger.debug(f"Error accessing config for {key_name}: {e}")

        # 2. Check keyring/keystore
        api_key = self.keyring_manager.get_password(keyring_username)
        if api_key:
            logger.debug(f"Found {key_name} key in keyring")
            return api_key

        # 3. Check environment variable
        env_key = os.environ.get(env_var)
        if env_key:
            logger.debug(f"Found {key_name} key in environment variable")
            return env_key

        logger.debug(f"No {key_name} key found in any source")
        return None

    def set_api_key(
        self,
        key_name: str,
        api_key: str,
        keyring_username: str,
        config_key: str,
        prefer_config: bool = False,
    ) -> bool:
        """
        Set API key with preference for keyring unless prefer_config is True.
        Returns True if successful.
        """
        if prefer_config and self.config_manager:
            try:
                config = self.config_manager.create_or_load_config()
                config[config_key] = api_key
                self.config_manager.save_config(config)
                logger.info(f"{key_name} API key stored in config file")
                return True
            except Exception as e:
                logger.error(f"Error storing {key_name} key in config: {e}")
                return False

        # Try keyring first
        if self.keyring_manager.set_password(keyring_username, api_key):
            logger.info(f"{key_name} API key stored in keyring")
            return True

        # Fallback to config if keyring fails and config manager is available
        if self.config_manager:
            try:
                config = self.config_manager.create_or_load_config()
                config[config_key] = api_key
                self.config_manager.save_config(config)
                logger.info(
                    f"{key_name} API key stored in config file (keyring unavailable)"
                )
                return True
            except Exception as e:
                logger.error(f"Error storing {key_name} key in config fallback: {e}")

        logger.error(f"Failed to store {key_name} API key")
        return False

    def get_openai_api_key(self) -> str | None:
        """Get OpenAI API key from configured sources."""
        return self.get_api_key(
            key_name="OpenAI",
            keyring_username="openai_api_key",
            config_key="openai_key",
            env_var="OPENAI_API_KEY",
        )

    def get_anthropic_api_key(self) -> str | None:
        """Get Anthropic API key from configured sources."""
        return self.get_api_key(
            key_name="Anthropic",
            keyring_username="anthropic_api_key",
            config_key="anthropic_key",
            env_var="ANTHROPIC_API_KEY",
        )

    def set_openai_api_key(self, api_key: str, prefer_config: bool = False) -> bool:
        """Set OpenAI API key."""
        return self.set_api_key(
            key_name="OpenAI",
            api_key=api_key,
            keyring_username="openai_api_key",
            config_key="openai_key",
            prefer_config=prefer_config,
        )

    def set_anthropic_api_key(self, api_key: str, prefer_config: bool = False) -> bool:
        """Set Anthropic API key."""
        return self.set_api_key(
            key_name="Anthropic",
            api_key=api_key,
            keyring_username="anthropic_api_key",
            config_key="anthropic_key",
            prefer_config=prefer_config,
        )


# Global instance for backward compatibility
_default_keyring_manager = KeyringManager()
_default_api_key_manager = None


def get_default_api_key_manager(config_manager=None) -> APIKeyManager:
    """Get default API key manager instance."""
    global _default_api_key_manager
    if _default_api_key_manager is None or (
        config_manager and _default_api_key_manager.config_manager != config_manager
    ):
        _default_api_key_manager = APIKeyManager(
            config_manager, _default_keyring_manager
        )
    return _default_api_key_manager


# Convenience functions for backward compatibility
def get_openai_api_key(config_manager=None) -> str | None:
    """Get OpenAI API key - convenience function."""
    return get_default_api_key_manager(config_manager).get_openai_api_key()


def get_anthropic_api_key(config_manager=None) -> str | None:
    """Get Anthropic API key - convenience function."""
    return get_default_api_key_manager(config_manager).get_anthropic_api_key()


def set_openai_api_key(
    api_key: str, prefer_config: bool = False, config_manager=None
) -> bool:
    """Set OpenAI API key - convenience function."""
    return get_default_api_key_manager(config_manager).set_openai_api_key(
        api_key, prefer_config
    )


def set_anthropic_api_key(
    api_key: str, prefer_config: bool = False, config_manager=None
) -> bool:
    """Set Anthropic API key - convenience function."""
    return get_default_api_key_manager(config_manager).set_anthropic_api_key(
        api_key, prefer_config
    )
