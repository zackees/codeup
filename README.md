# CodeUp - Intelligent Git Workflow Automation



[![Linting](../../actions/workflows/lint.yml/badge.svg)](../../actions/workflows/lint.yml)
[![MacOS_Tests](../../actions/workflows/push_macos.yml/badge.svg)](../../actions/workflows/push_macos.yml)
[![Ubuntu_Tests](../../actions/workflows/push_ubuntu.yml/badge.svg)](../../actions/workflows/push_ubuntu.yml)
[![Win_Tests](../../actions/workflows/push_win.yml/badge.svg)](../../actions/workflows/push_win.yml)

**An intelligent git workflow automation tool that streamlines your development process with AI-powered commit messages and automated testing.**

![here-title](https://github.com/user-attachments/assets/c661d973-3f44-4a70-b3ae-cb75bbf09285)

## What is CodeUp?

CodeUp automates your entire git workflow in a single command:
- ✅ **Git Status Check** - Verifies changes exist before proceeding
- 🧹 **Automatic Linting** - Runs your `./lint` script if present
- 🧪 **Automatic Testing** - Runs your `./test` script if present
- 📝 **AI-Powered Commits** - Generates contextual commit messages using OpenAI or Anthropic
- 🔄 **Smart Rebasing** - Handles conflicts and keeps your branch up-to-date
- 🚀 **Safe Pushing** - Pushes to remote with conflict detection

## Quick Start

### Installation

```bash
pip install codeup
```

### Basic Usage

```bash
# Navigate to your git repository
cd your-project

# Run the complete workflow
codeup

# That's it! CodeUp will:
# 1. Check git status
# 2. Run linting (if ./lint exists)
# 3. Run tests (if ./test exists)
# 4. Stage all changes
# 5. Generate an AI commit message
# 6. Commit and push to remote
```

### AI-Powered Commit Messages

CodeUp analyzes your git diff and generates meaningful commit messages following conventional commit format:

```bash
# Example generated messages:
feat(auth): add OAuth2 authentication system
fix(api): resolve null pointer exception in user endpoint
docs(readme): update installation instructions
```

## Configuration

### Setting Up API Keys

CodeUp supports both OpenAI and Anthropic for commit message generation:

```bash
# Set OpenAI API key (recommended)
codeup --set-key-openai sk-your-openai-key-here

# Or set Anthropic API key
codeup --set-key-anthropic sk-ant-your-anthropic-key-here

# Alternative: use environment variables
export OPENAI_API_KEY="sk-your-key-here"
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

Keys are securely stored in your system keyring.

## Command Line Options

```bash
# Skip AI and provide manual commit message
codeup -m "fix: resolve login bug"

# Skip linting and testing, just commit
codeup --just-ai-commit

# Non-interactive mode (perfect for CI/CD)
codeup --no-interactive

# Skip pushing to remote
codeup --no-push

# Skip automatic rebasing
codeup --no-rebase

# Disable auto-accept of AI commit messages
codeup --no-autoaccept

# Skip testing
codeup --no-test

# Skip linting
codeup --no-lint

# Verbose output
codeup --verbose

# Enable detailed logging
codeup --log
```

## Features

### 🤖 Dual AI Provider Support
- **OpenAI GPT-3.5-turbo**: Fast and reliable
- **Anthropic Claude**: Automatic fallback if OpenAI fails
- Analyzes git diffs to generate contextual commit messages

### 🔧 Development Tool Integration
- Automatically detects and runs `./lint` scripts
- Automatically detects and runs `./test` scripts
- Supports UV project dependency resolution
- Cross-platform support (Windows, macOS, Linux)

### 🛡️ Smart Git Operations
- Safe rebase handling with conflict detection
- Automatic staging of changes and untracked files
- Interactive prompts for untracked files (when not in `--no-interactive` mode)
- Push conflict resolution with automatic retries

### 🔐 Secure Credential Management
- System keyring integration for API key storage
- Multiple configuration sources (keyring → config file → environment)
- No credentials stored in plaintext

## Requirements

- Python 3.8.1 or higher
- Git repository
- OpenAI or Anthropic API key (for AI commit messages)

## Development

To contribute to CodeUp:

```bash
# Clone the repository
git clone https://github.com/zackees/codeup.git
cd codeup

# Install in development mode
pip install -e .

# Run tests
./test

# Run linting
./lint
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Author

Created by [Zach Vorhies](https://github.com/zackees) - zach@zachvorhies.com
