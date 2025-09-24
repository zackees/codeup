# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CodeUp is an intelligent git workflow automation tool that streamlines development with AI-powered commit messages. It's a Python CLI tool that automates the entire git workflow: status checks, linting, testing, staging, AI commit generation, and safe pushing with rebase handling.

### Architecture

- **Main Entry Point**: `src/codeup/main.py` - Core workflow orchestration
- **Configuration**: `src/codeup/config.py` - API key management (OpenAI/Anthropic) with keyring/config file fallbacks
- **CLI Interface**: `src/codeup/cli.py` - Command-line argument parsing (currently minimal)
- **Package Structure**: Uses `src/` layout with `setuptools` and `pyproject.toml`

### Key Components

1. **Git Operations**: Comprehensive git status checking, safe rebasing, conflict handling, and smart pushing
2. **AI Integration**: Dual AI provider support (OpenAI GPT-3.5-turbo primary, Anthropic Claude fallback)
3. **Development Tools Integration**: Automatic detection and execution of `./lint` and `./test` scripts
4. **UV Project Support**: Special handling for UV-managed Python projects with dependency resolution
5. **Cross-platform Support**: Handles Windows UTF-8 encoding issues and bash script execution

## Development Commands

### Core Commands
- **Testing**: `./test` - Runs pytest with parallel execution (`pytest -n auto`)
- **Linting**: `./lint` - Runs ruff check/format, black, and pyright type checking
- **Cleaning**: `./clean` - Removes build artifacts, caches, and temporary files
- **Installation**: `./install` - Development installation script
- **Publishing**: `./upload_package.sh` - Package publishing (triggered by `codeup --publish`)

### UV Project Requirements
**CRITICAL**: This project uses UV for Python environment and dependency management.

- **NEVER use `python` directly** - Always use `uv run python` or `uv run <command>`
- **Testing**: Use `uv run pytest` not `python -m pytest`
- **Script execution**: Use `uv run python script.py` not `python script.py`

### Testing
```bash
# Run all tests
./test

# Run specific test file
uv run pytest tests/test_codeup.py -v

# Run with coverage
uv run pytest --cov=src/codeup tests/
```

### Linting and Type Checking
```bash
# Full linting pipeline
./lint

# Individual tools
uv run ruff check --fix src tests
uv run black src tests
uv run pyright src tests
```

### Development Setup
```bash
# Install in development mode
pip install -e .

# Or using UV
uv pip install -e .
```

## Configuration Management

The project uses a multi-tier configuration system for API keys:
1. Config file (`~/.config/zcmds/openai.json` or equivalent)
2. System keyring (secure storage)
3. Environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`)

## Exception Handling Rules

1. **KeyboardInterrupt Priority**: When handling exceptions, KeyboardInterrupt must always be handled first before any general exception handlers.
   - Use specific `except KeyboardInterrupt:` blocks before `except Exception:`
   - In KeyboardInterrupt handlers, call `interrupt_main()` utility function and then `raise`

2. **General Exception Logging**: ALL general exception handlers MUST log the error before handling it.
   - Use `logger.error()`, `logger.warning()`, or appropriate logging level
   - Include context about what operation failed
   - **NEVER catch a general exception without logging it**
   - **NEVER use `pass` in exception handlers without logging**

3. **Exception Handler Ordering**: KeyboardInterrupt must always be handled before general Exception handlers.
   - This prevents KeyboardInterrupt from being caught by generic Exception handlers
   - Always use the pattern: KeyboardInterrupt first, then specific exceptions, then general Exception

### Examples

```python
# Good - KeyboardInterrupt handled first, general exceptions logged
try:
    risky_operation()
except KeyboardInterrupt:
    logger.info("Operation interrupted by user")
    interrupt_main()
    raise
except SpecificError as e:
    logger.warning(f"Specific error in operation: {e}")
    handle_specific_error(e)
except Exception as e:
    logger.error(f"Unexpected error in operation: {e}")
    handle_gracefully()

# Bad - KeyboardInterrupt caught by general Exception handler
try:
    risky_operation()
except Exception as e:  # This will catch KeyboardInterrupt too!
    logger.error(f"Operation failed: {e}")

# Bad - Exception caught without logging
try:
    risky_operation()
except Exception:
    pass  # NEVER do this - must log the exception

# Bad - Exception logged but execution continues unexpectedly
try:
    cleanup_operation()
except Exception:
    pass  # Even cleanup operations must log errors
```

## Testing Structure

Tests are organized by functionality:
- `test_codeup.py` - Core workflow testing
- `test_config.py` - Configuration and API key management
- `test_git_operations.py` - Git command testing
- `test_argument_parsing.py` - CLI argument validation
- `test_utilities.py` - Helper function testing

Test markers:
- `@pytest.mark.unit` - Fast unit tests
- `@pytest.mark.integration` - Slower integration tests
- `@pytest.mark.ai` - Tests requiring AI API access

## Code Quality Tools

- **Ruff**: Primary linter and formatter (replaces flake8, isort)
- **Black**: Code formatting (88 character line length)
- **Pyright**: Type checking (basic mode, Python 3.8+ compatibility)
- **Pytest**: Testing framework with xdist for parallel execution

## Data Structure Rules

### No Tuples Rule
**NEVER use tuples for return values or data structures.** Always use `@dataclass` instead.

**Rationale**: Tuples are positional and error-prone. Dataclasses provide named fields, type safety, and better maintainability.

```python
# Bad - Tuple return
def parse_data(text: str) -> Tuple[str, List[str]]:
    return ("program", ["arg1", "arg2"])

# Good - Dataclass return
@dataclass(frozen=True)
class ParseResult:
    program: str
    args: List[str]

def parse_data(text: str) -> ParseResult:
    return ParseResult(program="program", args=["arg1", "arg2"])
```

**Exceptions**: Only use tuples for:
- Unpacking in function parameters: `*args`
- Dictionary items iteration: `dict.items()`
- Built-in functions that require tuples: `isinstance(obj, (str, int))`

### Standalone Test Execution Rule
**ALL unit test files MUST include a `if __name__ == "__main__":` section for standalone execution.**

**Test Structure Requirements**:
- Use `unittest.TestCase` classes for all test definitions
- Use `unittest.main()` for standalone execution
- Project uses pytest as the test runner for full test suite
- Individual files run with unittest for standalone debugging

**Rationale**: Enables running individual test files directly for faster development and debugging without running the entire test suite.

```python
# Required pattern for all test files
import unittest

class TestMyFeature(unittest.TestCase):
    def setUp(self):
        # Setup code here
        pass

    def test_something(self):
        self.assertEqual(actual, expected)

if __name__ == "__main__":
    unittest.main()
```

**Import Rules for Tests**:
- **NEVER import `src.*` modules directly** - This indicates incorrect execution method
- **NEVER use `sys.path.insert()` or `sys.path.append()`** - This indicates incorrect execution method
- Use proper UV environment: `uv run pytest` handles import paths correctly
- If seeing import errors or path manipulation, you're using `python` instead of `uv run`

**Benefits**:
- Fast iteration during development
- Easy debugging of specific test modules
- Consistent execution pattern across all tests
- Works with both unittest and pytest runners
- No import path issues when using UV correctly