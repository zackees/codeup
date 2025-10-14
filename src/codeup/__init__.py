"""CodeUp - Intelligent git workflow automation tool."""

__version__ = "1.0.19"

from .api import LintTestResult, lint_test
from .main import main

__all__ = ["main", "LintTestResult", "lint_test"]
