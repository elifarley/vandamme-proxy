"""Endpoint response DTOs.

Type-safe response containers that provide consistent structure
across all endpoint responses.
"""

from dataclasses import dataclass
from typing import Any

from fastapi.responses import JSONResponse, Response


@dataclass(frozen=True, slots=True)
class ModelsListResponse:
    """Structured response from /v1/models endpoint."""

    status: int
    content: dict[str, Any]
    headers: dict[str, str] | None = None

    def to_response(self) -> Response:
        """Convert to FastAPI response."""
        if self.headers:
            return JSONResponse(
                status_code=self.status,
                content=self.content,
                headers=self.headers,
            )
        return JSONResponse(status_code=self.status, content=self.content)


@dataclass(frozen=True, slots=True)
class TopModelsResponse:
    """Structured response from /top-models endpoint."""

    status: int
    content: dict[str, Any]

    def to_response(self) -> Response:
        """Convert to FastAPI response."""
        return JSONResponse(status_code=self.status, content=self.content)
