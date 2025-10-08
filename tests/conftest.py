"""Pytest configuration and fixtures for test optimization."""

import sys
from unittest.mock import patch

import pytest


def pytest_keyboard_interrupt(excinfo):
    """Handle Ctrl-C gracefully without verbose traceback.

    This prevents pytest-xdist from showing nested stack traces when
    parallel test execution is interrupted.
    """
    print("\n\nTests interrupted by user (Ctrl-C)", file=sys.stderr)
    # Return None to let pytest handle the exit, but suppress traceback formatting
    return None


def pytest_exception_interact(node, call, report):
    """Prevent traceback formatting during KeyboardInterrupt."""
    if call.excinfo and call.excinfo.type is KeyboardInterrupt:
        # Suppress traceback formatting for KeyboardInterrupt
        return True
    return None


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response for faster tests."""
    return "feat: add new functionality and improve documentation\n\nImplement new features and enhance project documentation"


@pytest.fixture
def mock_anthropic_response():
    """Mock Anthropic API response for faster tests."""
    return "docs: enhance README with features and installation guide"


@pytest.fixture
def mock_ai_apis(mock_openai_response, mock_anthropic_response):
    """Mock both AI API providers to avoid network calls."""
    with patch("codeup.main._generate_ai_commit_message") as mock_openai:
        with patch(
            "codeup.main._generate_ai_commit_message_anthropic"
        ) as mock_anthropic:
            mock_openai.return_value = mock_openai_response
            mock_anthropic.return_value = mock_anthropic_response
            yield {"openai": mock_openai, "anthropic": mock_anthropic}


@pytest.fixture
def mock_api_keys():
    """Mock API keys to avoid configuration dependencies."""
    with patch("codeup.config.get_openai_api_key", return_value="test-openai-key"):
        with patch(
            "codeup.config.get_anthropic_api_key", return_value="test-anthropic-key"
        ):
            yield
