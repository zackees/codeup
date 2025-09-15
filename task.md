# CodeUp Migration Task

## NEW TASK:

git push to this origin with an empty repo: https://github.com/zackees/codeup.git

## Overview
This document outlines the migration of the `codeup` tool from the zcmds package to this standalone repository.

## Source Location
- **Source Repository**: `~/dev/zcmds` (locally located at `C:\Users\niteris\dev\zcmds`)
- **Main Module**: `src/zcmds/cmds/common/codeup.py` (1,313 lines)
- **Supporting Module**: `src/zcmds/cmds/common/openaicfg.py` (230 lines)
- **Unit Tests**:
  - `tests/test_codeup.py` (113 lines)
  - `tests/test_codeup_aicommit.py` (282 lines)

## Tool Description
CodeUp is an intelligent git workflow automation tool that:

1. **Checks git status** for changes
2. **Runs linting** (if `./lint` script exists)
3. **Runs tests** (if `./test` script exists)
4. **Stages all changes** with `git add .`
5. **Generates AI commit messages** using OpenAI or Anthropic APIs
6. **Commits changes** with generated or manual messages
7. **Pushes to remote** with automatic rebase handling

## Key Features
- **AI-powered commit messages** using OpenAI GPT or Anthropic Claude
- **Conventional commit format** (feat:, fix:, docs:, etc.)
- **Cross-platform support** (Windows/Unix)
- **Interactive and non-interactive modes**
- **Safe rebase handling** with conflict detection
- **UV project detection** and dependency management
- **Comprehensive error handling** and logging
- **API key management** via keyring or config files

## Dependencies
Based on analysis of the source code:

### Core Dependencies
- `openai` - OpenAI API integration
- `anthropic` - Anthropic Claude API integration
- `appdirs` - Cross-platform config directory support
- `ai-commit-msg` - Git AI commit message generation
- `keyring` - Secure API key storage (optional)

### Standard Library Usage
- `subprocess` - Git command execution
- `argparse` - Command-line argument parsing
- `logging` - Comprehensive logging system
- `pathlib` - Path manipulation
- `tempfile` - Testing infrastructure
- `threading` - Interrupt handling

## Migration Tasks

### Phase 1: Core Migration
1. **Copy main module** - Migrate `codeup.py` as the primary module
2. **Copy configuration module** - Migrate `openaicfg.py` for API key management
3. **Update imports** - Change from `zcmds.cmds.common.openaicfg` to local imports
4. **Create entry point** - Set up console script or CLI entry point

### Phase 2: Testing Infrastructure
1. **Migrate unit tests** - Copy both test files with path updates
2. **Update test imports** - Modify imports to reference new module structure
3. **Verify test coverage** - Ensure all functionality is properly tested
4. **Add integration tests** - Test end-to-end workflows

### Phase 3: Packaging & Distribution
1. **Create pyproject.toml** - Modern Python packaging configuration
2. **Set up dependencies** - Define all required packages
3. **Configure entry points** - CLI command registration
4. **Add development tools** - Linting, testing, formatting scripts

### Phase 4: Documentation & Cleanup
1. **Create README.md** - Installation and usage instructions
2. **Add examples** - Common usage patterns and workflows
3. **Document configuration** - API key setup and options
4. **Clean up code** - Remove zcmds-specific references

## File Structure (Proposed)
```
codeup/
├── src/
│   └── codeup/
│       ├── __init__.py
│       ├── main.py          # Main codeup functionality
│       └── config.py        # API key configuration (from openaicfg.py)
├── tests/
│   ├── test_codeup.py       # Core functionality tests
│   └── test_aicommit.py     # AI commit message tests
├── pyproject.toml           # Project configuration
├── README.md               # Documentation
└── task.md                 # This migration document
```

## Critical Considerations

### Import Updates Needed
- Change `from zcmds.cmds.common.openaicfg import ...` to local imports
- Update all internal module references
- Ensure proper Python package structure

### Configuration Compatibility
- Maintain compatibility with existing `~/.config/zcmds/openai.json` config files
- Support existing keyring entries under "zcmds" service name
- Preserve API key retrieval priority order

### Testing Considerations
- Tests currently mock `zcmds.cmds.common.openaicfg` functions
- Need to update mock paths for new module structure
- Verify UV project detection works in new environment
- Test cross-platform functionality (Windows/Unix)

### Feature Preservation
- Maintain all command-line arguments and options
- Preserve UV project detection and handling
- Keep AI fallback logic (OpenAI → Anthropic → manual)
- Ensure safe rebase and push logic remains intact

## Success Criteria
1. ✅ All source code successfully migrated
2. ✅ All unit tests pass with updated imports
3. ✅ Command-line interface works identically to original
4. ✅ AI commit message generation functions properly
5. ✅ Configuration and API key management preserved
6. ✅ Cross-platform compatibility maintained
7. ✅ Package can be installed via pip

## Notes
- The original tool is well-tested with comprehensive unit tests
- Code quality is high with proper error handling and logging
- The tool has mature features like timeout handling and interrupt management
- Existing configuration and keyring integration should be preserved for user compatibility