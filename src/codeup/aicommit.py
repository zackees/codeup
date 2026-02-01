"""AI-powered commit message generation for codeup."""

import logging
import os
import sys
import threading

import openai

from codeup.git_utils import get_git_diff, get_git_diff_cached, safe_git_commit

logger = logging.getLogger(__name__)


class InputTimeoutError(Exception):
    """Raised when input times out."""

    pass


class AuthException(Exception):
    """Raised when API authentication fails due to missing or invalid keys."""

    def __init__(self, message: str, provider: str | None = None):
        self.provider = provider
        self.message = message
        super().__init__(message)

    def get_fix_instructions(self) -> str:
        """Return user-friendly instructions to fix the auth issue."""
        lines = [
            "To fix this, either:",
            "  1. Configure a valid API key:",
            "       export OPENAI_API_KEY=your_key",
            "       export ANTHROPIC_API_KEY=your_key",
            "  2. Or provide a commit message manually:",
            "       codeup -m 'your commit message'",
        ]
        return "\n".join(lines)


def _generate_ai_commit_message_anthropic(
    diff_text: str,
) -> str | AuthException | None:
    """Generate commit message using Anthropic Claude API as fallback.

    Returns:
        str: Successfully generated commit message
        AuthException: Authentication failed (missing or invalid key)
        None: Other failures (network, API errors, etc.)
    """
    try:
        import anthropic

        from codeup.config import get_anthropic_api_key

        api_key = get_anthropic_api_key()
        if not api_key:
            logger.info("No Anthropic API key found")
            return AuthException(
                "No Anthropic API key configured", provider="anthropic"
            )

        logger.info("Using Anthropic Claude API for commit message generation")
        client = anthropic.Anthropic(api_key=api_key)

        prompt = f"""You are an expert developer who writes clear, concise commit messages following conventional commit format.

Analyze the following git diff and generate a single line commit message that:
1. Follows conventional commit format (type(scope): description)
2. Uses one of these types: feat, fix, docs, style, refactor, perf, test, chore, ci, build
3. Is under 72 characters
4. Describes the main change concisely
5. Uses imperative mood (e.g., "add", not "added")

Git diff:
```
{diff_text}
```

Respond with only the commit message, nothing else."""

        response = client.messages.create(
            model="claude-3-haiku-20240307",  # Fast and cost-effective model
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )

        if response.content and len(response.content) > 0:
            first_block = response.content[0]
            # Check if it's a text block and has the text attribute
            if hasattr(first_block, "text"):
                from codeup.console import success

                commit_message = first_block.text.strip()  # type: ignore
                success(f"Generated Anthropic commit message: {commit_message[:50]}...")
                return commit_message
            else:
                logger.warning("Anthropic API returned non-text content")
                return None
        else:
            logger.warning("Anthropic API returned empty response")
            return None

    except ImportError:
        logger.info("Anthropic library not available")
        return AuthException("Anthropic library not installed", provider="anthropic")
    except KeyboardInterrupt:
        logger.info("_generate_ai_commit_message_anthropic interrupted by user")
        from codeup.git_utils import interrupt_main

        interrupt_main()
        raise
    except Exception as e:
        error_msg = str(e)
        # Check for authentication errors
        if "401" in error_msg or "authentication" in error_msg.lower():
            logger.warning(f"Anthropic authentication failed: {error_msg}")
            return AuthException(
                f"Invalid Anthropic API key: {error_msg}", provider="anthropic"
            )
        logger.error(f"Failed to generate Anthropic commit message: {e}")
        return None


def _generate_ai_commit_message() -> str | AuthException | Exception:
    """Generate commit message using OpenAI API with Anthropic fallback.

    Returns:
        str: Successfully generated commit message
        AuthException: Authentication failed for all providers (missing or invalid keys)
        Exception: Unexpected error occurred (with deep logging already performed)
    """
    openai_auth_error: AuthException | None = None
    anthropic_auth_error: AuthException | None = None

    try:
        # Import and use existing OpenAI config system
        from codeup.config import get_openai_api_key

        api_key = get_openai_api_key()

        # Get staged diff
        diff_text = get_git_diff_cached()

        if not diff_text:
            # No staged changes, get regular diff
            logger.info("No staged changes, getting regular diff")
            diff_text = get_git_diff()
            if not diff_text:
                logger.warning("No changes found in git diff")
                return AuthException(
                    "No changes found in git diff to generate commit message"
                )

        # Try OpenAI first if we have a key
        if api_key:
            try:
                # Set the API key for OpenAI
                os.environ["OPENAI_API_KEY"] = api_key

                # Force the correct OpenAI API endpoint
                os.environ["OPENAI_BASE_URL"] = "https://api.openai.com/v1"
                os.environ["OPENAI_API_BASE"] = "https://api.openai.com/v1"

                # Create OpenAI client
                client = openai.OpenAI(api_key=api_key)

                prompt = f"""You are an expert developer who writes clear, concise commit messages following conventional commit format.

Analyze the following git diff and generate a single line commit message that:
1. Follows conventional commit format (type(scope): description)
2. Uses one of these types: feat, fix, docs, style, refactor, perf, test, chore, ci, build
3. Is under 72 characters
4. Describes the main change concisely
5. Uses imperative mood (e.g., "add", not "added")

Git diff:
```
{diff_text}
```

Respond with only the commit message, nothing else."""

                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    temperature=0.3,
                )

                if response.choices and len(response.choices) > 0:
                    content = response.choices[0].message.content
                    commit_message = content.strip() if content else ""
                    logger.info(
                        f"Successfully generated OpenAI commit message: {commit_message[:50]}..."
                    )
                    return commit_message
                else:
                    logger.warning("OpenAI API returned empty response")

            except KeyboardInterrupt:
                logger.info("OpenAI API call interrupted by user")
                from codeup.git_utils import interrupt_main

                interrupt_main()
                raise
            except Exception as e:
                # Extract cleaner error message from OpenAI exceptions
                error_msg = str(e)
                is_auth_error = False

                if "Error code: 401" in error_msg or "Incorrect API key" in error_msg:
                    clean_msg = "Invalid OpenAI API key"
                    is_auth_error = True
                elif "Error code:" in error_msg and "message" in error_msg:
                    # Try to extract just the message part from OpenAI error
                    try:
                        import re

                        match = re.search(r"'message': '([^']*)'", error_msg)
                        if match:
                            clean_msg = match.group(1)
                        else:
                            clean_msg = (
                                error_msg.split(" - ")[0]
                                if " - " in error_msg
                                else str(e)
                            )
                    except Exception as parse_error:
                        logger.debug(
                            f"Failed to parse OpenAI error message: {parse_error}"
                        )
                        clean_msg = str(e)
                else:
                    clean_msg = str(e)

                from codeup.console import warning

                logger.warning(f"OpenAI commit message generation failed: {clean_msg}")
                warning(f"⚠ OpenAI generation failed: {clean_msg}")

                if is_auth_error:
                    openai_auth_error = AuthException(clean_msg, provider="openai")
        else:
            # No OpenAI key configured
            logger.info("No OpenAI API key found")
            openai_auth_error = AuthException(
                "No OpenAI API key configured", provider="openai"
            )

        # Fallback to Anthropic
        from codeup.console import info

        info("Trying Anthropic as fallback for commit message generation")
        anthropic_result = _generate_ai_commit_message_anthropic(diff_text)

        if isinstance(anthropic_result, str):
            # Success - return the commit message
            return anthropic_result
        elif isinstance(anthropic_result, AuthException):
            anthropic_auth_error = anthropic_result
            logger.info(f"Anthropic auth error: {anthropic_auth_error.message}")
        else:
            # None - other failure (network, etc.)
            logger.warning("Anthropic generation failed with non-auth error")

        # Both providers failed - determine if it's an auth issue
        if openai_auth_error and anthropic_auth_error:
            # Both providers have auth issues
            combined_msg = (
                f"No valid API keys configured. "
                f"OpenAI: {openai_auth_error.message}. "
                f"Anthropic: {anthropic_auth_error.message}."
            )
            logger.warning(f"All AI providers failed with auth errors: {combined_msg}")
            return AuthException(combined_msg)

        # At least one provider had a non-auth failure
        logger.warning("AI commit message generation failed (non-auth error)")
        return AuthException(
            "AI commit message generation failed. Check API keys and network connectivity."
        )

    except KeyboardInterrupt:
        logger.info("_generate_ai_commit_message interrupted by user")
        from codeup.git_utils import interrupt_main

        interrupt_main()
        raise
    except Exception as e:
        # Deep logging for unexpected exceptions
        import traceback

        logger.error("=" * 60)
        logger.error("UNEXPECTED ERROR in _generate_ai_commit_message")
        logger.error("=" * 60)
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception message: {e}")
        logger.error(f"Exception args: {e.args}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        logger.error("=" * 60)

        # Also log context information
        logger.error("Context at time of error:")
        logger.error(f"  - OpenAI auth error: {openai_auth_error}")
        logger.error(f"  - Anthropic auth error: {anthropic_auth_error}")
        logger.error("=" * 60)

        # Return the exception for the caller to handle
        return e


def _opencommit_or_prompt_for_commit_message(
    auto_accept: bool, no_interactive: bool = False
) -> None:
    """Generate AI commit message or prompt for manual input."""
    from codeup.console import error, info, success

    # Try to generate AI commit message first
    result = _generate_ai_commit_message()

    # Handle successful commit message generation
    if isinstance(result, str):
        success(f"Generated commit message: {result}")
        # Always auto-accept AI-generated messages when they succeed
        info("Auto-accepting AI-generated commit message")
        safe_git_commit(result)
        return

    # Handle AuthException - authentication/key configuration issue
    if isinstance(result, AuthException):
        auth_error = result
        logger.warning(
            f"AI commit generation failed with auth error: {auth_error.message}"
        )

        if no_interactive:
            # In non-interactive mode, fail immediately with clear instructions
            logger.error("AI commit generation failed in non-interactive mode")
            error(f"⚠ {auth_error.message}")
            error("⚠ Running in non-interactive mode (--no-interactive)")
            info(auth_error.get_fix_instructions())
            raise RuntimeError(
                f"Cannot generate commit message: {auth_error.message}. Use: codeup -m 'your commit message'"
            )

        # Check if terminal is a PTY before attempting manual input
        if not sys.stdin.isatty():
            logger.error(
                "AI commit generation failed and terminal is not a PTY - cannot get manual input"
            )
            error(f"⚠ {auth_error.message}")
            error(
                "⚠ Cannot prompt for manual input (not running in interactive terminal)"
            )
            info(auth_error.get_fix_instructions())
            raise RuntimeError(
                f"Cannot generate commit message: {auth_error.message}. Use: codeup -m 'your commit message'"
            )

        # PTY available - warn but allow manual input
        from codeup.console import warning

        warning(f"⚠ {auth_error.message}")
        info("Falling back to manual commit message input...")

    # Handle unexpected Exception - rare case with deep logging already done
    elif isinstance(result, Exception):
        unexpected_error = result
        logger.error(
            f"Unexpected error during AI commit generation: {unexpected_error}"
        )

        if no_interactive:
            error(
                f"⚠ Unexpected error: {type(unexpected_error).__name__}: {unexpected_error}"
            )
            error("⚠ Running in non-interactive mode (--no-interactive)")
            info("Check logs for detailed error information.")
            info("Provide a commit message manually: codeup -m 'your commit message'")
            raise RuntimeError(
                f"Cannot generate commit message due to unexpected error: {unexpected_error}. Use: codeup -m 'your commit message'"
            )

        if not sys.stdin.isatty():
            error(
                f"⚠ Unexpected error: {type(unexpected_error).__name__}: {unexpected_error}"
            )
            error(
                "⚠ Cannot prompt for manual input (not running in interactive terminal)"
            )
            info("Check logs for detailed error information.")
            info("Provide a commit message manually: codeup -m 'your commit message'")
            raise RuntimeError(
                f"Cannot generate commit message due to unexpected error: {unexpected_error}. Use: codeup -m 'your commit message'"
            )

        # PTY available - warn but allow manual input
        from codeup.console import warning

        warning(
            f"⚠ Unexpected error: {type(unexpected_error).__name__}: {unexpected_error}"
        )
        info("Check logs for detailed error information.")
        info("Falling back to manual commit message input...")

    # Fall back to manual commit message (interactive terminal available)
    try:

        def input_with_timeout(prompt: str, timeout_seconds: int = 300) -> str:
            """
            Get user input with a timeout. Raises InputTimeoutError if timeout is reached.
            """
            # Check if we're in a non-interactive environment first
            if not sys.stdin.isatty():
                raise EOFError("No interactive terminal available")

            result = []
            exception_holder = []

            def get_input():
                try:
                    result.append(input(prompt))
                except KeyboardInterrupt:
                    from codeup.git_utils import interrupt_main

                    interrupt_main()
                    raise
                except Exception as e:
                    exception_holder.append(e)

            # Start input thread
            input_thread = threading.Thread(target=get_input, daemon=True)
            input_thread.start()

            # Wait for either input or timeout
            input_thread.join(timeout=timeout_seconds)

            if input_thread.is_alive():
                # Timeout occurred
                logger.warning(f"Input timed out after {timeout_seconds} seconds")
                raise InputTimeoutError(
                    f"Input timed out after {timeout_seconds} seconds"
                )

            # Check if an exception occurred in the input thread
            if exception_holder:
                raise exception_holder[0]

            # Return the input if successful
            if result:
                return result[0]
            else:
                raise InputTimeoutError("No input received")

        msg = input_with_timeout("Commit message: ", timeout_seconds=300)
        safe_git_commit(msg)
    except (EOFError, InputTimeoutError) as e:
        from codeup.console import info, warning

        logger.warning(f"Manual commit message input failed: {e}")
        warning(f"Commit message input failed or timed out ({type(e).__name__})")
        info("Using generic commit message as fallback...")
        safe_git_commit("chore: automated commit (input failed)")
        return


def ai_commit_or_prompt_for_commit_message(
    no_autoaccept: bool, message: str | None = None, no_interactive: bool = False
) -> None:
    """Generate commit message using AI or prompt for manual input."""
    if message:
        # Use provided commit message directly
        safe_git_commit(message)
    else:
        # Use AI or interactive commit
        _opencommit_or_prompt_for_commit_message(
            auto_accept=not no_autoaccept, no_interactive=no_interactive
        )
