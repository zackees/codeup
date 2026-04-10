"""AI-powered commit message generation for codeup."""

import logging
import os
import re

import openai

from codeup.git_utils import get_git_diff, get_git_diff_cached, safe_git_commit

logger = logging.getLogger(__name__)

CommitProvider = str | None


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


def _strip_emojis(text: str) -> str:
    """Remove emoji characters from text."""
    import re

    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map symbols
        "\U0001f1e0-\U0001f1ff"  # flags
        "\U00002702-\U000027b0"  # dingbats
        "\U000024c2-\U0001f251"  # enclosed characters
        "\U0001f926-\U0001f937"  # supplemental
        "\U00010000-\U0010ffff"  # supplemental symbols
        "\u2640-\u2642"
        "\u2600-\u2b55"
        "\u200d"
        "\u23cf"
        "\u23e9"
        "\u231a"
        "\ufe0f"
        "\u3030"
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub("", text).strip()


def _clean_clud_output(raw_output: str) -> str | None:
    """Clean clud output by removing metadata, emojis, and code fences.

    clud output typically looks like:
        💬 feat(scope): description
        📊 tokens: 4
    or sometimes wraps in code fences:
        💬 ```
        feat(scope): description
        ```
        📊 tokens: 4

    Returns:
        str: Cleaned commit message, or None if nothing useful remains.
    """
    # Remove clud metadata lines (📊 tokens: N)
    lines = [
        line
        for line in raw_output.split("\n")
        if not line.strip().startswith("\U0001f4ca")  # 📊
    ]
    text = "\n".join(lines).strip()

    # Strip emojis (e.g. 💬 prefix)
    text = _strip_emojis(text)
    if not text:
        logger.warning("clud output was only emojis or metadata")
        return None

    # Remove markdown code fences
    text = text.replace("```", "").strip()
    if not text:
        logger.warning("clud output was only code fences")
        return None

    cleaned_lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not cleaned_lines:
        logger.warning("clud output had no usable content")
        return None

    conventional_pattern = re.compile(
        r"^(feat|fix|docs|style|refactor|perf|test|chore|ci|build)(\([^)]*\))?:\s+\S"
    )
    for line in cleaned_lines:
        if conventional_pattern.match(line):
            return line

    status_prefixes = (
        "reading additional input from stdin",
        "reading from stdin",
        "processing stdin",
    )
    for line in cleaned_lines:
        if line.lower().startswith(status_prefixes):
            continue
        return line

    logger.warning("clud output had no usable content")
    return None


def _generate_cli_commit_message(
    diff_text: str, backend: str | None = None
) -> str | None:
    """Generate commit message using the configured CLI backend.

    Returns:
        str: Successfully generated commit message
        None: CLI backend not available or generation failed
    """
    import shutil

    if not shutil.which("clud"):
        logger.info("clud not found in PATH")
        return None

    try:
        import subprocess

        from codeup.console import info, success

        if backend:
            info(f"Trying {backend} CLI backend for commit message generation")
        else:
            info(
                "Trying CLI backend as last-resort fallback for commit message generation"
            )

        prompt = (
            "Write a conventional commit message (type(scope): description) for "
            "the git diff provided on stdin. Use types: feat, fix, docs, style, "
            "refactor, perf, test, chore, ci, build. Under 72 chars. Imperative "
            "mood. No emojis. Only the message, nothing else."
        )

        cmd = ["clud"]
        if backend:
            cmd.extend(["--session-model", backend])
        cmd.extend(["-p", prompt])

        result = subprocess.run(
            cmd,
            input=diff_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )

        if result.returncode != 0:
            logger.warning(
                f"CLI backend exited with code {result.returncode}: {result.stderr}"
            )
            return None

        commit_message = result.stdout.strip()
        if not commit_message:
            logger.warning("CLI backend returned empty output")
            return None

        commit_message = _clean_clud_output(commit_message)
        if not commit_message:
            return None

        source = backend if backend else "cli"
        success(f"Generated {source} commit message: {commit_message[:50]}...")
        return commit_message

    except KeyboardInterrupt:
        logger.info("_generate_cli_commit_message interrupted by user")
        from codeup.git_utils import interrupt_main

        interrupt_main()
        raise
    except subprocess.TimeoutExpired:
        logger.warning("CLI backend timed out after 120 seconds")
        return None
    except Exception as e:
        logger.error(f"Failed to generate CLI commit message: {e}")
        return None


def _generate_ai_commit_message_clud(diff_text: str) -> str | None:
    """Backward-compatible wrapper for the default CLI fallback."""
    return _generate_cli_commit_message(diff_text)


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


def _get_commit_diff_text() -> str | AuthException:
    """Get the staged diff, falling back to the working-tree diff."""
    diff_text = get_git_diff_cached()

    if not diff_text:
        logger.info("No staged changes, getting regular diff")
        diff_text = get_git_diff()
        if not diff_text:
            logger.warning("No changes found in git diff")
            return AuthException(
                "No changes found in git diff to generate commit message"
            )

    return diff_text


def _generate_ai_commit_message(
    provider: CommitProvider = None,
) -> str | AuthException | Exception:
    """Generate commit message using OpenAI API with Anthropic fallback.

    Returns:
        str: Successfully generated commit message
        AuthException: Authentication failed for all providers (missing or invalid keys)
        Exception: Unexpected error occurred (with deep logging already performed)
    """
    openai_auth_error: AuthException | None = None
    anthropic_auth_error: AuthException | None = None

    try:
        diff_result = _get_commit_diff_text()
        if isinstance(diff_result, AuthException):
            return diff_result
        diff_text = diff_result

        if provider in ("codex", "claude"):
            cli_result = _generate_cli_commit_message(diff_text, backend=provider)
            if isinstance(cli_result, str):
                return cli_result
            return AuthException(
                f"{provider.capitalize()} CLI commit message generation failed. "
                f"Check that 'clud' is installed and the {provider} backend is available."
            )

        # Import and use existing OpenAI config system
        from codeup.config import get_openai_api_key

        api_key = get_openai_api_key()

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
                    try:  # noqa
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

        # Both API providers failed - try clud as last-resort fallback
        clud_result = _generate_ai_commit_message_clud(diff_text)
        if isinstance(clud_result, str):
            return clud_result

        # All providers failed - determine if it's an auth issue
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
    auto_accept: bool,
    no_interactive: bool = False,
    provider: CommitProvider = None,
) -> None:
    """Generate AI commit message or prompt for manual input."""
    from codeup.console import error, info, success

    # Try to generate AI commit message first
    result = _generate_ai_commit_message(provider=provider)

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

        if provider in ("codex", "claude"):
            error(f"⚠ {auth_error.message}")
            raise RuntimeError(
                f"Forced CLI provider '{provider}' failed: {auth_error.message}"
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

        from codeup.console import warning

        warning(
            f"⚠ Unexpected error: {type(unexpected_error).__name__}: {unexpected_error}"
        )
        info("Check logs for detailed error information.")
        info("Falling back to manual commit message input...")

    # Fall back to manual commit message (interactive terminal available)
    try:
        from codeup.utils import input_with_timeout

        msg = input_with_timeout("Commit message: ")
        safe_git_commit(msg)
    except KeyboardInterrupt:
        from codeup.git_utils import interrupt_main

        interrupt_main()
        raise
    except Exception as e:
        from codeup.utils import InputTimeoutError, exit_for_missing_user_input

        if isinstance(e, (EOFError, InputTimeoutError)):
            logger.warning(f"Manual commit message input failed: {e}")
            exit_for_missing_user_input()
        raise


def ai_commit_or_prompt_for_commit_message(
    no_autoaccept: bool,
    message: str | None = None,
    no_interactive: bool = False,
    provider: CommitProvider = None,
) -> None:
    """Generate commit message using AI or prompt for manual input."""
    if message:
        # Use provided commit message directly
        safe_git_commit(message)
    else:
        # Use AI or interactive commit
        _opencommit_or_prompt_for_commit_message(
            auto_accept=not no_autoaccept,
            no_interactive=no_interactive,
            provider=provider,
        )
