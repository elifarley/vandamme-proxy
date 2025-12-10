import json
import logging
import os
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, Optional

from src.core.config import config

# Parse log level - extract just the first word to handle comments
log_level = config.log_level.split()[0].upper()

# Validate and set default if invalid
valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
if log_level not in valid_levels:
    log_level = "INFO"


NOISY_HTTP_LOGGERS = (
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


# Enhanced Logging Infrastructure
@dataclass
class RequestMetrics:
    """Metrics for a single request"""

    request_id: str
    start_time: float
    end_time: Optional[float] = None
    claude_model: Optional[str] = None
    openai_model: Optional[str] = None
    provider: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    message_count: int = 0
    request_size: int = 0  # bytes
    response_size: int = 0  # bytes
    is_streaming: bool = False
    error: Optional[str] = None
    error_type: Optional[str] = None

    @property
    def duration_ms(self) -> float:
        """Request duration in milliseconds"""
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0


@dataclass
class SummaryMetrics:
    """Accumulated metrics for summary"""

    total_requests: int = 0
    total_errors: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_duration_ms: float = 0
    model_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    error_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add_request(self, metrics: RequestMetrics) -> None:
        """Add request metrics to summary"""
        self.total_requests += 1
        self.total_input_tokens += metrics.input_tokens
        self.total_output_tokens += metrics.output_tokens
        self.total_cache_read_tokens += metrics.cache_read_tokens
        self.total_duration_ms += metrics.duration_ms

        if metrics.openai_model:
            self.model_counts[metrics.openai_model] += 1

        if metrics.error:
            self.total_errors += 1
            error_key = metrics.error_type or "unknown"
            self.error_counts[error_key] += 1


class RequestTracker:
    """Singleton tracker for request metrics"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls) -> "RequestTracker":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "initialized"):
            self.active_requests: Dict[str, RequestMetrics] = {}
            self.summary_metrics = SummaryMetrics()
            self.summary_interval = int(os.environ.get("LOG_SUMMARY_INTERVAL", "100"))
            self.request_count = 0
            self.initialized = True

    def start_request(
        self, request_id: str, claude_model: str, is_streaming: bool = False
    ) -> RequestMetrics:
        """Start tracking a new request"""
        metrics = RequestMetrics(
            request_id=request_id,
            start_time=time.time(),
            claude_model=claude_model,
            is_streaming=is_streaming,
        )
        self.active_requests[request_id] = metrics
        return metrics

    def end_request(self, request_id: str, **kwargs: Any) -> None:
        """End request tracking and update summary"""
        if request_id not in self.active_requests:
            return

        metrics = self.active_requests[request_id]
        metrics.end_time = time.time()

        # Update any provided fields
        for key, value in kwargs.items():
            if hasattr(metrics, key):
                setattr(metrics, key, value)

        # Add to summary
        self.summary_metrics.add_request(metrics)
        self.request_count += 1

        # Check if we should emit summary
        if self.request_count % self.summary_interval == 0:
            self._emit_summary()

        # Remove from active
        del self.active_requests[request_id]

    def get_request(self, request_id: str) -> Optional[RequestMetrics]:
        """Get active request metrics"""
        return self.active_requests.get(request_id)

    def _emit_summary(self) -> None:
        """Emit summary log"""
        logger.info(
            f"📊 SUMMARY (last {self.summary_interval} requests) | "
            f"Total: {self.summary_metrics.total_requests} | "
            f"Errors: {self.summary_metrics.total_errors} | "
            f"Avg Duration: {self.summary_metrics.total_duration_ms / max(1, self.summary_metrics.total_requests):.0f}ms | "
            f"Input Tokens: {self.summary_metrics.total_input_tokens:,} | "
            f"Output Tokens: {self.summary_metrics.total_output_tokens:,} | "
            f"Cache Hits: {self.summary_metrics.total_cache_read_tokens:,}"
        )

        # Log model distribution
        if self.summary_metrics.model_counts:
            model_dist = " | ".join(
                [f"{model}: {count}" for model, count in self.summary_metrics.model_counts.items()]
            )
            logger.info(f"📊 MODELS | {model_dist}")

        # Log errors if any
        if self.summary_metrics.error_counts:
            error_dist = " | ".join(
                [f"{error}: {count}" for error, count in self.summary_metrics.error_counts.items()]
            )
            logger.warning(f"📊 ERRORS | {error_dist}")

        # Reset summary metrics
        self.summary_metrics = SummaryMetrics()


class ConversationLogger:
    """Logger with correlation ID support"""

    @staticmethod
    def get_logger() -> logging.Logger:
        """Get logger with correlation ID support"""
        return logging.getLogger("conversation")

    @staticmethod
    @contextmanager
    def correlation_context(request_id: str) -> Generator[None, None, None]:
        """Context manager for correlation ID"""
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


# Custom formatter with correlation ID
class CorrelationFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Add correlation ID if available
        if hasattr(record, "correlation_id"):
            record.msg = f"[{record.correlation_id[:8]}] {record.msg}"
        return super().format(record)


# Configure root logger
formatter = CorrelationFormatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")


class HttpRequestLogDowngradeFilter(logging.Filter):
    """Downgrade noisy third-party HTTP logs to DEBUG."""

    def __init__(self, *prefixes: str) -> None:
        super().__init__()
        self.prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno == logging.INFO:
            for prefix in self.prefixes:
                if record.name.startswith(prefix):
                    record.levelno = logging.DEBUG
                    record.levelname = logging.getLevelName(logging.DEBUG)
                    break
        return True


handler = logging.StreamHandler()
handler.addFilter(HttpRequestLogDowngradeFilter(*NOISY_HTTP_LOGGERS))
handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.handlers.clear()
root_logger.addHandler(handler)
root_logger.setLevel(getattr(logging, log_level))

# Configure uvicorn to be quieter
for uvicorn_logger in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
    logging.getLogger(uvicorn_logger).setLevel(logging.WARNING)

set_noisy_http_logger_levels(log_level)

# Global instances
logger = logging.getLogger(__name__)
request_tracker = RequestTracker()
conversation_logger = ConversationLogger.get_logger()

# Check if request metrics are enabled
LOG_REQUEST_METRICS = os.environ.get("LOG_REQUEST_METRICS", "true").lower() == "true"
