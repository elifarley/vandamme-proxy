import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, cast

from fastapi import HTTPException
from openai import AsyncAzureOpenAI, AsyncOpenAI
from openai._exceptions import APIError, AuthenticationError, BadRequestError, RateLimitError

from src.core.config import config
from src.core.logging import ConversationLogger

LOG_REQUEST_METRICS = config.log_request_metrics
conversation_logger = ConversationLogger.get_logger()
logger = logging.getLogger(__name__)

NextApiKey = Callable[[set[str]], Awaitable[str]]


def _is_key_rotation_error(exc: HTTPException) -> bool:
    # HTTP status based triggers
    if exc.status_code in (401, 403, 429):
        return True
    # Content based triggers (quota signals often surface as 400/402/403 depending on provider)
    detail = str(exc.detail).lower()
    return "insufficient_quota" in detail


class OpenAIClient:
    """Async OpenAI client with cancellation support and per-request API key capability."""

    def __init__(
        self,
        api_key: str | None,  # Can be None for passthrough providers
        base_url: str,
        timeout: int = 90,
        api_version: str | None = None,
        custom_headers: dict[str, str] | None = None,
    ):
        self.base_url = base_url
        self.custom_headers = custom_headers or {}
        self.api_version = api_version
        self.timeout = timeout

        # Store default API key but allow None for passthrough
        self.default_api_key = api_key

        # Don't initialize the client yet - we'll create it per request
        # This allows us to use different API keys per request
        self._client_cache: dict[str, AsyncOpenAI | AsyncAzureOpenAI] = {}
        self.active_requests: dict[str, asyncio.Event] = {}

    def _get_client(self, api_key: str) -> AsyncOpenAI | AsyncAzureOpenAI:
        """Get or create a client for the specific API key"""
        # Use cache to avoid recreating clients for the same API key
        if api_key not in self._client_cache:
            # Prepare default headers
            default_headers = {
                "Content-Type": "application/json",
                "User-Agent": "claude-proxy/1.0.0",
            }

            # Merge custom headers with default headers
            all_headers = {**default_headers, **self.custom_headers}

            # Detect if using Azure and instantiate the appropriate client
            if self.api_version:
                self._client_cache[api_key] = AsyncAzureOpenAI(
                    api_key=api_key,
                    azure_endpoint=self.base_url,
                    api_version=self.api_version,
                    timeout=self.timeout,
                    default_headers=all_headers,
                )
            else:
                self._client_cache[api_key] = AsyncOpenAI(
                    api_key=api_key,
                    base_url=self.base_url,
                    timeout=self.timeout,
                    default_headers=all_headers,
                )

        return self._client_cache[api_key]

    async def create_chat_completion(
        self,
        request: dict[str, Any],
        request_id: str | None = None,
        api_key: str | None = None,  # Override API key for this request
        next_api_key: NextApiKey | None = None,  # async callable to rotate provider keys
    ) -> dict[str, Any]:
        """Send chat completion to OpenAI API with cancellation support."""

        api_start = time.time()

        # Get request metrics for updating
        # Metrics are updated in request-scoped layers (API endpoints / converters).
        metrics = None

        async def attempt_with_key(effective_api_key: str) -> dict[str, Any]:
            # Get client for this specific API key
            client = self._get_client(effective_api_key)

            # Create cancellation token if request_id provided
            if request_id:
                cancel_event = asyncio.Event()
                self.active_requests[request_id] = cancel_event

            # Log API call start
            if LOG_REQUEST_METRICS:
                model_name = request.get("model", "unknown")
                timeout = client.timeout
                conversation_logger.debug(f"📡 API CALL | Model: {model_name} | Timeout: {timeout}")

            # Create task that can be cancelled
            completion_task = asyncio.create_task(client.chat.completions.create(**request))

            if request_id:
                # Wait for either completion or cancellation
                cancel_task = asyncio.create_task(cancel_event.wait())
                done, pending = await asyncio.wait(
                    [completion_task, cancel_task], return_when=asyncio.FIRST_COMPLETED
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

                # Check if request was cancelled
                if cancel_task in done:
                    completion_task.cancel()
                    if LOG_REQUEST_METRICS and metrics:
                        metrics.error = "Request cancelled by client"
                        metrics.error_type = "cancelled"
                    raise HTTPException(status_code=499, detail="Request cancelled by client")

                completion = await completion_task
            else:
                completion = await completion_task

            # Log API call timing
            api_duration_ms = (time.time() - api_start) * 1000
            if LOG_REQUEST_METRICS:
                conversation_logger.debug(f"📡 API RESPONSE | Duration: {api_duration_ms:.0f}ms")

            # Debug: Log completion object before conversion
            if LOG_REQUEST_METRICS:
                conversation_logger.debug(f"📡 RAW RESPONSE TYPE: {type(completion)}")
                conversation_logger.debug(f"📡 RAW RESPONSE: {completion}")

            # Convert to dict format that matches the original interface
            response_dict = completion.model_dump()

            # Debug: Log converted response
            if LOG_REQUEST_METRICS:
                conversation_logger.debug(f"📡 CONVERTED RESPONSE TYPE: {type(response_dict)}")

            return cast(dict[str, Any], response_dict)

        # Use provided API key or fall back to default
        effective_api_key = api_key or self.default_api_key

        if not effective_api_key:
            raise ValueError("No API key available for request")

        attempted_keys: set[str] = set()
        while True:
            attempted_keys.add(effective_api_key)
            try:
                return await attempt_with_key(effective_api_key)
            except AuthenticationError as e:
                if LOG_REQUEST_METRICS and metrics:
                    metrics.error = "Authentication failed"
                    metrics.error_type = "auth_error"
                exc = HTTPException(status_code=401, detail=self.classify_openai_error(str(e)))
            except RateLimitError as e:
                if LOG_REQUEST_METRICS and metrics:
                    metrics.error = "Rate limit exceeded"
                    metrics.error_type = "rate_limit"
                exc = HTTPException(status_code=429, detail=self.classify_openai_error(str(e)))
            except BadRequestError as e:
                if LOG_REQUEST_METRICS and metrics:
                    metrics.error = "Bad request"
                    metrics.error_type = "bad_request"
                exc = HTTPException(status_code=400, detail=self.classify_openai_error(str(e)))
            except APIError as e:
                if LOG_REQUEST_METRICS and metrics:
                    metrics.error = "OpenAI API error"
                    metrics.error_type = "api_error"
                status_code = getattr(e, "status_code", 500)
                exc = HTTPException(
                    status_code=status_code, detail=self.classify_openai_error(str(e))
                )
            except HTTPException as e:
                exc = e
            except Exception as e:
                if LOG_REQUEST_METRICS and metrics:
                    metrics.error = f"Unexpected error: {str(e)}"
                    metrics.error_type = "unexpected_error"
                raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}") from e
            finally:
                if request_id and request_id in self.active_requests:
                    del self.active_requests[request_id]

            if next_api_key is None or not _is_key_rotation_error(exc):
                raise exc

            effective_api_key = await next_api_key(attempted_keys)

            if effective_api_key in attempted_keys:
                # next_api_key should not return an already-attempted key, but guard anyway.
                raise exc

            continue

    async def create_chat_completion_stream(
        self,
        request: dict[str, Any],
        request_id: str | None = None,
        api_key: str | None = None,  # Override API key for this request
        next_api_key: NextApiKey | None = None,  # async callable to rotate provider keys
    ) -> AsyncGenerator[str, None]:
        """Send streaming chat completion to OpenAI API with cancellation support."""

        # Use provided API key or fall back to default
        effective_api_key = api_key or self.default_api_key

        if not effective_api_key:
            raise ValueError("No API key available for request")

        attempted_keys: set[str] = set()

        while True:
            attempted_keys.add(effective_api_key)

            # Get client for this specific API key
            client = self._get_client(effective_api_key)

            # Create cancellation token if request_id provided
            if request_id:
                cancel_event = asyncio.Event()
                self.active_requests[request_id] = cancel_event

            try:
                # Ensure stream is enabled
                request["stream"] = True
                if "stream_options" not in request:
                    request["stream_options"] = {}
                request["stream_options"]["include_usage"] = True

                # Create the streaming completion
                streaming_completion = await client.chat.completions.create(**request)

                async for chunk in streaming_completion:
                    # Check for cancellation before yielding each chunk
                    if (
                        request_id
                        and request_id in self.active_requests
                        and self.active_requests[request_id].is_set()
                    ):
                        raise HTTPException(status_code=499, detail="Request cancelled by client")

                    # Convert chunk to SSE format matching original HTTP client format
                    chunk_dict = chunk.model_dump()
                    chunk_json = json.dumps(chunk_dict, ensure_ascii=False)
                    yield f"data: {chunk_json}"

                # Success: exit rotation loop
                yield "data: [DONE]"
                return

            except AuthenticationError as e:
                exc = HTTPException(status_code=401, detail=self.classify_openai_error(str(e)))
            except RateLimitError as e:
                exc = HTTPException(status_code=429, detail=self.classify_openai_error(str(e)))
            except BadRequestError as e:
                exc = HTTPException(status_code=400, detail=self.classify_openai_error(str(e)))
            except APIError as e:
                status_code = getattr(e, "status_code", 500)
                exc = HTTPException(
                    status_code=status_code, detail=self.classify_openai_error(str(e))
                )
            except HTTPException as e:
                exc = e
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}") from e
            finally:
                # Clean up active request tracking
                if request_id and request_id in self.active_requests:
                    del self.active_requests[request_id]

            if next_api_key is None or not _is_key_rotation_error(exc):
                raise exc

            effective_api_key = await next_api_key(attempted_keys)
            if effective_api_key in attempted_keys:
                raise exc

            continue

        # unreachable
        raise HTTPException(status_code=500, detail="Unexpected streaming control flow")

    def classify_openai_error(self, error_detail: Any) -> str:
        """Provide specific error guidance for common OpenAI API issues."""
        error_str = str(error_detail).lower()

        # Region/country restrictions
        if (
            "unsupported_country_region_territory" in error_str
            or "country, region, or territory not supported" in error_str
        ):
            return (
                "OpenAI API is not available in your region. "
                "Consider using a VPN or Azure OpenAI service."
            )

        # API key issues
        if "invalid_api_key" in error_str or "unauthorized" in error_str:
            return "Invalid API key. Please check your OPENAI_API_KEY configuration."

        # Rate limiting
        if "rate_limit" in error_str or "quota" in error_str:
            return "Rate limit exceeded. Please wait and try again, or upgrade your API plan."

        # Model not found
        if "model" in error_str and ("not found" in error_str or "does not exist" in error_str):
            return "Model not found."

        # Billing issues
        if "billing" in error_str or "payment" in error_str:
            return "Billing issue. Please check your OpenAI account billing status."

        # Default: return original message
        return str(error_detail)

    def cancel_request(self, request_id: str) -> bool:
        """Cancel an active request by request_id."""
        if request_id in self.active_requests:
            self.active_requests[request_id].set()
            return True
        return False
