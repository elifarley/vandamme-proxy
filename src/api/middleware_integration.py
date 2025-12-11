"""
Middleware Integration for API Endpoints

Elegant integration layer that connects the middleware system with API endpoints
without intruding into the core endpoint logic.

This module provides:
- Middleware-aware request/response processing
- Transparent streaming support with middleware
- Provider-specific middleware activation
- Minimal performance overhead
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from src.middleware import MiddlewareChain, RequestContext, ResponseContext
from src.middleware.base import StreamChunkContext
from src.models.claude import ClaudeMessagesRequest

logger = logging.getLogger(__name__)


class MiddlewareAwareRequestProcessor:
    """
    Elegant processor that integrates middleware into request/response flow.

    Provides a clean interface for endpoints to use middleware without
    needing to understand the internal middleware architecture.
    """

    def __init__(self) -> None:
        self.middleware_chain = MiddlewareChain()
        self.logger = logging.getLogger(f"{__name__}.MiddlewareAwareRequestProcessor")

    async def initialize(self) -> None:
        """Initialize the middleware chain with provider-specific middlewares."""
        # Register thought signature middleware for Gemini providers
        from src.middleware.thought_signature import ThoughtSignatureMiddleware

        self.middleware_chain.add(ThoughtSignatureMiddleware())

        await self.middleware_chain.initialize()
        self.logger.info("Middleware processor initialized")

    async def cleanup(self) -> None:
        """Cleanup middleware resources."""
        await self.middleware_chain.cleanup()
        self.logger.info("Middleware processor cleaned up")

    async def process_request(
        self,
        request: ClaudeMessagesRequest,
        provider_name: str,
        request_id: str,
        conversation_id: str | None = None,
    ) -> ClaudeMessagesRequest:
        """
        Process request through middleware chain.

        Args:
            request: The Claude request
            provider_name: The target provider
            request_id: Unique request identifier
            conversation_id: Optional conversation identifier

        Returns:
            Processed request (may be modified by middleware)
        """
        # Create request context
        context = RequestContext(
            messages=[msg.model_dump() for msg in request.messages],
            provider=provider_name,
            model=request.model,
            request_id=request_id,
            conversation_id=conversation_id,
            metadata={"original_request": request},
        )

        # Process through middleware chain
        processed_context = await self.middleware_chain.process_request(context)

        # Check if messages were modified
        if processed_context.messages != context.messages:
            # Convert back to Claude request format
            # Note: This is a simplified conversion. In a production system,
            # you'd want to preserve the full message structure
            self.logger.debug(
                f"Request modified by middleware, provider={provider_name}, "
                f"model={request.model}, original_messages={len(context.messages)}, "
                f"modified_messages={len(processed_context.messages)}"
            )

        return request  # Return original for now - full conversion would be more complex

    async def process_response(
        self,
        response: dict[str, Any],
        request_context: RequestContext,
        is_streaming: bool = False,
    ) -> dict[str, Any]:
        """
        Process response through middleware chain.

        Args:
            response: The response from provider
            request_context: The original request context
            is_streaming: Whether this is a streaming response

        Returns:
            Processed response (may be modified by middleware)
        """
        # Create response context
        response_context = ResponseContext(
            response=response, request_context=request_context, is_streaming=is_streaming
        )

        # Process through middleware chain
        processed_context = await self.middleware_chain.process_response(response_context)

        return processed_context.response  # type: ignore[return-value]

    async def process_stream_chunk(
        self,
        chunk: dict[str, Any],
        request_context: RequestContext,
        accumulated_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Process streaming chunk through middleware chain.

        Args:
            chunk: The streaming chunk
            request_context: The original request context
            accumulated_metadata: Metadata accumulated during streaming

        Returns:
            Processed chunk (may be modified by middleware)
        """
        # Create stream chunk context
        stream_context = StreamChunkContext(
            delta=chunk,
            request_context=request_context,
            accumulated_metadata=accumulated_metadata,
            is_complete=False,
        )

        # Process through middleware chain
        processed_context = await self.middleware_chain.process_stream_chunk(stream_context)

        # Update accumulated metadata from middleware
        accumulated_metadata.update(processed_context.accumulated_metadata)

        return processed_context.delta  # type: ignore[return-value]

    async def finalize_stream(
        self,
        request_context: RequestContext,
        accumulated_metadata: dict[str, Any],
    ) -> None:
        """
        Finalize streaming response processing.

        Called when streaming is complete to allow middleware
        to perform any final processing.

        Args:
            request_context: The original request context
            accumulated_metadata: All accumulated metadata from streaming
        """
        # Create final stream chunk context
        final_context = StreamChunkContext(
            delta={},
            request_context=request_context,
            accumulated_metadata=accumulated_metadata,
            is_complete=True,
        )

        # Process through middleware chain to trigger completion handlers
        await self.middleware_chain.process_stream_chunk(final_context)


# Global instance for use across endpoints
_processor_instance: MiddlewareAwareRequestProcessor | None = None


async def get_middleware_processor() -> MiddlewareAwareRequestProcessor:
    """
    Get the global middleware processor instance.

    Returns:
        The middleware processor instance
    """
    global _processor_instance

    if _processor_instance is None:
        _processor_instance = MiddlewareAwareRequestProcessor()
        await _processor_instance.initialize()

    return _processor_instance


async def cleanup_middleware_processor() -> None:
    """Cleanup the global middleware processor."""
    global _processor_instance

    if _processor_instance:
        await _processor_instance.cleanup()
        _processor_instance = None


class MiddlewareStreamingWrapper:
    """
    Elegant wrapper for streaming responses that applies middleware.

    Wraps an existing async generator to apply middleware to each chunk
    without the streaming endpoint needing to know about middleware.
    """

    def __init__(
        self,
        original_stream: AsyncGenerator[str, None],
        request_context: RequestContext,
        processor: MiddlewareAwareRequestProcessor,
    ):
        self.original_stream = original_stream
        self.request_context = request_context
        self.processor = processor
        self.accumulated_metadata: dict[str, Any] = {}
        self.logger = logging.getLogger(f"{__name__}.MiddlewareStreamingWrapper")

    async def __aiter__(self) -> AsyncGenerator[str, None]:
        """Iterate over streaming chunks with middleware applied."""
        try:
            async for chunk in self.original_stream:
                # For now, we just pass through the chunk
                # Full middleware integration would require parsing SSE format
                # and extracting JSON deltas for processing
                yield chunk

            # Finalize stream processing
            await self.processor.finalize_stream(self.request_context, self.accumulated_metadata)

        except Exception as e:
            self.logger.error(f"Error in middleware streaming wrapper: {e}")
            raise
