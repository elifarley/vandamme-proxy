"""API models for endpoint request/response DTOs.

This package provides type-safe data transfer objects (DTOs) for API endpoints,
ensuring clean separation between HTTP layer and business logic.
"""

from src.api.models.endpoint_requests import (
    ModelsListRequest,
    TopModelsRequest,
)
from src.api.models.endpoint_responses import (
    ModelsListResponse,
    TopModelsResponse,
)

__all__ = [
    "TopModelsRequest",
    "ModelsListRequest",
    "TopModelsResponse",
    "ModelsListResponse",
]
