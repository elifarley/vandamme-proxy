# tests/middleware/test_thought_signature_openai_format.py
"""Test thought signature injection in OpenAI-compatible format.

Tests that thought signatures are injected in the correct format for Google's
OpenAI compatibility mode: extra_content.google.thought_signature on tool_calls.

Reference: https://ai.google.dev/gemini-api/docs/thought-signatures
"""

import time

import pytest

from src.middleware.base import RequestContext
from src.middleware.thought_signature import (
    ThoughtSignatureEntry,
    ThoughtSignatureMiddleware,
    ThoughtSignatureStore,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_thought_signature_injection_uses_openai_format():
    """Thought signatures should be injected as extra_content.google.thought_signature."""
    store = ThoughtSignatureStore(max_size=100, ttl_seconds=3600)
    middleware = ThoughtSignatureMiddleware(store=store)

    # First, store a thought signature (simulating response from first request)
    # Using the current dataclass structure with reasoning_details
    entry = ThoughtSignatureEntry(
        message_id="msg_test",
        reasoning_details=[{"thought_signature": "sig_abc123"}],
        tool_call_ids=frozenset(["call_123"]),
        timestamp=time.time(),
        conversation_id="conv_1",
        provider="gemini",
        model="gemini-3-pro",
    )
    await store.store(entry)

    # Now test before_request - should inject in OpenAI format
    messages = [
        {"role": "user", "content": "What's the weather?"},
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "call_123", "type": "function", "function": {"name": "get_weather"}}
            ],
        },
        {"role": "tool", "tool_call_id": "call_123", "content": "Sunny"},
        {"role": "user", "content": "Is that good?"},
    ]

    request_ctx = RequestContext(
        messages=messages,
        provider="gemini",
        model="gemini-3-pro",
        request_id="req_1",
        conversation_id="conv_1",
    )

    processed_ctx = await middleware.before_request(request_ctx)

    # CRITICAL: Check OpenAI-compatible format
    assistant_msg = processed_ctx.messages[1]

    # Should NOT have message-level reasoning_details (that's the bug we're fixing)
    # Current implementation incorrectly adds it here
    assert "reasoning_details" not in assistant_msg, (
        "reasoning_details should NOT be at message level - "
        "should be in extra_content.google.thought_signature on tool_call"
    )

    # Should have extra_content.google.thought_signature on the tool_call
    tool_call = assistant_msg["tool_calls"][0]
    assert "extra_content" in tool_call, "tool_call should have extra_content"
    assert "google" in tool_call["extra_content"], "extra_content should have google namespace"
    assert "thought_signature" in tool_call["extra_content"]["google"], (
        "google should have thought_signature"
    )
    assert tool_call["extra_content"]["google"]["thought_signature"] == "sig_abc123"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multiple_tool_calls_with_signatures():
    """Each tool_call should get its own thought_signature in extra_content."""
    store = ThoughtSignatureStore(max_size=100, ttl_seconds=3600)
    middleware = ThoughtSignatureMiddleware(store=store)

    # Store multiple signatures for sequential calls
    entry1 = ThoughtSignatureEntry(
        message_id="msg_1",
        reasoning_details=[{"thought_signature": "sig_1"}],
        tool_call_ids=frozenset(["call_1"]),
        timestamp=time.time(),
        conversation_id="conv_1",
        provider="gemini",
        model="gemini-3-pro",
    )
    entry2 = ThoughtSignatureEntry(
        message_id="msg_2",
        reasoning_details=[{"thought_signature": "sig_2"}],
        tool_call_ids=frozenset(["call_2"]),
        timestamp=time.time(),
        conversation_id="conv_1",
        provider="gemini",
        model="gemini-3-pro",
    )
    await store.store(entry1)
    await store.store(entry2)

    # Sequential tool calls (multi-step)
    messages = [
        {"role": "user", "content": "Check weather and book taxi"},
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "check_weather"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Rainy"},
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "call_2", "type": "function", "function": {"name": "book_taxi"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_2", "content": "Booked"},
        {"role": "user", "content": "Thanks"},
    ]

    request_ctx = RequestContext(
        messages=messages,
        provider="gemini",
        model="gemini-3-pro",
        request_id="req_1",
        conversation_id="conv_1",
    )

    processed_ctx = await middleware.before_request(request_ctx)

    # First assistant message should have sig_1 in OpenAI format
    assert "extra_content" in processed_ctx.messages[1]["tool_calls"][0]
    assert (
        processed_ctx.messages[1]["tool_calls"][0]["extra_content"]["google"]["thought_signature"]
        == "sig_1"
    )

    # Second assistant message should have sig_2 in OpenAI format
    assert "extra_content" in processed_ctx.messages[3]["tool_calls"][0]
    assert (
        processed_ctx.messages[3]["tool_calls"][0]["extra_content"]["google"]["thought_signature"]
        == "sig_2"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parallel_tool_calls_only_first_has_signature():
    """For parallel tool calls, only the first should have thought_signature."""
    store = ThoughtSignatureStore(max_size=100, ttl_seconds=3600)
    middleware = ThoughtSignatureMiddleware(store=store)

    # Parallel calls share one signature (on first call)
    entry = ThoughtSignatureEntry(
        message_id="msg_1",
        reasoning_details=[{"thought_signature": "sig_parallel"}],
        tool_call_ids=frozenset(["call_1", "call_2"]),  # Both IDs in same entry
        timestamp=time.time(),
        conversation_id="conv_1",
        provider="gemini",
        model="gemini-3-pro",
    )
    await store.store(entry)

    messages = [
        {"role": "user", "content": "Check weather in Paris and London"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "London"}'},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "15C"},
        {"role": "tool", "tool_call_id": "call_2", "content": "12C"},
        {"role": "user", "content": "Thanks"},
    ]

    request_ctx = RequestContext(
        messages=messages,
        provider="gemini",
        model="gemini-3-pro",
        request_id="req_1",
        conversation_id="conv_1",
    )

    processed_ctx = await middleware.before_request(request_ctx)

    tool_calls = processed_ctx.messages[1]["tool_calls"]

    # First tool_call should have signature
    assert "extra_content" in tool_calls[0]
    assert tool_calls[0]["extra_content"]["google"]["thought_signature"] == "sig_parallel"

    # Second tool_call should NOT have signature (per Google spec)
    has_sig = (
        "extra_content" in tool_calls[1]
        and "google" in tool_calls[1].get("extra_content", {})
        and "thought_signature" in tool_calls[1].get("extra_content", {}).get("google", {})
    )
    assert not has_sig, "Second parallel tool_call should NOT have thought_signature"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extraction_from_openai_format():
    """Test extracting thought signatures from OpenAI format responses."""
    store = ThoughtSignatureStore(max_size=100, ttl_seconds=3600)
    middleware = ThoughtSignatureMiddleware(store=store)

    # Response in OpenAI format (what Google returns)
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "I'll check the weather",
                    "tool_calls": [
                        {
                            "id": "call_abc",
                            "type": "function",
                            "function": {"name": "get_weather", "arguments": "{}"},
                            "extra_content": {
                                "google": {"thought_signature": "sig_from_openai_format"}
                            },
                        }
                    ],
                }
            }
        ]
    }

    from src.middleware.base import ResponseContext

    request_ctx = RequestContext(
        messages=[],
        provider="gemini",
        model="gemini-3-pro",
        request_id="req_extract",
        conversation_id="conv_extract",
    )

    response_ctx = ResponseContext(
        response=response, request_context=request_ctx, is_streaming=False
    )

    # Process response - should extract and store
    await middleware.after_response(response_ctx)

    # Verify it was stored
    retrieved = await store.retrieve_by_tool_calls({"call_abc"}, conversation_id="conv_extract")
    assert retrieved is not None
    # Should return the thought_signature
    assert any(rd.get("thought_signature") == "sig_from_openai_format" for rd in retrieved)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_backward_compatible_extraction_from_legacy_format():
    """Test that extraction still works with legacy message-level reasoning_details."""
    store = ThoughtSignatureStore(max_size=100, ttl_seconds=3600)
    middleware = ThoughtSignatureMiddleware(store=store)

    # Response in legacy format (what current implementation uses)
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "I'll check the weather",
                    "tool_calls": [
                        {
                            "id": "call_legacy",
                            "type": "function",
                            "function": {"name": "get_weather"},
                        }
                    ],
                    "reasoning_details": [{"thought_signature": "sig_legacy_format"}],
                }
            }
        ]
    }

    from src.middleware.base import ResponseContext

    request_ctx = RequestContext(
        messages=[],
        provider="gemini",
        model="gemini-3-pro",
        request_id="req_legacy",
        conversation_id="conv_legacy",
    )

    response_ctx = ResponseContext(
        response=response, request_context=request_ctx, is_streaming=False
    )

    # Process response - should still extract from legacy format
    await middleware.after_response(response_ctx)

    # Verify it was stored
    retrieved = await store.retrieve_by_tool_calls({"call_legacy"}, conversation_id="conv_legacy")
    assert retrieved is not None
    assert any(rd.get("thought_signature") == "sig_legacy_format" for rd in retrieved)
