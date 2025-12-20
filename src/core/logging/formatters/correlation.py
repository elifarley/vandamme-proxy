"""Correlation-aware formatters.

Correlation IDs are attached to LogRecord objects by the conversation context.
These formatters render a short prefix so logs from a single request can be
tracked across the stack.
"""

from __future__ import annotations

import logging

from .base import HashingFormatter


class CorrelationFormatter(logging.Formatter):
    """Backward-compatible correlation formatter (no hashing)."""

    def format(self, record: logging.LogRecord) -> str:
        if hasattr(record, "correlation_id"):
            record.msg = f"[{record.correlation_id[:8]}] {record.msg}"
        return super().format(record)


class CorrelationHashingFormatter(HashingFormatter):
    """Formatter that prefixes correlation id and hashes API keys."""

    def format(self, record: logging.LogRecord) -> str:
        if hasattr(record, "correlation_id"):
            record.msg = f"[{record.correlation_id[:8]}] {record.msg}"
        return super().format(record)
