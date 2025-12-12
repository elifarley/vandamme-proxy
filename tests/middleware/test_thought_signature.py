"""
Comprehensive tests for Thought Signature Middleware

Tests cover:
- Thought signature extraction from responses
- Injection into requests with conversation history
- Cache management and cleanup
- Edge cases and error handling
- Streaming support
"""

import asyncio
import time

import pytest

from src.middleware.base import RequestContext, ResponseContext, StreamChunkContext
from src.middleware.thought_signature import (
    ThoughtSignatureEntry,
    ThoughtSignatureMiddleware,
    ThoughtSignatureStore,
)


@pytest.fixture
def mock_store():
    """Create a mock thought signature store for testing."""
    return ThoughtSignatureStore(max_size=10, ttl_seconds=1.0, cleanup_interval=0.1)


@pytest.fixture
def large_store():
    """Create a larger mock store for concurrent tests."""
    return ThoughtSignatureStore(max_size=100, ttl_seconds=1.0, cleanup_interval=0.1)


@pytest.fixture
def middleware(mock_store):
    """Create thought signature middleware with mock store."""
    return ThoughtSignatureMiddleware(store=mock_store)


@pytest.mark.unit
class TestThoughtSignatureStore:
    """Test the ThoughtSignatureStore implementation."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, mock_store):
        """Test storing and retrieving thought signatures."""
        # Create test entry
        tool_call_ids = {"tool_1", "tool_2"}
        reasoning_details = [
            {"thought_signature": "signature_1", "data": "test_data_1"},
            {"thought_signature": "signature_2", "data": "test_data_2"},
        ]

        entry = ThoughtSignatureEntry(
            message_id="msg_123",
            reasoning_details=reasoning_details,
            tool_call_ids=frozenset(tool_call_ids),
            timestamp=time.time(),
            conversation_id="conv_1",
            provider="vertex",
            model="gemini-3-pro",
        )

        # Store the entry
        await mock_store.store(entry)

        # Retrieve by tool call IDs
        retrieved = await mock_store.retrieve_by_tool_calls(tool_call_ids)
        assert retrieved is not None
        assert len(retrieved) == 2
        assert retrieved[0]["thought_signature"] == "signature_1"

        # Retrieve partial match (should return None)
        partial = await mock_store.retrieve_by_tool_calls({"tool_3"})
        assert partial is None

    @pytest.mark.asyncio
    async def test_retrieve_by_conversation(self, mock_store):
        """Test retrieving all entries for a conversation."""
        # Store multiple entries for the same conversation
        for i in range(3):
            entry = ThoughtSignatureEntry(
                message_id=f"msg_{i}",
                reasoning_details=[{"thought_signature": f"signature_{i}"}],
                tool_call_ids=frozenset({f"tool_{i}"}),
                timestamp=time.time(),
                conversation_id="conv_1",
                provider="vertex",
                model="gemini-3-pro",
            )
            await mock_store.store(entry)

        # Retrieve all entries for conversation
        entries = await mock_store.retrieve_by_conversation("conv_1")
        assert len(entries) == 3

        # Retrieve for different conversation
        entries = await mock_store.retrieve_by_conversation("conv_2")
        assert len(entries) == 0

    @pytest.mark.asyncio
    async def test_ttl_cleanup(self, mock_store):
        """Test that entries are cleaned up after TTL expires."""
        # Create entry with old timestamp
        old_timestamp = time.time() - 2.0  # 2 seconds ago (TTL is 1 second)

        entry = ThoughtSignatureEntry(
            message_id="msg_old",
            reasoning_details=[{"thought_signature": "old"}],
            tool_call_ids=frozenset({"tool_old"}),
            timestamp=old_timestamp,
            conversation_id="conv_1",
            provider="vertex",
            model="gemini-3-pro",
        )

        await mock_store.store(entry)

        # Should not be retrievable due to TTL
        retrieved = await mock_store.retrieve_by_tool_calls({"tool_old"})
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_max_size_eviction(self, mock_store):
        """Test that old entries are evicted when max size is reached."""
        # Fill store to capacity
        for i in range(12):  # More than max_size of 10
            entry = ThoughtSignatureEntry(
                message_id=f"msg_{i}",
                reasoning_details=[{"thought_signature": f"signature_{i}"}],
                tool_call_ids=frozenset({f"tool_{i}"}),
                timestamp=time.time() + i,  # Incrementing timestamps
                conversation_id="conv_1",
                provider="vertex",
                model="gemini-3-pro",
            )
            await mock_store.store(entry)

        # Check that oldest entries were evicted
        stats = await mock_store.get_stats()
        assert stats["total_entries"] <= 10

        # Oldest entries should not be retrievable
        old_retrieved = await mock_store.retrieve_by_tool_calls({"tool_0"})
        assert old_retrieved is None

        # Newest entries should still be there
        new_retrieved = await mock_store.retrieve_by_tool_calls({"tool_11"})
        assert new_retrieved is not None

    @pytest.mark.asyncio
    async def test_clear_conversation(self, mock_store):
        """Test clearing all entries for a conversation."""
        # Store entries for multiple conversations
        for conv_id in ["conv_1", "conv_2"]:
            for i in range(2):
                entry = ThoughtSignatureEntry(
                    message_id=f"msg_{conv_id}_{i}",
                    reasoning_details=[{"thought_signature": f"signature_{conv_id}_{i}"}],
                    tool_call_ids=frozenset({f"tool_{conv_id}_{i}"}),
                    timestamp=time.time(),
                    conversation_id=conv_id,
                    provider="vertex",
                    model="gemini-3-pro",
                )
                await mock_store.store(entry)

        # Clear one conversation
        await mock_store.clear_conversation("conv_1")

        # Check that conv_1 entries are gone
        conv_1_entries = await mock_store.retrieve_by_conversation("conv_1")
        assert len(conv_1_entries) == 0

        # Check that conv_2 entries remain
        conv_2_entries = await mock_store.retrieve_by_conversation("conv_2")
        assert len(conv_2_entries) == 2

    @pytest.mark.asyncio
    async def test_concurrent_access(self, large_store):
        """Test thread-safety with concurrent operations."""
        # Start the store
        await large_store.start()

        async def store_entries(start: int, count: int):
            for i in range(count):
                entry = ThoughtSignatureEntry(
                    message_id=f"msg_{start + i}",
                    reasoning_details=[{"thought_signature": f"signature_{start + i}"}],
                    tool_call_ids=frozenset({f"tool_{start + i}"}),
                    timestamp=time.time(),
                    conversation_id=f"conv_{start + i}",
                    provider="vertex",
                    model="gemini-3-pro",
                )
                await large_store.store(entry)

        # Run concurrent store operations
        await asyncio.gather(store_entries(0, 5), store_entries(5, 5), store_entries(10, 5))

        # Verify all entries were stored
        stats = await large_store.get_stats()
        assert stats["total_entries"] == 15

        # Cleanup
        await large_store.stop()

    @pytest.mark.asyncio
    async def test_store_lifecycle(self, mock_store):
        """Test store start/stop lifecycle."""
        await mock_store.start()
        assert mock_store._cleanup_task is not None

        await mock_store.stop()
        assert mock_store._cleanup_task is None


@pytest.mark.unit
class TestThoughtSignatureMiddleware:
    """Test the ThoughtSignatureMiddleware implementation."""

    @pytest.mark.asyncio
    async def test_should_handle(self, middleware):
        """Test provider detection logic."""
        # Should handle Gemini/Vertex providers
        assert await middleware.should_handle("vertex", "gemini-3-pro")
        assert await middleware.should_handle("google", "gemini-pro")
        assert await middleware.should_handle("openai", "vertex:gemini-3-pro")

        # Should not handle other providers
        assert not await middleware.should_handle("openai", "gpt-4")
        assert not await middleware.should_handle("anthropic", "claude-3")
        assert not await middleware.should_handle("azure", "gpt-4")

    @pytest.mark.asyncio
    async def test_before_request_injection(self, middleware, mock_store):
        """Test injecting thought signatures into requests."""
        # Pre-populate store with thought signatures
        entry = ThoughtSignatureEntry(
            message_id="msg_123",
            reasoning_details=[{"thought_signature": "test_signature", "data": "test"}],
            tool_call_ids=frozenset({"tool_1"}),
            timestamp=time.time(),
            conversation_id="conv_1",
            provider="vertex",
            model="gemini-3-pro",
        )
        await mock_store.store(entry)

        # Create request with conversation history
        messages = [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": "I'll use a tool",
                "tool_calls": [
                    {"id": "tool_1", "type": "function", "function": {"name": "test_tool"}}
                ],
            },
            {"role": "tool", "tool_call_id": "tool_1", "content": "Tool result"},
            {"role": "user", "content": "Continue"},
        ]

        context = RequestContext(
            messages=messages,
            provider="vertex",
            model="gemini-3-pro",
            request_id="req_123",
            conversation_id="conv_1",
        )

        # Process request
        processed = await middleware.before_request(context)

        # Check that thought signatures were injected
        assistant_message = processed.messages[1]
        assert "reasoning_details" in assistant_message
        assert len(assistant_message["reasoning_details"]) == 1
        assert assistant_message["reasoning_details"][0]["thought_signature"] == "test_signature"

    @pytest.mark.asyncio
    async def test_after_response_extraction(self, middleware, mock_store):
        """Test extracting thought signatures from responses."""
        # Create mock response with reasoning details in OpenAI format
        response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "I'll use tools",
                        "tool_calls": [
                            {
                                "id": "tool_123",
                                "type": "function",
                                "function": {"name": "test_func"},
                            }
                        ],
                        "reasoning_details": [
                            {"thought_signature": "response_signature", "data": "response_data"}
                        ],
                    }
                }
            ]
        }

        request_context = RequestContext(
            messages=[], provider="vertex", model="gemini-3-pro", request_id="req_123"
        )

        response_context = ResponseContext(
            response=response, request_context=request_context, is_streaming=False
        )

        # Process response
        await middleware.after_response(response_context)

        # Check that thought signatures were stored
        retrieved = await mock_store.retrieve_by_tool_calls({"tool_123"})
        assert retrieved is not None
        assert len(retrieved) == 1
        assert retrieved[0]["thought_signature"] == "response_signature"

    @pytest.mark.asyncio
    async def test_streaming_accumulation(self, middleware, mock_store):
        """Test accumulating thought signatures from streaming chunks."""
        # Create request context
        request_context = RequestContext(
            messages=[], provider="vertex", model="gemini-3-pro", request_id="req_123"
        )

        # Simulate streaming chunks
        chunks = [
            {"delta": {"reasoning_details": [{"thought_signature": "chunk_1", "data": "data_1"}]}},
            {"delta": {"tool_calls": [{"id": "tool_stream"}]}},
            {"delta": {"reasoning_details": [{"thought_signature": "chunk_2", "data": "data_2"}]}},
        ]

        accumulated_metadata = {}

        # Process chunks
        for chunk in chunks:
            stream_context = StreamChunkContext(
                delta=chunk.get("delta", {}),
                request_context=request_context,
                accumulated_metadata=accumulated_metadata,
                is_complete=False,
            )
            stream_context = await middleware.on_stream_chunk(stream_context)
            accumulated_metadata = stream_context.accumulated_metadata

        # Finalize stream
        await middleware.on_stream_complete(request_context, accumulated_metadata)

        # Check that thought signatures were accumulated and stored
        retrieved = await mock_store.retrieve_by_tool_calls({"tool_stream"})
        assert retrieved is not None
        assert len(retrieved) == 2
        assert retrieved[0]["thought_signature"] == "chunk_1"
        assert retrieved[1]["thought_signature"] == "chunk_2"

    @pytest.mark.asyncio
    async def test_no_processing_when_disabled(self):
        """Test that middleware doesn't process when disabled."""
        # Create middleware with disabled store
        disabled_middleware = ThoughtSignatureMiddleware(store=ThoughtSignatureStore())

        # Create request that would normally be processed
        messages = [{"role": "assistant", "tool_calls": [{"id": "tool_1"}]}]

        context = RequestContext(
            messages=messages, provider="vertex", model="gemini-3-pro", request_id="req_123"
        )

        # Process should not modify request
        processed = await disabled_middleware.before_request(context)
        assert processed == context

        # Response should not be processed
        response = {"tool_calls": [{"id": "tool_1"}], "reasoning_details": []}
        response_context = ResponseContext(
            response=response, request_context=context, is_streaming=False
        )

        await disabled_middleware.after_response(response_context)

        # Store should be empty
        stats = await disabled_middleware.store.get_stats()
        assert stats["total_entries"] == 0

    @pytest.mark.asyncio
    async def test_malformed_data_handling(self, middleware):
        """Test handling of malformed data."""
        # Test response without reasoning details
        response = {
            "tool_calls": [{"id": "tool_1"}]
            # Missing reasoning_details
        }

        request_context = RequestContext(
            messages=[], provider="vertex", model="gemini-3-pro", request_id="req_123"
        )

        response_context = ResponseContext(
            response=response, request_context=request_context, is_streaming=False
        )

        # Should not raise error
        await middleware.after_response(response_context)

        # Test response without tool calls
        response = {
            "reasoning_details": [{"thought_signature": "test"}]
            # Missing tool_calls
        }

        response_context = ResponseContext(
            response=response, request_context=request_context, is_streaming=False
        )

        # Should not raise error
        await middleware.after_response(response_context)

    @pytest.mark.asyncio
    async def test_initialize_and_cleanup(self, middleware):
        """Test middleware lifecycle."""
        # Initialize
        await middleware.initialize()
        assert middleware.store is not None

        # Cleanup
        await middleware.cleanup()
        # Store should be stopped

    @pytest.mark.asyncio
    async def test_concurrent_processing(self, middleware, mock_store):
        """Test concurrent request/response processing."""

        async def process_request(i: int):
            messages = [{"role": "assistant", "tool_calls": [{"id": f"tool_{i}"}]}]

            context = RequestContext(
                messages=messages, provider="vertex", model="gemini-3-pro", request_id=f"req_{i}"
            )

            return await middleware.before_request(context)

        async def process_response(i: int):
            response = {
                "tool_calls": [{"id": f"tool_{i}"}],
                "reasoning_details": [{"thought_signature": f"sig_{i}"}],
            }

            request_context = RequestContext(
                messages=[], provider="vertex", model="gemini-3-pro", request_id=f"req_{i}"
            )

            response_context = ResponseContext(
                response=response, request_context=request_context, is_streaming=False
            )

            await middleware.after_response(response_context)

        # Run concurrent operations
        await asyncio.gather(
            *[process_request(i) for i in range(10)], *[process_response(i) for i in range(10)]
        )

        # Verify all responses were stored
        stats = await mock_store.get_stats()
        assert stats["total_entries"] == 10
