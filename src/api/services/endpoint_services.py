"""Endpoint service layer for business logic abstraction.

Elevates business logic from routing layer into dedicated, testable services.
Each service encapsulates a single endpoint's core operations.

Design principles:
- Single Responsibility: Each service handles one endpoint's logic
- Dependency Injection: All dependencies passed via constructor
- Testability: Services can be unit tested independently of FastAPI
- Type Safety: Return structured result types, not raw dictionaries
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from src.api.models.endpoint_requests import ModelsListRequest, TopModelsRequest
from src.api.utils.yaml_formatter import format_health_yaml
from src.core.config import Config
from src.models.cache import ModelsDiskCache

# Type alias for fetch function
FetchModelsFunc = Callable[[str, dict[str, str]], Awaitable[dict[str, Any]]]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ModelsListResult:
    """Structured result from /v1/models endpoint."""

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
class HealthCheckResult:
    """Structured result from /health endpoint."""

    status: int
    content: str
    media_type: str = "text/yaml; charset=utf-8"
    headers: dict[str, str] | None = None

    def to_response(self) -> Response:
        """Convert to FastAPI response."""
        return PlainTextResponse(
            content=self.content,
            status_code=self.status,
            media_type=self.media_type,
            headers=self.headers,
        )


@dataclass(frozen=True, slots=True)
class TokenCountResult:
    """Structured result from /v1/messages/count_tokens endpoint."""

    status: int
    content: dict[str, Any]

    def to_response(self) -> Response:
        """Convert to FastAPI response."""
        return JSONResponse(status_code=self.status, content=self.content)


@dataclass(frozen=True, slots=True)
class AliasesListResult:
    """Structured result from /v1/aliases endpoint."""

    status: int
    content: dict[str, Any]

    def to_response(self) -> Response:
        """Convert to FastAPI response."""
        return JSONResponse(status_code=self.status, content=self.content)


class ModelsListService:
    """Service for /v1/models endpoint logic.

    Handles provider resolution, caching, format conversion, and error handling
    for model listing operations.
    """

    def __init__(
        self,
        config: Config,
        models_cache: ModelsDiskCache | None,
        fetch_fn: FetchModelsFunc | None = None,
    ) -> None:
        """Initialize service with dependencies.

        Args:
            config: Application configuration
            models_cache: Optional disk cache for model lists
            fetch_fn: Optional async function to fetch models from upstream.
                     If not provided, uses default httpx-based implementation.
        """
        self._config = config
        self._cache = models_cache
        self._fetch_fn = fetch_fn

    async def execute(
        self,
        provider_candidate: str | None,
        format_requested: str | None,
        refresh: bool,
        anthropic_version: str | None,
    ) -> ModelsListResult:
        """Execute the models list operation.

        Args:
            provider_candidate: Provider name from query/header (None = default)
            format_requested: Response format (anthropic|openai|raw)
            refresh: Force cache bypass
            anthropic_version: Anthropic version header for format inference

        Returns:
            ModelsListResult with status code and content
        """
        try:
            provider_name = self._resolve_provider(provider_candidate)
            self._validate_provider_exists(provider_name)

            format_type = self._infer_format(format_requested, anthropic_version)
            self._validate_format(format_type)

            raw = await self._fetch_models(provider_name, refresh)

            if format_type == "raw":
                return ModelsListResult(status=200, content=raw)

            return self._convert_to_format(raw, format_type)

        except (httpx.HTTPStatusError, ValueError, KeyError) as e:
            # Expected errors: HTTP errors, validation errors, missing keys
            return self._error_response(str(e))
        except Exception as unexpected:
            # Truly unexpected errors
            logger.error(
                f"Unexpected error in ModelsListService: {type(unexpected).__name__}: {unexpected}"
            )
            return self._error_response(str(unexpected))

    async def execute_with_request(self, request: ModelsListRequest) -> ModelsListResult:
        """Execute using ModelsListRequest DTO.

        This method provides a cleaner API when using DTOs from the endpoint layer.

        Args:
            request: ModelsListRequest DTO containing all parameters

        Returns:
            ModelsListResult with status code and content
        """
        return await self.execute(
            provider_candidate=request.provider,
            format_requested=request.format_requested,
            refresh=request.refresh,
            anthropic_version=request.anthropic_version,
        )

    def _resolve_provider(self, candidate: str | None) -> str:
        """Resolve provider name from candidate or default."""
        if candidate:
            return candidate.lower()
        return self._config.provider_manager.default_provider

    def _validate_provider_exists(self, provider_name: str) -> None:
        """Validate provider exists, raise 404 if not."""
        all_providers = self._config.provider_manager.list_providers()
        if provider_name not in all_providers:
            available = ", ".join(sorted(all_providers.keys()))
            raise httpx.HTTPStatusError(
                message=f"Provider '{provider_name}' not found. Available providers: {available}",
                request=None,  # type: ignore[arg-type]
                response=None,  # type: ignore[arg-type]
            )

    def _infer_format(self, format_requested: str | None, anthropic_version: str | None) -> str:
        """Infer response format from parameters and headers."""
        if format_requested is None:
            # Default: OpenAI, unless Anthropic version header present
            return "anthropic" if anthropic_version else "openai"
        return format_requested

    def _validate_format(self, format_type: str) -> None:
        """Validate format is supported."""
        if format_type not in {"anthropic", "openai", "raw"}:
            raise ValueError("Invalid format. Use format=anthropic|openai|raw")

    async def _fetch_models(self, provider_name: str, refresh: bool) -> dict[str, Any]:
        """Fetch models from cache or upstream.

        Implements cache-first strategy with fallback to stale cache on error.
        """
        provider_config = self._config.provider_manager.get_provider_config(provider_name)
        client = self._config.provider_manager.get_client(provider_name)
        base_url = client.base_url
        custom_headers = provider_config.custom_headers if provider_config else {}

        # Try fresh cache first
        if not refresh and self._cache:
            cached = self._cache.read_response_if_fresh(
                provider=provider_name,
                base_url=base_url,
                custom_headers=custom_headers,
            )
            if cached:
                return cached

        # Fetch from upstream
        try:
            if self._fetch_fn:
                raw = await self._fetch_fn(base_url, custom_headers)
            else:
                raw = await self._default_fetch(base_url, custom_headers)

            if self._cache and raw:
                self._cache.write_response(
                    provider=provider_name,
                    base_url=base_url,
                    custom_headers=custom_headers,
                    response=raw,
                )
            return raw

        except (httpx.HTTPError, ConnectionError, asyncio.TimeoutError) as e:
            # Network/HTTP errors - try stale cache
            logger.debug(f"Upstream fetch failed, trying stale cache: {type(e).__name__}: {e}")
            if self._cache:
                stale = self._cache.read_response_if_any(
                    provider=provider_name,
                    base_url=base_url,
                    custom_headers=custom_headers,
                )
                if stale:
                    return stale
            raise

    async def _default_fetch(self, base_url: str, custom_headers: dict[str, str]) -> dict[str, Any]:
        """Default fetch implementation using httpx."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "claude-proxy/1.0.0",
            **custom_headers,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{base_url}/models", headers=headers)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]

    def _convert_to_format(self, raw: dict[str, Any], format_type: str) -> ModelsListResult:
        """Convert raw response to requested format."""
        from src.conversion.models_converter import (
            raw_to_anthropic_models,
            raw_to_openai_models,
        )

        if format_type == "openai":
            return ModelsListResult(status=200, content=raw_to_openai_models(raw))

        # Default: anthropic
        return ModelsListResult(status=200, content=raw_to_anthropic_models(raw))

    def _error_response(self, error_message: str) -> ModelsListResult:
        """Generate error response."""
        return ModelsListResult(
            status=500,
            content={
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": f"Failed to list models: {error_message}",
                },
            },
        )


class HealthCheckService:
    """Service for /health endpoint logic.

    Gathers provider information and formats health status with graceful degradation.
    """

    def __init__(self, config: Config) -> None:
        """Initialize service with dependencies.

        Args:
            config: Application configuration
        """
        self._config = config

    def execute(self) -> HealthCheckResult:
        """Execute health check and gather provider information.

        Returns:
            HealthCheckResult with formatted YAML output
        """
        try:
            health_data = self._gather_health_data()
            yaml_output = format_health_yaml(health_data)

            return HealthCheckResult(
                status=200,
                content=yaml_output,
                headers={
                    "Cache-Control": "no-cache",
                    "Content-Disposition": (
                        f"inline; filename=health-{datetime.now().strftime('%Y%m%d-%H%M%S')}.yaml"
                    ),
                },
            )

        except (AttributeError, KeyError, TypeError, ValueError) as e:
            logger.debug(f"Health check data gathering failed: {type(e).__name__}: {e}")
            return self._degraded_response(str(e))

    def _gather_health_data(self) -> dict[str, Any]:
        """Gather health data from all providers."""
        providers = self._gather_provider_info()

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "api_key_valid": self._config.validate_api_key(),
            "client_api_key_validation": bool(self._config.proxy_api_key),
            "default_provider": getattr(
                self._config.provider_manager, "default_provider", "unknown"
            ),
            "providers": providers,
        }

    def _gather_provider_info(self) -> dict[str, Any]:
        """Gather information for all configured providers."""
        providers: dict[str, Any] = {}
        try:
            for provider_name in self._config.provider_manager.list_providers():
                provider_config = self._config.provider_manager.get_provider_config(provider_name)

                # Determine auth mode indicator
                auth_mode = "unknown"
                if provider_config:
                    if provider_config.uses_oauth:
                        auth_mode = "oauth"
                    elif provider_config.uses_passthrough:
                        auth_mode = "passthrough"
                    else:
                        auth_mode = "api_key"

                providers[provider_name] = {
                    "api_format": (provider_config.api_format if provider_config else "unknown"),
                    "base_url": provider_config.base_url if provider_config else None,
                    "auth_mode": auth_mode,
                    "api_key_hash": (
                        f"sha256:{self._config.provider_manager.get_api_key_hash(provider_config.api_key)}"
                        if provider_config and provider_config.api_key
                        else "<not set>"
                    ),
                }
        except (AttributeError, KeyError, TypeError, ValueError) as e:
            # Provider info is optional; don't fail health check
            logger.debug(f"Provider info gathering failed: {type(e).__name__}: {e}")

        return providers

    def _degraded_response(self, error_message: str) -> HealthCheckResult:
        """Generate degraded health response when config is incomplete."""
        degraded_data = {
            "status": "degraded",
            "timestamp": datetime.now().isoformat(),
            "error": error_message,
            "message": "Server is running but configuration is incomplete",
            "suggestions": [
                "Set OPENAI_API_KEY environment variable for OpenAI provider",
                "Set VDM_DEFAULT_PROVIDER to specify your preferred provider",
                "Check .env file for required configuration",
            ],
        }

        yaml_output = format_health_yaml(degraded_data)

        return HealthCheckResult(
            status=200,  # Still return 200 for degraded
            content=yaml_output,
            headers={
                "Cache-Control": "no-cache",
                "Content-Disposition": (
                    f"inline; filename=health-{datetime.now().strftime('%Y%m%d-%H%M%S')}.yaml"
                ),
            },
        )


class TokenCountService:
    """Service for /v1/messages/count_tokens endpoint logic.

    Handles token counting via provider API or character-based fallback.
    """

    def __init__(self, config: Config) -> None:
        """Initialize service with dependencies.

        Args:
            config: Application configuration
        """
        self._config = config

    async def execute(
        self,
        model: str,
        system: str | list[Any] | None,
        messages: list[Any],
        model_manager: Any,
    ) -> TokenCountResult:
        """Execute token counting.

        Args:
            model: Model name for resolution
            system: System message content
            messages: List of message objects
            model_manager: ModelManager instance for resolution

        Returns:
            TokenCountResult with input_tokens count
        """
        try:
            provider_name, actual_model = model_manager.resolve_model(model)
            provider_config = self._config.provider_manager.get_provider_config(provider_name)

            # Try Anthropic-compatible API token counting first
            if provider_config and provider_config.is_anthropic_format:
                api_tokens = await self._try_provider_token_count(actual_model, system, messages)
                if api_tokens is not None:
                    return TokenCountResult(status=200, content={"input_tokens": api_tokens})

            # Fallback to character-based estimation
            estimated = self._estimate_tokens(system, messages)
            return TokenCountResult(status=200, content={"input_tokens": estimated})

        except (AttributeError, KeyError, TypeError, ValueError, ImportError) as e:
            logger.debug(
                f"Token counting failed, falling back to estimation: {type(e).__name__}: {e}"
            )
            estimated = self._estimate_tokens(system, messages)
            return TokenCountResult(status=200, content={"input_tokens": estimated})

    async def _try_provider_token_count(
        self,
        model: str,
        system: str | list[Any] | None,
        messages: list[Any],
    ) -> int | None:
        """Attempt to get token count from provider API.

        Returns None if provider doesn't support counting or on error.
        """
        try:
            client = self._config.provider_manager.get_client(
                self._config.provider_manager.default_provider
            )

            # Build minimal request for token counting
            count_request = {
                "model": model,
                "messages": self._build_messages_for_counting(system, messages),
            }

            count_response = await client.create_chat_completion(
                {**count_request, "max_tokens": 1}, "count_tokens"
            )

            # Extract usage if available
            usage = count_response.get("usage", {})
            tokens = usage.get("input_tokens")
            return tokens if isinstance(tokens, int) else None

        except (
            httpx.HTTPError,
            ConnectionError,
            asyncio.TimeoutError,
            KeyError,
            AttributeError,
            TypeError,
        ) as e:
            # Provider doesn't support counting; fall through
            logger.debug(f"Provider token count failed: {type(e).__name__}: {e}")
            return None

    def _build_messages_for_counting(
        self,
        system: str | list[Any] | None,
        messages: list[Any],
    ) -> list[dict[str, Any]]:
        """Build message list for token counting request."""
        messages_list: list[dict[str, Any]] = []

        # Add system message
        if system:
            if isinstance(system, str):
                messages_list.append({"role": "user", "content": system})
            elif isinstance(system, list):
                text = "".join(
                    block.text for block in system if hasattr(block, "text") and block.text
                )
                messages_list.append({"role": "user", "content": text})

        # Add messages with text extraction
        for msg in messages:
            msg_dict: dict[str, Any] = {"role": msg.role}
            if isinstance(msg.content, str):
                msg_dict["content"] = msg.content
            elif isinstance(msg.content, list):
                text_parts = [
                    block.text for block in msg.content if hasattr(block, "text") and block.text
                ]
                msg_dict["content"] = "".join(text_parts)
            messages_list.append(msg_dict)

        return messages_list

    def _estimate_tokens(
        self,
        system: str | list[Any] | None,
        messages: list[Any],
    ) -> int:
        """Estimate tokens using character-based heuristic (~4 chars per token)."""
        total_chars = 0

        # Count system message characters
        if system:
            if isinstance(system, str):
                total_chars += len(system)
            elif isinstance(system, list):
                for block in system:
                    if hasattr(block, "text"):
                        total_chars += len(block.text)

        # Count message characters
        for msg in messages:
            if msg.content is None:
                continue
            elif isinstance(msg.content, str):
                total_chars += len(msg.content)
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if hasattr(block, "text") and block.text:
                        total_chars += len(block.text)

        # Rough estimation: 4 characters per token
        return max(1, total_chars // 4)


class AliasesListService:
    """Service for /v1/aliases endpoint logic.

    Retrieves active aliases and overlays suggested aliases from top-models.
    """

    def __init__(self, config: Config) -> None:
        """Initialize service with dependencies.

        Args:
            config: Application configuration
        """
        self._config = config

    async def execute(self) -> AliasesListResult:
        """Execute aliases list retrieval.

        Returns:
            AliasesListResult with aliases grouped by provider and suggestions
        """
        try:
            aliases = self._config.alias_service.get_active_aliases()
            suggested = await self._fetch_suggested_aliases()

            total_aliases = sum(len(provider_aliases) for provider_aliases in aliases.values())

            return AliasesListResult(
                status=200,
                content={
                    "object": "list",
                    "aliases": aliases,
                    "suggested": suggested,
                    "total": total_aliases,
                },
            )

        except Exception as e:
            # Service boundary: catch all exceptions for API error response conversion
            logger.error(f"Aliases listing failed: {type(e).__name__}: {e}")
            return AliasesListResult(
                status=500,
                content={
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": f"Failed to list aliases: {str(e)}",
                    },
                },
            )

    async def _fetch_suggested_aliases(self) -> dict[str, dict[str, str]]:
        """Fetch suggested aliases from top-models service.

        Returns empty dict on error; suggestions should never break the endpoint.
        """
        try:
            from src.top_models.service import TopModelsService
            from src.top_models.source import TopModelsSourceError

            top = await TopModelsService().get_top_models(limit=10, refresh=False, provider=None)
            if top.aliases:
                return {"default": top.aliases}
        except (
            ImportError,
            ConnectionError,
            asyncio.TimeoutError,
            AttributeError,
            TopModelsSourceError,
            RuntimeError,
        ) as e:
            # Suggestions are optional; log and continue
            logger.debug(f"Suggested aliases fetch failed: {type(e).__name__}: {e}")

        return {}


@dataclass(frozen=True, slots=True)
class TestConnectionResult:
    """Structured result from /test-connection endpoint."""

    status: int
    content: dict[str, Any]

    def to_response(self) -> Response:
        """Convert to FastAPI response."""
        return JSONResponse(status_code=self.status, content=self.content)


@dataclass(frozen=True, slots=True)
class TopModelsEndpointResult:
    """Structured result from /top-models endpoint."""

    status: int
    content: dict[str, Any]

    def to_response(self) -> Response:
        """Convert to FastAPI response."""
        return JSONResponse(status_code=self.status, content=self.content)


class TestConnectionService:
    """Service for /test-connection endpoint logic.

    Tests API connectivity to the default provider by making a minimal
    chat completion request.
    """

    def __init__(self, config: Config) -> None:
        """Initialize TestConnectionService.

        Args:
            config: Application configuration
        """
        self._config = config

    async def execute(self) -> TestConnectionResult:
        """Execute connectivity test to default provider.

        Returns:
            TestConnectionResult with test status and details
        """
        try:
            default_provider = self._config.provider_manager.default_provider
            default_client = self._config.provider_manager.get_client(default_provider)

            # Minimal test request to verify API connectivity
            test_response = await default_client.create_chat_completion(
                {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 20,
                }
            )

            # Defensive check for None response
            if test_response is None:
                return TestConnectionResult(
                    status=503,
                    content={
                        "status": "failed",
                        "message": f"Provider {default_provider} returned None response",
                        "provider": default_provider,
                        "error": "None response from provider",
                    },
                )

            return TestConnectionResult(
                status=200,
                content={
                    "status": "success",
                    "message": f"Successfully connected to {default_provider} API",
                    "provider": default_provider,
                    "model_used": "gpt-4o-mini",
                    "timestamp": datetime.now().isoformat(),
                    "response_id": test_response.get("id", "unknown"),
                },
            )

        except (
            httpx.HTTPError,
            ConnectionError,
            asyncio.TimeoutError,
            KeyError,
            AttributeError,
            TypeError,
        ) as e:
            logger.debug(f"Connection test failed: {type(e).__name__}: {e}")
            return TestConnectionResult(
                status=503,
                content={
                    "status": "failed",
                    "error_type": "API Error",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat(),
                    "suggestions": [
                        "Check your OPENAI_API_KEY is valid",
                        "Verify your API key has the necessary permissions",
                        "Check if you have reached rate limits",
                    ],
                },
            )


class TopModelsEndpointService:
    """Service for /top-models endpoint logic.

    Fetches curated top models and transforms them into the API response format.
    """

    def __init__(
        self,
        config: Config,
        models_cache: ModelsDiskCache | None = None,
    ) -> None:
        """Initialize TopModelsEndpointService.

        Args:
            config: Application configuration
            models_cache: Optional disk cache for models data
        """
        self._config = config
        self._models_cache = models_cache

    async def execute(
        self,
        limit: int = 10,
        refresh: bool = False,
        provider: str | None = None,
        include_cache_info: bool = False,
    ) -> TopModelsEndpointResult:
        """Execute top models retrieval and transformation.

        Args:
            limit: Maximum number of models to return
            refresh: Force refresh from upstream
            provider: Filter by provider name
            include_cache_info: Include cache metadata in response

        Returns:
            TopModelsEndpointResult with transformed models data
        """
        try:
            from src.top_models.service import TopModelsService
            from src.top_models.types import top_model_to_api_dict

            svc = TopModelsService(models_cache=self._models_cache)
            result = await svc.get_top_models(limit=limit, refresh=refresh, provider=provider)

            models = [top_model_to_api_dict(m) for m in result.models]

            # Extract unique providers and sub-providers
            providers_raw = [
                m.get("provider") for m in models if isinstance(m.get("provider"), str)
            ]
            providers: list[str] = sorted({p for p in providers_raw if isinstance(p, str)})

            sub_providers_raw = [
                m.get("sub_provider") for m in models if isinstance(m.get("sub_provider"), str)
            ]
            sub_providers: list[str] = sorted({p for p in sub_providers_raw if isinstance(p, str)})

            # Build metadata
            meta: dict[str, Any] = {"excluded_rules": list(svc._cfg.exclude)}
            if include_cache_info:
                meta["rankings_file"] = str(svc._cfg.rankings_file)

            return TopModelsEndpointResult(
                status=200,
                content={
                    "object": "top_models",
                    "source": result.source,
                    "last_updated": result.last_updated.isoformat(),
                    "providers": providers,
                    "sub_providers": sub_providers,
                    "models": models,
                    "suggested_aliases": result.aliases,
                    "meta": meta,
                },
            )

        except (
            ImportError,
            ConnectionError,
            asyncio.TimeoutError,
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
        ) as e:
            # Return graceful error response
            logger.debug(f"Top models endpoint failed: {type(e).__name__}: {e}")
            return TopModelsEndpointResult(
                status=500,
                content={
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": f"Failed to fetch top models: {str(e)}",
                    },
                },
            )

    async def execute_with_request(self, request: TopModelsRequest) -> TopModelsEndpointResult:
        """Execute using TopModelsRequest DTO.

        This method provides a cleaner API when using DTOs from the endpoint layer.

        Args:
            request: TopModelsRequest DTO containing all parameters

        Returns:
            TopModelsEndpointResult with transformed models data
        """
        return await self.execute(
            limit=request.limit,
            refresh=request.refresh,
            provider=request.provider,
            include_cache_info=request.include_cache_info,
        )
