"""HTTP-related logging filters.

This module is intentionally small and import-safe.
"""

from __future__ import annotations

import logging


class HttpRequestLogDowngradeFilter(logging.Filter):
    """Downgrade noisy third-party HTTP INFO logs to DEBUG.

    Why:
        Libraries like httpx/httpcore/openai can emit INFO logs that overwhelm
        application logs in non-debug environments.

    Semantics:
        - If a record is INFO and matches one of the configured logger prefixes,
          we rewrite it to DEBUG.
        - We never drop records; we only adjust severity.
    """

    def __init__(self, *prefixes: str) -> None:
        super().__init__()
        self._prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno == logging.INFO:
            for prefix in self._prefixes:
                if record.name.startswith(prefix):
                    record.levelno = logging.DEBUG
                    record.levelname = logging.getLevelName(logging.DEBUG)
                    break
        return True
