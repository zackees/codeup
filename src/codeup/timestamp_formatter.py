"""Timestamp output formatter for RunningProcess."""

import time


class TimestampOutputFormatter:
    """Output formatter that prepends elapsed time in seconds to each line.

    Format: "0.01 (rest of stdout line)" with 2 decimal places.
    """

    def __init__(self) -> None:
        self._start_time: float | None = None

    def begin(self) -> None:
        """Record the start time when output begins."""
        self._start_time = time.time()

    def transform(self, line: str) -> str:
        """Transform output line by prepending elapsed time.

        Args:
            line: The output line to transform

        Returns:
            Line with timestamp prepended in format "0.01 (original line)"
        """
        if self._start_time is None:
            # Fallback if begin() wasn't called
            self._start_time = time.time()

        elapsed = time.time() - self._start_time
        return f"{elapsed:.2f} {line}"

    def end(self) -> None:
        """Reset state when output ends."""
        self._start_time = None
