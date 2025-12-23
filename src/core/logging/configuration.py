"""Logging configuration.

This module is the *only* place where we mutate the global Python logging
subsystem (root handlers and uvicorn handlers).

Educational note:
- We deliberately **clear+replace** handlers to match the existing semantics of
  the project (and to prevent accidental handler duplication).
- This is a conscious tradeoff: we prefer predictable app logs over
  best-effort composition with arbitrary third-party handlers.

This module must remain import-safe: nothing runs at import time.
"""

from __future__ import annotations

import logging
import logging.handlers
import os

from src.core.config import config

from .filters.http import HttpRequestLogDowngradeFilter
from .formatters.correlation import CorrelationHashingFormatter
from .formatters.syslog import JournaldFormatter

NOISY_HTTP_LOGGERS: tuple[str, ...] = (
    "openai",
    "httpx",
    "httpcore",
    "httpcore.http11",
    "httpcore.connection",
)


def set_noisy_http_logger_levels(current_log_level: str) -> None:
    """Ensure HTTP client noise only surfaces at DEBUG level."""

    noisy_level = logging.DEBUG if current_log_level == "DEBUG" else logging.WARNING
    for logger_name in NOISY_HTTP_LOGGERS:
        logging.getLogger(logger_name).setLevel(noisy_level)


def _build_syslog_handler() -> logging.Handler | None:
    if os.path.exists("/dev/log"):
        handler = logging.handlers.SysLogHandler(address="/dev/log")
        handler.setFormatter(
            JournaldFormatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")
        )
        handler.addFilter(HttpRequestLogDowngradeFilter(*NOISY_HTTP_LOGGERS))
        handler.set_name("syslog")
        return handler
    return None


def _build_console_handler(formatter: logging.Formatter) -> logging.Handler:
    handler = logging.StreamHandler()
    handler.addFilter(HttpRequestLogDowngradeFilter(*NOISY_HTTP_LOGGERS))
    handler.setFormatter(formatter)
    handler.set_name("console")
    return handler


def _resolve_formatter() -> logging.Formatter:
    return CorrelationHashingFormatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
    )


LOGGING_MODE_REQUESTED_SYSTEMD: bool = False
LOGGING_MODE_EFFECTIVE_HANDLER_NAME: str | None = None


def get_logging_mode() -> dict[str, object]:
    """Return the effective logging mode for UI/diagnostics.

    We expose this so the dashboard can decide whether to enable features that
    depend on journald/syslog integration.
    """

    return {
        "requested_systemd": LOGGING_MODE_REQUESTED_SYSTEMD,
        "effective_handler": LOGGING_MODE_EFFECTIVE_HANDLER_NAME,
        "effective_systemd": LOGGING_MODE_EFFECTIVE_HANDLER_NAME == "syslog",
    }


def configure_root_logging(*, use_systemd: bool = False) -> None:
    """Configure root and uvicorn loggers.

    Why this function exists:
        - Centralize logging wiring.
        - Make logging configuration **explicit** (entrypoints call it).
        - Keep handler setup consistent for root + uvicorn.

    IMPORTANT SEMANTICS (matches existing behavior):
        - We clear+replace root handlers.
        - We clear+replace uvicorn handlers.
        - We downgrade noisy HTTP logs unless DEBUG.

    Idempotency:
        Calling this multiple times yields the same effective handler set.
    """

    log_level = config.log_level.split()[0].upper()
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if log_level not in valid_levels:
        log_level = "INFO"

    uvicorn_loggers = ("uvicorn", "uvicorn.access", "uvicorn.error", "uvicorn.server")

    global LOGGING_MODE_REQUESTED_SYSTEMD
    global LOGGING_MODE_EFFECTIVE_HANDLER_NAME

    LOGGING_MODE_REQUESTED_SYSTEMD = use_systemd

    if use_systemd:
        handler = _build_syslog_handler()
        if not handler:
            # /dev/log unavailable (local dev, some containers). Fall back.
            handler = _build_console_handler(_resolve_formatter())
    else:
        handler = _build_console_handler(_resolve_formatter())

    LOGGING_MODE_EFFECTIVE_HANDLER_NAME = handler.get_name()

    if log_level == "DEBUG":
        logging.getLogger(__name__).debug("LOG_LEVEL=DEBUG: noisy HTTP log suppression disabled")

    # Root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level))

    # Uvicorn loggers share the same handler for consistent output.
    for logger_name in uvicorn_loggers:
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.addHandler(handler)
        uvicorn_logger.setLevel(logging.WARNING if log_level != "DEBUG" else logging.INFO)

    set_noisy_http_logger_levels(log_level)
