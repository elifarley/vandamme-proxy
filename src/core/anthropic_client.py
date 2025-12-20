"""Anthropic API client for direct passthrough mode.

This client provides an interface compatible with OpenAIClient but
bypasses all format conversions when talking to Anthropic-compatible APIs.
"""

import hashlib
import json
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

import httpx
from fastapi import HTTPException

from src.core.config import config
from src.core.logging import ConversationLogger

LOG_REQUEST_METRICS = config.log_request_metrics
conversation_logger = ConversationLogger.get_logger()

NextApiKey = Callable[[set[str]], Awaitable[str]]


class AnthropicClient:
    """Client for Anthropic-compatible APIs with passthrough mode."""

    def __init__(
        self,
        api_key: str | None,  # Can be None for passthrough providers
        base_url: str,
        timeout: int = 90,
        custom_headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize Anthropic client."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.custom_headers = custom_headers or {}
        self.default_api_key = api_key

        # Don't create HTTP client yet - we'll create it per request
        # This allows us to use different API keys per request
        self._client_cache: dict[str, httpx.AsyncClient] = {}

    def _get_client(self, api_key: str) -> httpx.AsyncClient:
        """Get or create an HTTP client for the specific API key"""
        if api_key not in self._client_cache:
            # Build headers for this specific API key
            headers = {
                "x-api-key": api_key,
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
                **self.custom_headers,
            }

            # Create HTTP client with these headers
            self._client_cache[api_key] = httpx.AsyncClient(
                timeout=self.timeout,
                headers=headers,
            )

        return self._client_cache[api_key]

    async def create_chat_completion(
        self,
        request: dict[str, Any],
        request_id: str | None = None,
        api_key: str | None = None,  # Override API key for this request
        next_api_key: NextApiKey | None = None,  # async callable to rotate provider keys
    ) -> dict[str, Any]:
        """Send chat completion to Anthropic API with passthrough."""
        start_time = time.time()

        effective_api_key = api_key or self.default_api_key
        if not effective_api_key:
            raise ValueError("No API key available for request")

        attempted_keys: set[str] = set()
        while True:
            attempted_keys.add(effective_api_key)

            # Get client for this specific API key
            client = self._get_client(effective_api_key)

            # Log the request with API key hash
            if LOG_REQUEST_METRICS:
                key_hash = hashlib.sha256(effective_api_key.encode()).hexdigest()[:8]
                conversation_logger.debug(f"🔑 API KEY HASH {key_hash} @ {self.base_url}")
                conversation_logger.debug(
                    f"📤 ANTHROPIC REQUEST | Model: {request.get('model', 'unknown')}"
                )

            try:
                # Direct API call to Anthropic-compatible endpoint
                response = await client.post(
                    f"{self.base_url}/v1/messages",
                    json=request,
                )

                response.raise_for_status()

                # Parse response
                response_data: dict[str, Any] = response.json()

                # Log timing
                if LOG_REQUEST_METRICS:
                    duration_ms = (time.time() - start_time) * 1000
                    conversation_logger.debug(
                        f"📥 ANTHROPIC RESPONSE | Duration: {duration_ms:.0f}ms"
                    )

                return response_data

            except httpx.HTTPStatusError as e:
                try:
                    error_detail = e.response.json()
                except Exception:
                    try:
                        error_detail = e.response.text
                    except Exception:
                        error_detail = str(e)

                exc = HTTPException(status_code=e.response.status_code, detail=error_detail)

            except HTTPException as e:
                exc = e

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Anthropic API error: {str(e)}") from e

            # Rotation decision
            detail = str(getattr(exc, "detail", "")).lower()
            is_key_error = exc.status_code in (401, 403, 429) or "insufficient_quota" in detail
            if next_api_key is None or not is_key_error:
                raise exc

            effective_api_key = await next_api_key(attempted_keys)
            if effective_api_key in attempted_keys:
                raise exc

            continue

    async def create_chat_completion_stream(
        self,
        request: dict[str, Any],
        request_id: str | None = None,
        api_key: str | None = None,  # Override API key for this request
        next_api_key: NextApiKey | None = None,  # async callable to rotate provider keys
    ) -> AsyncGenerator[str, None]:
        """Send streaming chat completion to Anthropic API with SSE passthrough."""

        effective_api_key = api_key or self.default_api_key
        if not effective_api_key:
            raise ValueError("No API key available for request")

        attempted_keys: set[str] = set()
        while True:
            attempted_keys.add(effective_api_key)

            # Get client for this specific API key
            client = self._get_client(effective_api_key)

            if LOG_REQUEST_METRICS:
                key_hash = hashlib.sha256(effective_api_key.encode()).hexdigest()[:8]
                conversation_logger.debug(f"🔑 API KEY HASH {key_hash} @ {self.base_url}")
                conversation_logger.debug(
                    f"📤 ANTHROPIC STREAM | Model: {request.get('model', 'unknown')}"
                )

            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/v1/messages",
                    json=request,
                ) as response:
                    response.raise_for_status()

                    # Pass through SSE events directly
                    async for line in response.aiter_lines():
                        if line.strip():
                            yield f"data: {line}"

                    # Success: end stream and exit rotation loop
                    yield "data: [DONE]"
                    return

            except httpx.HTTPStatusError as e:
                try:
                    content = e.response.read()
                    error_detail = json.loads(content.decode("utf-8")) if content else str(e)
                except Exception:
                    error_detail = str(e)

                exc = HTTPException(status_code=e.response.status_code, detail=error_detail)

            except HTTPException as e:
                exc = e

            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Anthropic API streaming error: {str(e)}"
                ) from e

            # Rotation decision
            detail = str(getattr(exc, "detail", "")).lower()
            is_key_error = exc.status_code in (401, 403, 429) or "insufficient_quota" in detail
            if next_api_key is None or not is_key_error:
                raise exc

            effective_api_key = await next_api_key(attempted_keys)
            if effective_api_key in attempted_keys:
                raise exc

            continue

        raise HTTPException(status_code=500, detail="Unexpected streaming control flow")

    def classify_openai_error(self, error_message: str) -> str:
        """Classify error message for Anthropic API (passthrough)."""
        # For Anthropic-compatible APIs, we don't need to map error types
        # Just return the error as-is since it should be in Claude format already
        return error_message
