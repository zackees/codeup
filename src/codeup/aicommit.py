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


def _generate_ai_commit_message_anthropic(diff_text: str) -> str | None:
    """Generate commit message using Anthropic Claude API as fallback."""
    try:
        import anthropic

        from codeup.config import get_anthropic_api_key

        api_key = get_anthropic_api_key()
        if not api_key:
            logger.info("No Anthropic API key found")
            return None

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
        return None
    except KeyboardInterrupt:
        logger.info("_generate_ai_commit_message_anthropic interrupted by user")
        from codeup.git_utils import interrupt_main

        interrupt_main()
        raise
    except Exception as e:
        logger.error(f"Failed to generate Anthropic commit message: {e}")
        return None


def _generate_ai_commit_message() -> str | None:
    """Generate commit message using OpenAI API with Anthropic fallback."""
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
                return None

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
                if "Error code: 401" in error_msg and "Incorrect API key" in error_msg:
                    clean_msg = "Invalid OpenAI API key"
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

        # Fallback to Anthropic only if we have a key
        from codeup.config import get_anthropic_api_key
        from codeup.console import info

        if get_anthropic_api_key():
            info("Trying Anthropic as fallback for commit message generation")
            anthropic_message = _generate_ai_commit_message_anthropic(diff_text)
            if anthropic_message:
                return anthropic_message
        else:
            info("No Anthropic API key found, skipping Anthropic fallback")

        # If both failed
        from codeup.console import info, warning

        logger.warning("AI commit message generation failed")
        warning("⚠ AI commit message generation failed")
        info("Solutions:")
        info("  - Set OpenAI API key: export OPENAI_API_KEY=your_key")
        info("  - Set Anthropic API key: export ANTHROPIC_API_KEY=your_key")
        info(
            "  - Set keys via config: python -c \"from codeup.config import save_config; save_config({'openai_key': 'your_openai_key', 'anthropic_key': 'your_anthropic_key'})\""
        )
        return None

    except KeyboardInterrupt:
        logger.info("_generate_ai_commit_message interrupted by user")
        from codeup.git_utils import interrupt_main

        interrupt_main()
        raise
    except Exception as e:
        from codeup.console import error

        logger.error(f"Failed to generate AI commit message: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception args: {e.args}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")

        error_msg = str(e)
        error("⚠ AI commit message generation failed")
        error(f"Exception: {type(e).__name__}: {error_msg}")
        error("Full traceback:")
        error(traceback.format_exc())

        return None


def _opencommit_or_prompt_for_commit_message(
    auto_accept: bool, no_interactive: bool = False
) -> None:
    """Generate AI commit message or prompt for manual input."""
    from codeup.console import info, success

    # Try to generate AI commit message first
    ai_message = _generate_ai_commit_message()

    if ai_message:
        success(f"Generated commit message: {ai_message}")
        # Always auto-accept AI-generated messages when they succeed
        info("Auto-accepting AI-generated commit message")
        safe_git_commit(ai_message)
        return
    elif no_interactive:
        from codeup.console import error, info

        # In non-interactive mode, fail if AI commit generation fails
        logger.error("AI commit generation failed in non-interactive mode")
        error("⚠ Failed to generate AI commit message in non-interactive mode")
        info("This may be due to:")
        info("  - OpenAI API issues or rate limiting")
        info("  - Missing or invalid OpenAI API key")
        info("  - Network connectivity problems")
        info("Solutions:")
        info("  - Run in interactive mode: codeup (without --no-interactive)")
        info("  - Set API key via environment: export OPENAI_API_KEY=your_key")
        info("  - Set API key via imgai: imgai --set-key YOUR_KEY")
        info("  - Set API key via Python config:")
        info(
            "    python -c \"from codeup.config import save_config; save_config({'openai_key': 'your_key'})\""
        )
        raise RuntimeError(
            "AI commit message generation failed in non-interactive terminal"
        )

    # Check if terminal is a PTY before attempting manual input
    # If both AI providers failed and we're not in a PTY, exit with error
    if not sys.stdin.isatty():
        from codeup.console import error, info

        logger.error(
            "AI commit generation failed and terminal is not a PTY - cannot get manual input"
        )
        error("⚠ AI commit message generation failed")
        error("⚠ Cannot prompt for manual input (terminal is not interactive)")
        info("Both OpenAI and Anthropic API calls failed.")
        info("Please provide a commit message manually:")
        info("  git commit -m 'your commit message'")
        raise RuntimeError(
            "AI commit message generation failed in non-interactive terminal"
        )

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
