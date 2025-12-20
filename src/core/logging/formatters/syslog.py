"""Syslog / journald formatting.

We send structured-ish messages to syslog via SysLogHandler.
Important: SysLogHandler itself prepends the <N> priority wrapper. We only add
our application tag prefix.
"""

from __future__ import annotations

import logging

from src.core.security import hash_api_keys_in_message


class JournaldFormatter(logging.Formatter):
    """Syslog-friendly formatter with vandamme-proxy tag + API key hashing."""

    def format(self, record: logging.LogRecord) -> str:
        if hasattr(record, "correlation_id"):
            prefix = f"[{record.correlation_id[:8]}]"
            if not str(record.msg).startswith(prefix):
                record.msg = f"{prefix} {record.msg}"

        msg = super().format(record)
        msg = hash_api_keys_in_message(msg)
        return f"vandamme-proxy: {msg}"
