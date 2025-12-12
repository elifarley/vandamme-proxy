"""
Tests for middleware base infrastructure

Tests cover:
- Middleware chain execution
- Request/Response context handling
- Middleware selection and ordering
- Error handling
"""

import pytest

from src.middleware.base import (
    Middleware,
    MiddlewareChain,
    RequestContext,
    ResponseContext,
    StreamChunkContext,
)


class MockMiddleware(Middleware):
    """Mock middleware for testing."""

    def __init__(
        self,
        name: str,
        should_handle: bool = True,
        modify_request: bool = False,
        modify_response: bool = False,
    ):
        self._name = name
        self._should_handle = should_handle
        self._modify_request = modify_request
        self._modify_response = modify_response
        self.initialized = False
        self.cleaned_up = False

    @property
    def name(self) -> str:
        return self._name

    async def should_handle(self, provider: str, model: str) -> bool:
        # Handle both boolean and callable cases
        if callable(self._should_handle):
            return self._should_handle(provider, model)
        return self._should_handle

    async def before_request(self, context: RequestContext) -> RequestContext:
        if self._modify_request:
            # Add metadata to indicate processing
            metadata = context.metadata.copy()
            metadata[f"processed_by_{self._name}"] = True
            return context.with_updates(metadata=metadata)
        return context

    async def after_response(self, context: ResponseContext) -> ResponseContext:
        if self._modify_response:
            # Add metadata to response
            response = context.response.copy()
            response[f"processed_by_{self._name}"] = True
            return context.with_updates(response=response)
        return context

    async def initialize(self) -> None:
        self.initialized = True

    async def cleanup(self) -> None:
        self.cleaned_up = True

    async def on_stream_complete(self, context: StreamChunkContext) -> None:
        """Handle stream completion."""
        pass


@pytest.mark.unit
class TestRequestContext:
    """Test RequestContext functionality."""

    def test_create_context(self):
        """Test creating a basic request context."""
        messages = [{"role": "user", "content": "Hello"}]
        context = RequestContext(
            messages=messages, provider="openai", model="gpt-4", request_id="req_123"
        )

        assert context.messages == messages
        assert context.provider == "openai"
        assert context.model == "gpt-4"
        assert context.request_id == "req_123"
        assert context.conversation_id is None
        assert context.metadata == {}

    def test_with_updates(self):
        """Test updating context while preserving immutability."""
        original = RequestContext(
            messages=[{"role": "user", "content": "Hello"}], provider="openai", model="gpt-4"
        )

        # Update with new metadata
        updated = original.with_updates(conversation_id="conv_123", metadata={"key": "value"})

        # Original should be unchanged
        assert original.conversation_id is None
        assert original.metadata == {}

        # Updated should have new values
        assert updated.conversation_id == "conv_123"
        assert updated.metadata == {"key": "value"}

        # Other fields should be preserved
        assert updated.provider == original.provider
        assert updated.model == original.model

    def test_with_updates_messages(self):
        """Test updating messages in context."""
        original = RequestContext(
            messages=[{"role": "user", "content": "Hello"}], provider="openai", model="gpt-4"
        )

        # Update messages
        new_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        updated = original.with_updates(messages=new_messages)

        # Messages should be updated
        assert updated.messages == new_messages
        # Original should be unchanged
        assert original.messages == [{"role": "user", "content": "Hello"}]


@pytest.mark.unit
class TestResponseContext:
    """Test ResponseContext functionality."""

    def test_create_context(self):
        """Test creating a basic response context."""
        request_context = RequestContext(messages=[], provider="openai", model="gpt-4")
        response = {"content": "Hello!"}

        context = ResponseContext(response=response, request_context=request_context)

        assert context.response == response
        assert context.request_context == request_context
        assert not context.is_streaming
        assert context.metadata == {}

    def test_with_updates(self):
        """Test updating response context."""
        request_context = RequestContext(messages=[], provider="openai", model="gpt-4")
        original = ResponseContext(response={"content": "Hello!"}, request_context=request_context)

        # Update
        updated = original.with_updates(is_streaming=True, metadata={"stream_id": "123"})

        # Original unchanged
        assert not original.is_streaming
        assert original.metadata == {}

        # Updated has new values
        assert updated.is_streaming
        assert updated.metadata == {"stream_id": "123"}
        # Response preserved
        assert updated.response == original.response


@pytest.mark.unit
class TestStreamChunkContext:
    """Test StreamChunkContext functionality."""

    def test_create_context(self):
        """Test creating stream chunk context."""
        request_context = RequestContext(messages=[], provider="openai", model="gpt-4")
        delta = {"content": "Hello"}

        context = StreamChunkContext(delta=delta, request_context=request_context)

        assert context.delta == delta
        assert context.request_context == request_context
        assert not context.is_complete
        assert context.accumulated_metadata == {}


@pytest.mark.unit
class TestMiddlewareChain:
    """Test MiddlewareChain functionality."""

    @pytest.mark.asyncio
    async def test_empty_chain(self):
        """Test middleware chain with no middlewares."""
        chain = MiddlewareChain()
        await chain.initialize()

        context = RequestContext(messages=[], provider="openai", model="gpt-4")

        # Should return unchanged context
        processed = await chain.process_request(context)
        assert processed == context

        # Response should also be unchanged
        response_context = ResponseContext(response={"content": "Hello"}, request_context=context)
        processed_response = await chain.process_response(response_context)
        assert processed_response == response_context

        await chain.cleanup()

    @pytest.mark.asyncio
    async def test_add_middleware(self):
        """Test adding middleware to chain."""
        chain = MiddlewareChain()
        middleware1 = MockMiddleware("middleware1")
        middleware2 = MockMiddleware("middleware2")

        # Add middlewares
        chain.add(middleware1)
        chain.add(middleware2)

        # Initialize chain
        await chain.initialize()

        # Check middlewares were initialized
        assert middleware1.initialized
        assert middleware2.initialized

        await chain.cleanup()

        # Check middlewares were cleaned up
        assert middleware1.cleaned_up
        assert middleware2.cleaned_up

    @pytest.mark.asyncio
    async def test_process_request_through_middlewares(self):
        """Test processing request through multiple middlewares."""
        chain = MiddlewareChain()

        # Add middlewares that modify request
        chain.add(MockMiddleware("mw1", should_handle=True, modify_request=True))
        chain.add(MockMiddleware("mw2", should_handle=True, modify_request=True))
        chain.add(MockMiddleware("mw3", should_handle=False, modify_request=True))

        await chain.initialize()

        context = RequestContext(
            messages=[], provider="openai", model="gpt-4", metadata={"initial": True}
        )

        # Process request
        processed = await chain.process_request(context)

        # Should have metadata from mw1 and mw2 (mw3 should not handle)
        assert "processed_by_mw1" in processed.metadata
        assert "processed_by_mw2" in processed.metadata
        assert "processed_by_mw3" not in processed.metadata
        # Original metadata preserved
        assert "initial" in processed.metadata

        await chain.cleanup()

    @pytest.mark.asyncio
    async def test_process_response_through_middlewares(self):
        """Test processing response through multiple middlewares."""
        chain = MiddlewareChain()

        # Add middlewares that modify response
        chain.add(MockMiddleware("mw1", should_handle=True, modify_response=True))
        chain.add(MockMiddleware("mw2", should_handle=True, modify_response=True))

        await chain.initialize()

        request_context = RequestContext(messages=[], provider="openai", model="gpt-4")
        response = {"content": "Hello"}

        response_context = ResponseContext(response=response, request_context=request_context)

        # Process response
        processed = await chain.process_response(response_context)

        # Should have modifications from both middlewares
        assert "processed_by_mw1" in processed.response
        assert "processed_by_mw2" in processed.response
        # Original content preserved
        assert "content" in processed.response

        await chain.cleanup()

    @pytest.mark.asyncio
    async def test_provider_specific_handling(self):
        """Test that only applicable middlewares handle requests."""
        chain = MiddlewareChain()

        # Add middlewares for different providers
        chain.add(MockMiddleware("openai_mw", should_handle=False))  # Will handle only OpenAI
        chain.add(MockMiddleware("gemini_mw", should_handle=True))  # Will handle all

        await chain.initialize()

        # Create OpenAI middleware that handles only OpenAI
        openai_mw = chain._middlewares[0]

        def openai_only(p, m):
            return p == "openai"

        openai_mw._should_handle = openai_only

        # Test with OpenAI provider
        RequestContext(messages=[], provider="openai", model="gpt-4")

        # Both should handle OpenAI
        should_handle_openai = [
            await mw.should_handle("openai", "gpt-4") for mw in chain._middlewares
        ]
        assert all(should_handle_openai)

        # Test with Gemini provider
        should_handle_gemini = [
            await mw.should_handle("vertex", "gemini-3-pro") for mw in chain._middlewares
        ]
        assert not should_handle_gemini[0]  # openai_mw should not handle
        assert should_handle_gemini[1]  # gemini_mw should handle

        await chain.cleanup()

    @pytest.mark.asyncio
    async def test_stream_chunk_processing(self):
        """Test processing stream chunks through middleware."""
        chain = MiddlewareChain()
        await chain.initialize()

        request_context = RequestContext(messages=[], provider="openai", model="gpt-4")
        delta = {"content": "Hello"}

        stream_context = StreamChunkContext(delta=delta, request_context=request_context)

        # Process chunk
        processed = await chain.process_stream_chunk(stream_context)

        # Should be unchanged (no modifying middleware)
        assert processed.delta == delta
        assert not processed.is_complete

        # Test completion
        complete_context = StreamChunkContext(
            delta={}, request_context=request_context, is_complete=True
        )
        await chain.process_stream_chunk(complete_context)

        await chain.cleanup()

    @pytest.mark.asyncio
    async def test_middleware_error_handling(self):
        """Test error handling in middleware chain."""

        class ErrorMiddleware(Middleware):
            @property
            def name(self) -> str:
                return "error_mw"

            async def should_handle(self, provider: str, model: str) -> bool:
                return True

            async def before_request(self, context: RequestContext) -> RequestContext:
                raise ValueError("Test error")

            async def after_response(self, context: ResponseContext) -> ResponseContext:
                return context

            async def initialize(self) -> None:
                pass

            async def cleanup(self) -> None:
                pass

            async def on_stream_complete(self, context: StreamChunkContext) -> None:
                pass

        chain = MiddlewareChain()
        chain.add(ErrorMiddleware())
        await chain.initialize()

        context = RequestContext(messages=[], provider="openai", model="gpt-4")

        # Should propagate error
        with pytest.raises(ValueError, match="Test error"):
            await chain.process_request(context)

        await chain.cleanup()

    @pytest.mark.asyncio
    async def test_idempotent_initialization(self):
        """Test that initialize can be called multiple times safely."""
        chain = MiddlewareChain()
        middleware = MockMiddleware("test")
        chain.add(middleware)

        # Initialize multiple times
        await chain.initialize()
        await chain.initialize()
        await chain.initialize()

        # Should only initialize once
        assert middleware.initialized

        await chain.cleanup()

    @pytest.mark.asyncio
    async def test_cleanup_without_initialization(self):
        """Test cleanup without initialization."""
        chain = MiddlewareChain()
        middleware = MockMiddleware("test")
        chain.add(middleware)

        # Cleanup without initialize should be safe
        await chain.cleanup()
        assert not middleware.cleaned_up
