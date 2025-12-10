"""Anthropic API client for direct passthrough mode.

This client provides an interface compatible with OpenAIClient but
bypasses all format conversions when talking to Anthropic-compatible APIs.
"""

import asyncio
import hashlib
import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from fastapi import HTTPException

from src.core.logging import LOG_REQUEST_METRICS, conversation_logger
from src.models.claude import ClaudeMessagesRequest


class AnthropicClient:
    """Client for Anthropic-compatible APIs with passthrough mode."""

    def __init__(
        self,
        api_key: Optional[str],  # Can be None for passthrough providers
        base_url: str,
        timeout: int = 90,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """Initialize Anthropic client."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.custom_headers = custom_headers or {}
        self.default_api_key = api_key

        # Don't create HTTP client yet - we'll create it per request
        # This allows us to use different API keys per request
        self._client_cache: Dict[str, httpx.AsyncClient] = {}

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
        request: Dict[str, Any],
        request_id: Optional[str] = None,
        api_key: Optional[str] = None  # Override API key for this request
    ) -> Dict[str, Any]:
        """Send chat completion to Anthropic API with passthrough."""
        start_time = time.time()

        # Use provided API key or fall back to default
        effective_api_key = api_key or self.default_api_key

        if not effective_api_key:
            raise ValueError("No API key available for request")

        # Get client for this specific API key
        client = self._get_client(effective_api_key)

        # Log the request with API key hash
        if LOG_REQUEST_METRICS:
            key_hash = hashlib.sha256(effective_api_key.encode()).hexdigest()[:8]
            conversation_logger.debug(
                f"🔑 API KEY HASH {key_hash} @ {self.base_url}"
            )
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
            response_data: Dict[str, Any] = response.json()

            # Log timing
            if LOG_REQUEST_METRICS:
                duration_ms = (time.time() - start_time) * 1000
                conversation_logger.debug(f"📥 ANTHROPIC RESPONSE | Duration: {duration_ms:.0f}ms")

            return response_data

        except httpx.HTTPStatusError as e:
            # Convert HTTP errors to our format
            try:
                error_detail = e.response.json()
            except Exception:
                try:
                    error_detail = e.response.text
                except Exception:
                    error_detail = str(e)
            raise HTTPException(status_code=e.response.status_code, detail=error_detail)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Anthropic API error: {str(e)}")

    async def create_chat_completion_stream(
        self,
        request: Dict[str, Any],
        request_id: Optional[str] = None,
        api_key: Optional[str] = None  # Override API key for this request
    ) -> AsyncGenerator[str, None]:
        """Send streaming chat completion to Anthropic API with SSE passthrough."""
        start_time = time.time()

        # Use provided API key or fall back to default
        effective_api_key = api_key or self.default_api_key

        if not effective_api_key:
            raise ValueError("No API key available for request")

        # Get client for this specific API key
        client = self._get_client(effective_api_key)

        if LOG_REQUEST_METRICS:
            key_hash = hashlib.sha256(effective_api_key.encode()).hexdigest()[:8]
            conversation_logger.debug(
                f"🔑 API KEY HASH {key_hash} @ {self.base_url}"
            )
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

                # Send final event
                yield "data: [DONE]"

        except httpx.HTTPStatusError as e:
            # For streaming responses, we need to read the content first
            try:
                content = await e.response.read()
                error_detail = json.loads(content.decode('utf-8')) if content else str(e)
            except Exception:
                error_detail = str(e)
            raise HTTPException(status_code=e.response.status_code, detail=error_detail)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Anthropic API streaming error: {str(e)}")

    def classify_openai_error(self, error_message: str) -> str:
        """Classify error message for Anthropic API (passthrough)."""
        # For Anthropic-compatible APIs, we don't need to map error types
        # Just return the error as-is since it should be in Claude format already
        return error_message
