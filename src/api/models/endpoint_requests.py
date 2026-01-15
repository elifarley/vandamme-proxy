"""Endpoint request DTOs.

Type-safe data containers for endpoint parameters, extracted from FastAPI's
dependency injection for cleaner service layer integration.
"""

from dataclasses import dataclass

from fastapi import Header, Query


@dataclass(frozen=True, slots=True)
class ModelsListRequest:
    """Parameters for /v1/models endpoint.

    Encapsulates all query parameters and headers for model listing,
    providing a single type-safe object for service layer consumption.
    """

    provider: str | None
    format_requested: str | None  # noqa: A003
    refresh: bool
    provider_header: str | None
    anthropic_version: str | None

    @classmethod
    def from_fastapi(
        cls,
        provider: str | None = Query(
            None,
            description=(
                "Provider name to fetch models from (defaults to configured default provider)"
            ),
        ),
        format: str | None = Query(  # noqa: A003
            None,
            description=(
                "Response format selector (takes precedence over headers): "
                "anthropic, openai, or raw. If omitted, inferred from headers."
            ),
        ),
        refresh: bool = Query(
            False,
            description="Force refresh model list from upstream (bypass models cache)",
        ),
        provider_header: str | None = Header(
            None,
            alias="provider",
            description="Provider override (header takes precedence over query/default)",
        ),
        anthropic_version: str | None = Header(
            None,
            alias="anthropic-version",
            description=(
                "If present and no explicit format=... was provided, the response format "
                "may be inferred as Anthropic for /v1/models compatibility"
            ),
        ),
    ) -> "ModelsListRequest":
        """Create request from FastAPI dependencies.

        This classmethod enables FastAPI's dependency injection to populate
        the DTO directly, eliminating parameter passing anti-patterns.

        Usage:
            @router.get("/v1/models")
            async def list_models(
                request: ModelsListRequest = Depends(ModelsListRequest.from_fastapi),
                ...
            ):
        """
        return cls(
            provider=provider,
            format_requested=format,
            refresh=refresh,
            provider_header=provider_header,
            anthropic_version=anthropic_version,
        )


@dataclass(frozen=True, slots=True)
class TopModelsRequest:
    """Parameters for /top-models endpoint.

    Encapsulates query parameters for curated top models retrieval.
    """

    limit: int
    refresh: bool
    provider: str | None
    include_cache_info: bool

    @classmethod
    def from_fastapi(
        cls,
        limit: int = Query(10, ge=1, le=50),
        refresh: bool = Query(False),
        provider: str | None = Query(None),
        include_cache_info: bool = Query(False),
    ) -> "TopModelsRequest":
        """Create request from FastAPI dependencies.

        Usage:
            @router.get("/top-models")
            async def top_models(
                request: TopModelsRequest = Depends(TopModelsRequest.from_fastapi),
                ...
            ):
        """
        return cls(
            limit=limit,
            refresh=refresh,
            provider=provider,
            include_cache_info=include_cache_info,
        )
