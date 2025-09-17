"""AI-powered commit message generation for codeup."""

import _thread
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
                commit_message = first_block.text.strip()  # type: ignore
                logger.info(
                    f"Generated Anthropic commit message: {commit_message[:50]}..."
                )
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
        _thread.interrupt_main()
        return None
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
        logger.info("Getting git diff for commit message generation")
        diff_text = get_git_diff_cached()

        if not diff_text:
            # No staged changes, get regular diff
            logger.info("No staged changes, getting regular diff")
            diff_text = get_git_diff()
            if not diff_text:
                logger.warning("No changes found in git diff")
                return None

        logger.info(f"Got diff, length: {len(diff_text)}")

        # Try OpenAI first if we have a key
        if api_key:
            try:
                # Set the API key for OpenAI
                os.environ["OPENAI_API_KEY"] = api_key

                # Force the correct OpenAI API endpoint
                os.environ["OPENAI_BASE_URL"] = "https://api.openai.com/v1"
                os.environ["OPENAI_API_BASE"] = "https://api.openai.com/v1"

                logger.info(f"Using OpenAI API key, length: {len(api_key)}")
                logger.info("Set OpenAI base URL to: https://api.openai.com/v1")

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
                _thread.interrupt_main()
                return None
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
                    except Exception:
                        clean_msg = str(e)
                else:
                    clean_msg = str(e)

                logger.warning(f"OpenAI commit message generation failed: {clean_msg}")
                print(f"OpenAI generation failed: {clean_msg}")

        # Fallback to Anthropic only if we have a key
        from codeup.config import get_anthropic_api_key

        if get_anthropic_api_key():
            logger.info("Trying Anthropic as fallback for commit message generation")
            anthropic_message = _generate_ai_commit_message_anthropic(diff_text)
            if anthropic_message:
                return anthropic_message
        else:
            logger.info("No Anthropic API key found, skipping Anthropic fallback")

        # If both failed
        logger.warning("AI commit message generation failed")
        print("Warning: AI commit message generation failed")
        print("Solutions:")
        print("  - Set OpenAI API key: export OPENAI_API_KEY=your_key")
        print("  - Set Anthropic API key: export ANTHROPIC_API_KEY=your_key")
        print(
            "  - Set keys via config: python -c \"from codeup.config import save_config; save_config({'openai_key': 'your_openai_key', 'anthropic_key': 'your_anthropic_key'})\""
        )
        return None

    except KeyboardInterrupt:
        logger.info("_generate_ai_commit_message interrupted by user")
        _thread.interrupt_main()
        return None
    except Exception as e:
        logger.error(f"Failed to generate AI commit message: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception args: {e.args}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")

        error_msg = str(e)
        print("Error: AI commit message generation failed")
        print(f"Exception: {type(e).__name__}: {error_msg}")
        print("Full traceback:")
        print(traceback.format_exc())

        return None


def _opencommit_or_prompt_for_commit_message(
    auto_accept: bool, no_interactive: bool = False
) -> None:
    """Generate AI commit message or prompt for manual input."""
    # Try to generate AI commit message first
    ai_message = _generate_ai_commit_message()

    if ai_message:
        print(f"Generated commit message: {ai_message}")
        # Always auto-accept AI-generated messages when they succeed
        print("Auto-accepting AI-generated commit message")
        safe_git_commit(ai_message)
        return
    elif no_interactive:
        # In non-interactive mode, fail if AI commit generation fails
        logger.error("AI commit generation failed in non-interactive mode")
        print("Error: Failed to generate AI commit message in non-interactive mode")
        print("This may be due to:")
        print("  - OpenAI API issues or rate limiting")
        print("  - Missing or invalid OpenAI API key")
        print("  - Network connectivity problems")
        print("Solutions:")
        print("  - Run in interactive mode: codeup (without --no-interactive)")
        print("  - Set API key via environment: export OPENAI_API_KEY=your_key")
        print("  - Set API key via imgai: imgai --set-key YOUR_KEY")
        print("  - Set API key via Python config:")
        print(
            "    python -c \"from codeup.config import save_config; save_config({'openai_key': 'your_key'})\""
        )
        raise RuntimeError(
            "AI commit message generation failed in non-interactive terminal"
        )

    # Fall back to manual commit message
    if no_interactive:
        logger.warning(
            "Cannot get manual commit message input in non-interactive mode, using fallback"
        )
        print("Cannot get commit message input in non-interactive mode")
        print("Using generic commit message as fallback...")
        safe_git_commit("chore: automated commit (AI unavailable)")
        return

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
                    import _thread

                    _thread.interrupt_main()
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
        logger.warning(f"Manual commit message input failed: {e}")
        print(f"Commit message input failed or timed out ({type(e).__name__})")
        print("Using generic commit message as fallback...")
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
