"""
Thought Signature Middleware for Google Vertex AI/Gemini

Elegantly handles thought signature persistence for Gemini models to enable
seamless function calling across multi-turn conversations.

The middleware:
1. Extracts thought signatures from Gemini responses (both streaming and non-streaming)
2. Stores them in an in-memory cache
3. Injects them into subsequent requests when conversation history is sent

Based on Google's thought signature documentation:
https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thought-signatures
"""

import logging
import time
from typing import Any

from .base import Middleware, RequestContext, ResponseContext, StreamChunkContext
from .thought_signature_extract import (
    extract_message_from_response,
    extract_reasoning_details,
    extract_tool_call_ids,
)
from .thought_signature_store import ThoughtSignatureEntry, ThoughtSignatureStore

logger = logging.getLogger(__name__)


class ThoughtSignatureMiddleware(Middleware):
    """Middleware for handling Google Gemini thought signatures."""

    def __init__(self, store: ThoughtSignatureStore | None = None):
        self.store = store or ThoughtSignatureStore()
        self.logger = logging.getLogger(f"{__name__}.ThoughtSignatureMiddleware")

    @property
    def name(self) -> str:
        return "ThoughtSignature"

    async def initialize(self) -> None:
        await self.store.start()
        self.logger.info("Thought signature middleware initialized")

    async def cleanup(self) -> None:
        await self.store.stop()
        self.logger.info("Thought signature middleware cleaned up")

    async def should_handle(self, provider: str, model: str) -> bool:
        model_lower = model.lower()
        handles = "gemini" in model_lower
        self.logger.debug(f"should_handle: provider={provider}, model={model}, handles={handles}")
        return handles

    async def before_request(self, context: RequestContext) -> RequestContext:
        messages = context.messages
        if not messages:
            return context

        modified = False
        for i, message in enumerate(messages):
            if (
                message.get("role") == "assistant"
                and "tool_calls" in message
                and message["tool_calls"]
            ):
                tool_call_ids = {
                    tc.get("id") for tc in message["tool_calls"] if tc.get("id")
                }
                if not tool_call_ids:
                    continue

                reasoning_details = await self.store.retrieve_by_tool_calls(
                    tool_call_ids,
                    conversation_id=context.conversation_id or "default",
                )
                if reasoning_details:
                    new_message = message.copy()
                    new_message["reasoning_details"] = reasoning_details
                    messages[i] = new_message
                    modified = True

        if modified:
            return context.with_updates(messages=messages)
        return context

    async def after_response(self, context: ResponseContext) -> ResponseContext:
        if context.is_streaming:
            return context

        await self._extract_and_store(response=context.response, request_context=context.request_context)
        return context

    async def on_stream_chunk(self, context: StreamChunkContext) -> StreamChunkContext:
        if context.delta and "reasoning_details" in context.delta:
            reasoning_details = context.delta["reasoning_details"]
            if reasoning_details:
                current_details = context.accumulated_metadata.get("reasoning_details", [])
                current_details.extend(reasoning_details)
                context.accumulated_metadata["reasoning_details"] = current_details

        if context.delta and "tool_calls" in context.delta:
            tool_calls = context.delta["tool_calls"]
            if tool_calls:
                current_ids = context.accumulated_metadata.get("tool_call_ids", set())
                for tool_call in tool_calls:
                    if tool_call.get("id"):
                        current_ids.add(tool_call["id"])
                context.accumulated_metadata["tool_call_ids"] = current_ids

        return context

    async def on_stream_complete(self, context: RequestContext, metadata: dict[str, Any]) -> None:
        reasoning_details = metadata.get("reasoning_details", [])
        tool_call_ids = metadata.get("tool_call_ids", set())

        if reasoning_details and tool_call_ids:
            mock_response = {
                "reasoning_details": reasoning_details,
                "tool_calls": [{"id": tc_id} for tc_id in tool_call_ids],
            }
            await self._extract_and_store(response=mock_response, request_context=context)

    async def _extract_and_store(self, response: dict[str, Any], request_context: RequestContext) -> None:
        message = extract_message_from_response(response)
        reasoning_details = extract_reasoning_details(message)
        if not reasoning_details:
            return

        tool_call_ids = extract_tool_call_ids(message)
        if not tool_call_ids:
            return

        message_id = f"msg_{request_context.request_id}_{int(time.time() * 1000)}"

        entry = ThoughtSignatureEntry(
            message_id=message_id,
            reasoning_details=reasoning_details,
            tool_call_ids=frozenset(tool_call_ids),
            timestamp=time.time(),
            conversation_id=request_context.conversation_id or "default",
            provider=request_context.provider,
            model=request_context.model,
        )

        await self.store.store(entry)
