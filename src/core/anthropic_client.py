"""Anthropic API client for direct passthrough mode.

This client provides an interface compatible with OpenAIClient but
bypasses all format conversions when talking to Anthropic-compatible APIs.
"""

import asyncio
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
        api_key: str,
        base_url: str,
        timeout: int = 90,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """Initialize Anthropic client."""
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.custom_headers = custom_headers or {}

        # Build base headers
        self.headers = {
            "x-api-key": api_key,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        # Add custom headers
        self.headers.update(self.custom_headers)

        # Create HTTP client
        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers=self.headers,
        )

    async def create_chat_completion(
        self, request: Dict[str, Any], request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send chat completion to Anthropic API with passthrough."""
        start_time = time.time()

        # Log the request
        if LOG_REQUEST_METRICS:
            conversation_logger.debug(f"📤 ANTHROPIC REQUEST | Model: {request.get('model', 'unknown')}")

        try:
            # Direct API call to Anthropic-compatible endpoint
            response = await self.client.post(
                f"{self.base_url}/v1/messages",
                json=request,
            )

            response.raise_for_status()

            # Parse response
            response_data = response.json()

            # Log timing
            if LOG_REQUEST_METRICS:
                duration_ms = (time.time() - start_time) * 1000
                conversation_logger.debug(f"📥 ANTHROPIC RESPONSE | Duration: {duration_ms:.0f}ms")

            return response_data

        except httpx.HTTPStatusError as e:
            # Convert HTTP errors to our format
            error_detail = e.response.json() if e.response.text else str(e)
            raise HTTPException(
                status_code=e.response.status_code,
                detail=error_detail
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Anthropic API error: {str(e)}"
            )

    async def create_chat_completion_stream(
        self,
        request: Dict[str, Any],
        request_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Send streaming chat completion to Anthropic API with SSE passthrough."""
        start_time = time.time()

        if LOG_REQUEST_METRICS:
            conversation_logger.debug(f"📤 ANTHROPIC STREAM | Model: {request.get('model', 'unknown')}")

        try:
            async with self.client.stream(
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
            error_detail = e.response.json() if e.response.text else str(e)
            raise HTTPException(
                status_code=e.response.status_code,
                detail=error_detail
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Anthropic API streaming error: {str(e)}"
            )

    def classify_openai_error(self, error_message: str) -> str:
        """Classify error message for Anthropic API (passthrough)."""
        # For Anthropic-compatible APIs, we don't need to map error types
        # Just return the error as-is since it should be in Claude format already
        return error_message