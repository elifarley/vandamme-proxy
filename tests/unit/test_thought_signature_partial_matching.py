import time

import pytest

from src.middleware.thought_signature_store import ThoughtSignatureEntry, ThoughtSignatureStore


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retrieve_by_tool_calls_partial_match_uses_most_recent_in_conversation():
    store = ThoughtSignatureStore(max_size=10, ttl_seconds=60.0, cleanup_interval=9999.0)

    # older entry
    await store.store(
        ThoughtSignatureEntry(
            message_id="m1",
            reasoning_details=[{"thought_signature": "old"}],
            tool_call_ids=frozenset({"call_shared", "call_a"}),
            timestamp=time.time() - 10,
            conversation_id="conv_1",
            provider="vertex",
            model="gemini-3-pro",
        )
    )

    # newer entry sharing one tool_call_id
    await store.store(
        ThoughtSignatureEntry(
            message_id="m2",
            reasoning_details=[{"thought_signature": "new"}],
            tool_call_ids=frozenset({"call_shared", "call_b"}),
            timestamp=time.time(),
            conversation_id="conv_1",
            provider="vertex",
            model="gemini-3-pro",
        )
    )

    got = await store.retrieve_by_tool_calls({"call_shared"}, conversation_id="conv_1")
    assert got == [{"thought_signature": "new"}]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retrieve_by_tool_calls_does_not_cross_conversations():
    store = ThoughtSignatureStore(max_size=10, ttl_seconds=60.0, cleanup_interval=9999.0)

    await store.store(
        ThoughtSignatureEntry(
            message_id="m1",
            reasoning_details=[{"thought_signature": "conv1"}],
            tool_call_ids=frozenset({"call_shared"}),
            timestamp=time.time(),
            conversation_id="conv_1",
            provider="vertex",
            model="gemini-3-pro",
        )
    )

    # same tool id in different conversation
    await store.store(
        ThoughtSignatureEntry(
            message_id="m2",
            reasoning_details=[{"thought_signature": "conv2"}],
            tool_call_ids=frozenset({"call_shared"}),
            timestamp=time.time() + 1,
            conversation_id="conv_2",
            provider="vertex",
            model="gemini-3-pro",
        )
    )

    got1 = await store.retrieve_by_tool_calls({"call_shared"}, conversation_id="conv_1")
    got2 = await store.retrieve_by_tool_calls({"call_shared"}, conversation_id="conv_2")

    assert got1 == [{"thought_signature": "conv1"}]
    assert got2 == [{"thought_signature": "conv2"}]
