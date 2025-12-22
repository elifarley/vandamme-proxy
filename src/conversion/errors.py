from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConversionError(Exception):
    """Base class for conversion-layer exceptions.

    These errors are intended to carry structured context that can be:
    - logged deterministically
    - mapped to stable client-visible error payloads
    - optionally attached to request metrics
    """

    message: str
    error_type: str = "conversion_error"
    context: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return self.message


@dataclass(frozen=True)
class SSEParseError(ConversionError):
    error_type: str = "sse_parse_error"


@dataclass(frozen=True)
class StreamingCancelledError(ConversionError):
    error_type: str = "cancelled"


@dataclass(frozen=True)
class StreamingInternalError(ConversionError):
    error_type: str = "streaming_error"
