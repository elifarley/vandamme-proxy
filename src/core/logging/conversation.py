"""Conversation logging helpers.

A correlation id (request id) is injected into LogRecord instances while a
request is being processed.

This is intentionally implemented as a small context manager rather than a
global singleton to keep usage obvious and testable.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any


class ConversationLogger:
    """Factory for loggers used in request/conversation contexts."""

    @staticmethod
    def get_logger() -> logging.Logger:
        return logging.getLogger("conversation")

    @staticmethod
    @contextmanager
    def correlation_context(request_id: str) -> Generator[None, None, None]:
        """Temporarily inject a correlation_id into all created LogRecords."""

        old_factory = logging.getLogRecordFactory()

        def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = old_factory(*args, **kwargs)
            record.correlation_id = request_id
            return record

        logging.setLogRecordFactory(record_factory)
        try:
            yield
        finally:
            logging.setLogRecordFactory(old_factory)
