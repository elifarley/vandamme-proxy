"""src.core.logging

Logging infrastructure for Vandamme Proxy.

MIGRATION NOTES
---------------
This package replaces the historical monolithic module `src.core.logging`.
The new design has two core principles:

1) **Explicit initialization**
   Importing this package must never configure the Python logging subsystem.
   Entry points (CLI commands / server startup / tests) must call:

       configure_root_logging(...)

2) **Single-responsibility modules**
   - configuration: building handlers + wiring root/uvicorn loggers
   - formatters/filters: reusable logging components
   - conversation: correlation context helpers

This makes behavior predictable under import-order changes and keeps tests
isolated.
"""

from __future__ import annotations

from .configuration import NOISY_HTTP_LOGGERS, configure_root_logging, set_noisy_http_logger_levels
from .conversation import ConversationLogger

__all__ = [
    "NOISY_HTTP_LOGGERS",
    "configure_root_logging",
    "set_noisy_http_logger_levels",
    "ConversationLogger",
]
