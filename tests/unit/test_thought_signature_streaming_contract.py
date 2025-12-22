import pytest

from src.middleware.base import RequestContext
from src.middleware.thought_signature import ThoughtSignatureMiddleware, ThoughtSignatureStore


@pytest.mark.unit
@pytest.mark.asyncio
async def test_thought_signature_streaming_persists_and_injects_from_middleware_hooks():
    """Contract test for thought signature streaming hooks.

    This is the minimal contract that *must* hold for streaming support:
    - on_stream_complete stores reasoning_details keyed by tool_call_ids
    - before_request injects reasoning_details into the matching assistant message

    NOTE: This uses middleware hooks directly. A separate integration test should
    prove the SSE parsing layer actually produces the deltas needed by
    on_stream_chunk/on_stream_complete.
    """

    store = ThoughtSignatureStore(max_size=10, ttl_seconds=60.0, cleanup_interval=9999.0)
    middleware = ThoughtSignatureMiddleware(store=store)
    await middleware.initialize()

    req_ctx = RequestContext(
        messages=[],
        provider="vertex",
        model="gemini-3-pro",
        request_id="r1",
        conversation_id="conv_1",
    )

    await middleware.on_stream_complete(
        req_ctx,
        metadata={
            "reasoning_details": [{"thought_signature": "sig1", "data": "x"}],
            "tool_call_ids": {"call_123"},
        },
    )

    # Ensure persistence happened
    stored = await store.retrieve_by_tool_calls({"call_123"}, conversation_id="conv_1")
    assert stored == [{"thought_signature": "sig1", "data": "x"}]

    # Ensure injection happens on subsequent request
    next_req = RequestContext(
        messages=[
            {
                "role": "assistant",
                "content": "will call tool",
                "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "t"}}],
            }
        ],
        provider="vertex",
        model="gemini-3-pro",
        request_id="r2",
        conversation_id="conv_1",
    )

    injected_ctx = await middleware.before_request(next_req)
    assert injected_ctx.messages[0]["reasoning_details"] == [{"thought_signature": "sig1", "data": "x"}]

    await middleware.cleanup()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_thought_signature_streaming_metadata_delta_shape_expected_by_middleware():
    """Delta-shape contract for streaming middleware.

    ThoughtSignatureMiddleware.on_stream_chunk currently expects a dict delta with:
    - optional "reasoning_details": list[dict]
    - optional "tool_calls": list[dict] where each has an "id"

    This test ensures the accumulator logic works with the intended shapes.
    """

    store = ThoughtSignatureStore(max_size=10, ttl_seconds=60.0, cleanup_interval=9999.0)
    middleware = ThoughtSignatureMiddleware(store=store)
    await middleware.initialize()

    req_ctx = RequestContext(
        messages=[],
        provider="vertex",
        model="gemini-3-pro",
        request_id="r1",
        conversation_id="conv_1",
    )

    accumulated: dict = {}

    # tool_call id arrives
    from src.middleware.base import StreamChunkContext

    await middleware.on_stream_chunk(
        StreamChunkContext(
            delta={"tool_calls": [{"id": "call_123"}]},
            request_context=req_ctx,
            accumulated_metadata=accumulated,
            is_complete=False,
        )
    )

    # reasoning arrives
    await middleware.on_stream_chunk(
        StreamChunkContext(
            delta={"reasoning_details": [{"thought_signature": "sig1"}]},
            request_context=req_ctx,
            accumulated_metadata=accumulated,
            is_complete=False,
        )
    )

    assert accumulated["tool_call_ids"] == {"call_123"}
    assert accumulated["reasoning_details"] == [{"thought_signature": "sig1"}]

    await middleware.cleanup()
