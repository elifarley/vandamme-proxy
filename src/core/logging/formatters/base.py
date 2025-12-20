"""Base formatters.

Keep formatters focused and composable. We avoid clever metaprogramming so that
formatting behavior remains obvious to readers.
"""

from __future__ import annotations

import logging

from src.core.security import hash_api_keys_in_message


class HashingFormatter(logging.Formatter):
    """Formatter that hashes API keys in the final rendered message."""

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        return hash_api_keys_in_message(rendered)
