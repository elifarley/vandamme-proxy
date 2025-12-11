"""
Thought Signature Middleware for Google Vertex AI/Gemini

Elegantly handles thought signature persistence for Gemini models to enable
seamless function calling across multi-turn conversations.

The middleware:
1. Extracts thought signatures from Gemini responses (both streaming and non-streaming)
2. Stores them in a sophisticated in-memory cache with efficient indexing
3. Injects them into subsequent requests when conversation history is sent

Based on Google's thought signature documentation:
https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thought-signatures
"""

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from typing import Any

from .base import Middleware, RequestContext, ResponseContext, StreamChunkContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ThoughtSignatureEntry:
    """
    Immutable entry for storing thought signature data.

    Associates thought signatures with their corresponding tool calls
    for efficient lookup during injection.
    """

    message_id: str
    reasoning_details: list[dict[str, Any]]
    tool_call_ids: frozenset  # Immutable set for hashability
    timestamp: float
    conversation_id: str
    provider: str
    model: str

    def with_reasoning_details(
        self, reasoning_details: list[dict[str, Any]]
    ) -> "ThoughtSignatureEntry":
        """Create a new entry with updated reasoning details."""
        return ThoughtSignatureEntry(
            message_id=self.message_id,
            reasoning_details=reasoning_details,
            tool_call_ids=self.tool_call_ids,
            timestamp=self.timestamp,
            conversation_id=self.conversation_id,
            provider=self.provider,
            model=self.model,
        )


class ThoughtSignatureStore:
    """
    Sophisticated in-memory store for thought signatures.

    Features:
    - Dual indexing: by message ID and by tool call IDs
    - Automatic TTL-based cleanup with background task
    - Conversation-based isolation
    - Thread-safe operations
    - Memory usage monitoring
    """

    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: float = 3600.0,  # 1 hour
        cleanup_interval: float = 300.0,  # 5 minutes
    ):
        """
        Initialize the store.

        Args:
            max_size: Maximum number of entries to store
            ttl_seconds: Time-to-live for entries in seconds
            cleanup_interval: Interval between cleanup runs
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cleanup_interval = cleanup_interval

        # Primary storage by message ID
        self._entries: dict[str, ThoughtSignatureEntry] = {}

        # Index for efficient lookup by tool call ID
        # Maps: tool_call_id -> set of message_ids
        self._tool_call_index: dict[str, set[str]] = {}

        # Conversation index for bulk operations
        # Maps: conversation_id -> set of message_ids
        self._conversation_index: dict[str, set[str]] = {}

        # Background cleanup task
        self._cleanup_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

        self.logger = logging.getLogger(f"{__name__}.ThoughtSignatureStore")

    async def start(self) -> None:
        """Start the background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            self.logger.debug("Started background cleanup task")

    async def stop(self) -> None:
        """Stop the background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None
            self.logger.debug("Stopped background cleanup task")

    async def store(self, entry: ThoughtSignatureEntry) -> None:
        """
        Store a thought signature entry.

        Args:
            entry: The entry to store
        """
        async with self._lock:
            # Check if we need to evict entries
            if len(self._entries) >= self.max_size:
                await self._evict_oldest()

            # Remove existing entry if updating
            if entry.message_id in self._entries:
                await self._remove_entry(entry.message_id)

            # Store the entry
            self._entries[entry.message_id] = entry

            # Update tool call index
            for tool_call_id in entry.tool_call_ids:
                if tool_call_id not in self._tool_call_index:
                    self._tool_call_index[tool_call_id] = set()
                self._tool_call_index[tool_call_id].add(entry.message_id)

            # Update conversation index
            if entry.conversation_id not in self._conversation_index:
                self._conversation_index[entry.conversation_id] = set()
            self._conversation_index[entry.conversation_id].add(entry.message_id)

            self.logger.debug(
                f"Stored thought signature entry: message_id={entry.message_id}, "
                f"tool_calls={len(entry.tool_call_ids)}, "
                f"conversation_id={entry.conversation_id}, "
                f"total_entries={len(self._entries)}"
            )

    async def retrieve_by_tool_calls(self, tool_call_ids: set[str]) -> list[dict[str, Any]] | None:
        """
        Retrieve reasoning details for a set of tool call IDs.

        Args:
            tool_call_ids: Set of tool call IDs to look up

        Returns:
            Reasoning details if found, None otherwise
        """
        if not tool_call_ids:
            return None

        async with self._lock:
            # Find message IDs that match all tool call IDs
            matching_message_ids = None

            for tool_call_id in tool_call_ids:
                if tool_call_id not in self._tool_call_index:
                    matching_message_ids = None
                    break

                message_ids = self._tool_call_index[tool_call_id]
                if matching_message_ids is None:
                    matching_message_ids = message_ids.copy()
                else:
                    # Intersection - must match all tool calls
                    matching_message_ids &= message_ids
                    if not matching_message_ids:
                        break

            if not matching_message_ids:
                return None

            # Get the first matching entry (there should be at most one)
            message_id = next(iter(matching_message_ids))
            entry = self._entries.get(message_id)

            if entry and self._is_entry_valid(entry):
                self.logger.debug(
                    f"Retrieved thought signatures for message_id={message_id}, tool_calls={len(tool_call_ids)}"
                )
                return entry.reasoning_details

            return None

    async def retrieve_by_conversation(self, conversation_id: str) -> list[ThoughtSignatureEntry]:
        """
        Retrieve all entries for a conversation.

        Args:
            conversation_id: The conversation ID

        Returns:
            List of valid entries for the conversation
        """
        async with self._lock:
            if conversation_id not in self._conversation_index:
                return []

            valid_entries = []
            message_ids = self._conversation_index[conversation_id].copy()

            for message_id in message_ids:
                entry = self._entries.get(message_id)
                if entry and self._is_entry_valid(entry):
                    valid_entries.append(entry)

            return valid_entries

    async def clear_conversation(self, conversation_id: str) -> None:
        """
        Clear all entries for a conversation.

        Args:
            conversation_id: The conversation ID to clear
        """
        async with self._lock:
            if conversation_id not in self._conversation_index:
                return

            message_ids = self._conversation_index[conversation_id].copy()
            for message_id in message_ids:
                await self._remove_entry(message_id)

            self.logger.debug(
                f"Cleared conversation {conversation_id}, cleared_entries={len(message_ids)}"
            )

    async def get_stats(self) -> dict[str, Any]:
        """Get store statistics."""
        async with self._lock:
            return {
                "total_entries": len(self._entries),
                "conversations": len(self._conversation_index),
                "tool_calls": len(self._tool_call_index),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
            }

    async def _remove_entry(self, message_id: str) -> None:
        """Remove an entry and clean up indexes."""
        if message_id not in self._entries:
            return

        entry = self._entries[message_id]
        del self._entries[message_id]

        # Clean up tool call index
        for tool_call_id in entry.tool_call_ids:
            if tool_call_id in self._tool_call_index:
                self._tool_call_index[tool_call_id].discard(message_id)
                if not self._tool_call_index[tool_call_id]:
                    del self._tool_call_index[tool_call_id]

        # Clean up conversation index
        if entry.conversation_id in self._conversation_index:
            self._conversation_index[entry.conversation_id].discard(message_id)
            if not self._conversation_index[entry.conversation_id]:
                del self._conversation_index[entry.conversation_id]

    async def _evict_oldest(self) -> None:
        """Evict the oldest entries to make room."""
        if not self._entries:
            return

        # Sort entries by timestamp and remove the oldest 10%
        sorted_entries = sorted(self._entries.items(), key=lambda x: x[1].timestamp)

        to_evict = max(1, len(sorted_entries) // 10)
        for message_id, _ in sorted_entries[:to_evict]:
            await self._remove_entry(message_id)

        self.logger.debug(f"Evicted {to_evict} oldest entries")

    def _is_entry_valid(self, entry: ThoughtSignatureEntry) -> bool:
        """Check if an entry is still valid (not expired)."""
        return (time.time() - entry.timestamp) < self.ttl_seconds

    async def _cleanup_loop(self) -> None:
        """Background task to periodically clean up expired entries."""
        self.logger.info("Starting cleanup loop")

        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cleanup loop: {e}")

        self.logger.info("Cleanup loop stopped")

    async def _cleanup_expired(self) -> None:
        """Remove expired entries."""
        async with self._lock:
            expired_message_ids = []

            for message_id, entry in self._entries.items():
                if not self._is_entry_valid(entry):
                    expired_message_ids.append(message_id)

            for message_id in expired_message_ids:
                await self._remove_entry(message_id)

            if expired_message_ids:
                self.logger.debug(
                    f"Cleaned up expired entries: count={len(expired_message_ids)}, remaining={len(self._entries)}"
                )


class ThoughtSignatureMiddleware(Middleware):
    """
    Middleware for handling Google Gemini thought signatures.

    Automatically detects Gemini providers and manages thought signatures
    to enable seamless function calling across conversations.
    """

    def __init__(self, store: ThoughtSignatureStore | None = None):
        """
        Initialize the middleware.

        Args:
            store: Optional custom store. If not provided, creates a default one.
        """
        self.store = store or ThoughtSignatureStore()
        self.logger = logging.getLogger(f"{__name__}.ThoughtSignatureMiddleware")

    @property
    def name(self) -> str:
        return "ThoughtSignature"

    async def initialize(self) -> None:
        """Initialize the middleware."""
        await self.store.start()
        self.logger.info("Thought signature middleware initialized")

    async def cleanup(self) -> None:
        """Cleanup resources."""
        await self.store.stop()
        self.logger.info("Thought signature middleware cleaned up")

    async def should_handle(self, provider: str, model: str) -> bool:
        """
        Determine if this middleware should handle the request.

        The middleware handles any request for a model with "gemini" in the name,
        regardless of which provider is serving it.

        This elegant approach allows any provider (Poe, Vertex AI, etc.) to serve
        Gemini models while automatically getting thought signature support.
        """
        model_lower = model.lower()

        # Handle any model with "gemini" in the name
        # This covers gemini-1.5-pro, gemini-3-pro, claude-3-gemini, etc.
        handles = "gemini" in model_lower

        self.logger.debug(f"should_handle: provider={provider}, model={model}, handles={handles}")

        return handles

    async def before_request(self, context: RequestContext) -> RequestContext:
        """
        Inject thought signatures into request messages.

        Scans conversation history for assistant messages with tool calls
        and injects stored thought signatures.

        Args:
            context: The request context

        Returns:
            Context with thought signatures injected
        """
        self.logger.debug(
            f"before_request: conversation_id={context.conversation_id}, provider={context.provider}, model={context.model}, messages={len(context.messages)}"
        )

        messages = context.messages
        if not messages:
            return context

        modified = False
        injected_count = 0

        # Process each message
        for i, message in enumerate(messages):
            # Only process assistant messages with tool calls
            if (
                message.get("role") == "assistant"
                and "tool_calls" in message
                and message["tool_calls"]
            ):
                # Extract tool call IDs
                tool_call_ids = {tc.get("id") for tc in message["tool_calls"] if tc.get("id")}

                if tool_call_ids:
                    # Retrieve thought signatures
                    reasoning_details = await self.store.retrieve_by_tool_calls(tool_call_ids)

                    if reasoning_details:
                        # Create new message with reasoning details
                        new_message = message.copy()
                        new_message["reasoning_details"] = reasoning_details
                        messages[i] = new_message
                        modified = True
                        injected_count += 1

                        self.logger.debug(
                            f"Injected thought signatures: message_index={i}, tool_calls={len(tool_call_ids)}, reasoning_blocks={len(reasoning_details)}"
                        )

        if modified:
            self.logger.info(
                f"Injected thought signatures into request: conversation_id={context.conversation_id}, injected_messages={injected_count}, total_messages={len(messages)}"
            )
            return context.with_updates(messages=messages)

        return context

    async def after_response(self, context: ResponseContext) -> ResponseContext:
        """
        Extract thought signatures from response.

        Processes non-streaming responses and stores thought signatures
        for future injection.

        Args:
            context: The response context

        Returns:
            Unmodified response context
        """
        self.logger.debug(
            f"after_response: conversation_id={context.request_context.conversation_id}, is_streaming={context.is_streaming}, response_keys={list(context.response.keys()) if context.response else []}"
        )

        if context.is_streaming:
            return context

        await self._extract_and_store(
            response=context.response, request_context=context.request_context
        )

        return context

    async def on_stream_chunk(self, context: StreamChunkContext) -> StreamChunkContext:
        """
        Process streaming chunk for thought signatures.

        Accumulates reasoning details across streaming chunks
        and stores them when the stream completes.

        Args:
            context: The stream chunk context

        Returns:
            Unmodified stream chunk context
        """
        # Check if this chunk has reasoning details
        if context.delta and "reasoning_details" in context.delta:
            reasoning_details = context.delta["reasoning_details"]
            if reasoning_details:
                # Accumulate reasoning details
                current_details = context.accumulated_metadata.get("reasoning_details", [])
                current_details.extend(reasoning_details)
                context.accumulated_metadata["reasoning_details"] = current_details

                self.logger.debug(
                    f"Accumulated reasoning details from stream: chunk_blocks={len(reasoning_details)}, total_blocks={len(current_details)}"
                )

        # Track tool call IDs
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
        """
        Store accumulated thought signatures from streaming.

        Called when streaming response is complete to store
        the accumulated reasoning details.

        Args:
            context: The original request context
            metadata: Accumulated metadata from streaming
        """
        reasoning_details = metadata.get("reasoning_details", [])
        tool_call_ids = metadata.get("tool_call_ids", set())

        if reasoning_details and tool_call_ids:
            # Create a mock response for storage
            mock_response = {
                "reasoning_details": reasoning_details,
                "tool_calls": [{"id": tc_id} for tc_id in tool_call_ids],
            }

            await self._extract_and_store(response=mock_response, request_context=context)

            self.logger.info(
                f"Stored thought signatures from streaming response: conversation_id={context.conversation_id}, reasoning_blocks={len(reasoning_details)}, tool_calls={len(tool_call_ids)}"
            )

    async def _extract_and_store(
        self, response: dict[str, Any], request_context: RequestContext
    ) -> None:
        """
        Extract thought signatures from response and store them.

        Args:
            response: The response to process
            request_context: The original request context
        """
        self.logger.debug(
            f"_extract_and_store: response_keys={list(response.keys())}, conversation_id={request_context.conversation_id}"
        )

        # Handle OpenAI response format
        message = None
        if "choices" in response and response["choices"]:
            message = response["choices"][0].get("message", {})
            self.logger.debug("_extract_and_store: Found OpenAI format with choices")
        elif "message" in response:
            # Direct message format
            message = response["message"]
            self.logger.debug("_extract_and_store: Found direct message format")
        else:
            # Flat response format
            message = response
            self.logger.debug("_extract_and_store: Using flat response format")

        # Extract reasoning details
        reasoning_details = message.get("reasoning_details", [])
        self.logger.debug(f"_extract_and_store: reasoning_details found={len(reasoning_details)}")

        if not reasoning_details:
            self.logger.debug("_extract_and_store: No reasoning_details found in response")
            return

        # Extract tool calls
        tool_calls = message.get("tool_calls", [])
        if not tool_calls:
            return

        # Extract tool call IDs
        tool_call_ids = {tc.get("id") for tc in tool_calls if tc.get("id")}

        if not tool_call_ids:
            return

        # Generate unique message ID
        message_id = f"msg_{request_context.request_id}_{int(time.time() * 1000)}"

        # Create entry
        entry = ThoughtSignatureEntry(
            message_id=message_id,
            reasoning_details=reasoning_details,
            tool_call_ids=frozenset(tool_call_ids),
            timestamp=time.time(),
            conversation_id=request_context.conversation_id or "default",
            provider=request_context.provider,
            model=request_context.model,
        )

        # Store the entry
        await self.store.store(entry)

        self.logger.info(
            f"Stored thought signatures from response: message_id={message_id}, conversation_id={request_context.conversation_id}, reasoning_blocks={len(reasoning_details)}, tool_calls={len(tool_call_ids)}"
        )
