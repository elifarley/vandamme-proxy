"""Unit tests for OpenAI→Claude streaming state machine.

This module tests the ingest_openai_chunk() function which converts OpenAI
streaming chunks to Claude SSE events through a stateful transformation.

State Machine Overview:
    - Tracks text blocks (text_block_index)
    - Manages tool call state per index (current_tool_calls)
    - Buffers tool arguments until complete JSON
    - Maps finish_reason to stop_reason

Test Categories:
    1. Text Streaming: Basic content deltas
    2. Tool Calls: ID allocation, start events, argument buffering
    3. Multi-Tool: Concurrent tool call handling
    4. Edge Cases: Empty/malformed data
    5. Stop Reasons: finish_reason mapping
    6. Invariants: Property-based state consistency
"""

import json

import pytest

from src.conversion.openai_stream_to_claude_state_machine import (
    OpenAIToClaudeStreamState,
    final_events,
    ingest_openai_chunk,
    initial_events,
    parse_openai_sse_line,
)

# =============================================================================
# Helper Functions
# =============================================================================


def parse_sse_event(sse_string: str) -> tuple[str, dict]:
    """Parse SSE string into (event_name, data_dict)."""
    lines = sse_string.strip().split("\n")
    event_name = None
    data_json = None

    for line in lines:
        if line.startswith("event: "):
            event_name = line.split("event: ")[1]
        elif line.startswith("data: "):
            data_json = line.split("data: ")[1]

    if event_name is None or data_json is None:
        raise ValueError(f"Invalid SSE format: {sse_string[:100]}")

    return event_name, json.loads(data_json)


def extract_events_by_type(sse_strings: list[str], event_type: str) -> list[dict]:
    """Extract all events of a given type from SSE strings."""
    events = []
    for sse in sse_strings:
        name, data = parse_sse_event(sse)
        if name == event_type:
            events.append(data)
    return events


def assert_content_block_delta(events: list[str], expected_index: int, expected_text: str) -> None:
    """Helper to assert content_block_delta event with correct content."""
    delta_events = extract_events_by_type(events, "content_block_delta")
    assert len(delta_events) == 1
    assert delta_events[0]["index"] == expected_index
    assert delta_events[0]["delta"]["type"] == "text_delta"
    assert delta_events[0]["delta"]["text"] == expected_text


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def stream_state():
    """Factory for creating stream state with custom defaults."""

    def _create(**kwargs):
        defaults = {
            "message_id": "msg_test",
            "tool_name_map_inverse": {},
            "text_block_index": 0,
            "tool_block_counter": 0,
        }
        defaults.update(kwargs)
        return OpenAIToClaudeStreamState(**defaults)

    return _create


# =============================================================================
# Category 1: Text Streaming Tests (5 tests)
# =============================================================================


@pytest.mark.unit
def test_ingest_openai_chunk_text_delta_emits_content_block_delta(stream_state):
    """Test that text content is converted to Claude content_block_delta."""
    state = stream_state()

    chunk = {"choices": [{"delta": {"content": "Hello, world!"}, "finish_reason": None}]}

    events = ingest_openai_chunk(state, chunk)

    assert len(events) == 1
    assert "content_block_delta" in events[0]
    assert "text_delta" in events[0]
    assert "Hello, world!" in events[0]


@pytest.mark.unit
def test_ingest_openai_chunk_text_delta_uses_correct_index(stream_state):
    """Test that text deltas use state.text_block_index."""
    state = stream_state(text_block_index=0)

    chunk = {"choices": [{"delta": {"content": "test"}, "finish_reason": None}]}

    events = ingest_openai_chunk(state, chunk)

    _, data = parse_sse_event(events[0])
    assert data["index"] == 0


@pytest.mark.unit
def test_ingest_openai_chunk_multiple_text_deltas(stream_state):
    """Test multiple sequential text chunks."""
    state = stream_state()

    chunks = [
        {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": " world"}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": "!"}, "finish_reason": None}]},
    ]

    all_events = []
    for chunk in chunks:
        all_events.extend(ingest_openai_chunk(state, chunk))

    delta_events = extract_events_by_type(all_events, "content_block_delta")
    assert len(delta_events) == 3
    assert delta_events[0]["delta"]["text"] == "Hello"
    assert delta_events[1]["delta"]["text"] == " world"
    assert delta_events[2]["delta"]["text"] == "!"


@pytest.mark.unit
def test_ingest_openai_chunk_empty_content_skipped(stream_state):
    """Test that empty content strings are skipped."""
    state = stream_state()

    chunk = {"choices": [{"delta": {"content": ""}, "finish_reason": None}]}

    events = ingest_openai_chunk(state, chunk)

    # Empty content is still emitted (upstream may send empty deltas)
    assert len(events) == 1
    _, data = parse_sse_event(events[0])
    assert data["delta"]["text"] == ""


@pytest.mark.unit
def test_ingest_openai_chunk_null_content_ignored(stream_state):
    """Test that null content is ignored."""
    state = stream_state()

    chunk = {"choices": [{"delta": {"content": None}, "finish_reason": None}]}

    events = ingest_openai_chunk(state, chunk)

    assert events == []


# =============================================================================
# Category 2: Tool Call State Machine Tests (8 tests)
# =============================================================================


@pytest.mark.unit
def test_ingest_openai_chunk_tool_call_initial_state(stream_state):
    """Test tool call starts with no state."""
    state = stream_state()

    assert len(state.current_tool_calls) == 0
    assert state.tool_block_counter == 0


@pytest.mark.unit
def test_ingest_openai_chunk_tool_call_id_allocation(stream_state):
    """Test tool call ID is allocated and stored."""
    state = stream_state()

    chunk = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {"index": 0, "id": "call_abc123", "function": {"name": "calculator"}}
                    ]
                }
            }
        ]
    }

    ingest_openai_chunk(state, chunk)

    # State should have tool call at index 0
    assert 0 in state.current_tool_calls
    # ToolCallIdAllocator returns provided_id directly when given
    assert state.current_tool_calls[0].tool_id == "call_abc123"
    assert state.current_tool_calls[0].tool_name == "calculator"


@pytest.mark.unit
def test_ingest_openai_chunk_tool_call_emits_start_event_once(stream_state):
    """Test content_block_start is emitted only when id+name present."""
    state = stream_state()

    # First chunk with id only
    chunk1 = {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_123"}]}}]}

    events1 = ingest_openai_chunk(state, chunk1)
    # No start event yet (no name)
    assert not any("content_block_start" in e for e in events1)
    assert not state.current_tool_calls[0].started

    # Second chunk with name
    chunk2 = {
        "choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "calculator"}}]}}]
    }

    events2 = ingest_openai_chunk(state, chunk2)
    # Now start event is emitted
    assert any("content_block_start" in e for e in events2)
    assert state.current_tool_calls[0].started
    assert state.tool_block_counter == 1


@pytest.mark.unit
def test_ingest_openai_chunk_tool_call_name_remapping(stream_state):
    """Test tool name is remapped via tool_name_map_inverse."""
    state = stream_state(tool_name_map_inverse={"remapped_calculator": "calculator"})

    chunk = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {"index": 0, "id": "call_123", "function": {"name": "remapped_calculator"}}
                    ]
                }
            }
        ]
    }

    events = ingest_openai_chunk(state, chunk)

    # Extract content_block_start event
    start_events = extract_events_by_type(events, "content_block_start")
    assert len(start_events) == 1
    assert start_events[0]["content_block"]["name"] == "calculator"


@pytest.mark.unit
def test_ingest_openai_chunk_tool_call_args_buffering(stream_state):
    """Test arguments are buffered until complete JSON."""
    state = stream_state()

    # Initialize tool call
    init_chunk = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [{"index": 0, "id": "call_123", "function": {"name": "calc"}}]
                }
            }
        ]
    }
    ingest_openai_chunk(state, init_chunk)

    # Partial JSON
    chunk1 = {
        "choices": [
            {"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"expr":'}}]}}
        ]
    }
    events1 = ingest_openai_chunk(state, chunk1)

    # No delta event yet (incomplete JSON)
    assert not any("input_json_delta" in e for e in events1)
    assert state.current_tool_calls[0].args_buffer == '{"expr":'

    # Complete JSON
    chunk2 = {
        "choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"2+2"}'}}]}}]
    }
    events2 = ingest_openai_chunk(state, chunk2)

    # Delta event emitted
    assert any("input_json_delta" in e for e in events2)
    assert state.current_tool_calls[0].json_sent


@pytest.mark.unit
def test_ingest_openai_chunk_tool_call_json_sent_only_once(stream_state):
    """Test input_json_delta is emitted exactly once per tool."""
    state = stream_state()

    # Initialize tool call with complete args
    init_chunk = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_0",
                            "function": {"name": "tool", "arguments": '{"x":1}'},
                        }
                    ]
                }
            }
        ]
    }
    ingest_openai_chunk(state, init_chunk)

    # Send args again (should not emit again)
    args_chunk = {
        "choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"x":1}'}}]}}]
    }

    events1 = ingest_openai_chunk(state, args_chunk)
    events2 = ingest_openai_chunk(state, args_chunk)

    # Only first emission should have input_json_delta
    deltas1 = [e for e in events1 if "input_json_delta" in e]
    deltas2 = [e for e in events2 if "input_json_delta" in e]

    assert len(deltas1) == 0  # Already sent in init_chunk
    assert len(deltas2) == 0


@pytest.mark.unit
def test_ingest_openai_chunk_tool_call_claude_index_calculation(stream_state):
    """Test Claude tool index = text_block_index + tool_block_counter."""
    state = stream_state(text_block_index=0)

    chunk = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_0",
                            "function": {"name": "tool", "arguments": "{}"},
                        }
                    ]
                }
            }
        ]
    }

    events = ingest_openai_chunk(state, chunk)

    start_event = extract_events_by_type(events, "content_block_start")[0]
    expected_index = state.text_block_index + state.tool_block_counter
    assert start_event["index"] == expected_index == 1


@pytest.mark.unit
def test_ingest_openai_chunk_tool_call_args_before_name(stream_state):
    """Test arguments arriving before name (edge case)."""
    state = stream_state()

    # Arguments first
    chunk1 = {
        "choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{}"}}]}}]
    }
    events1 = ingest_openai_chunk(state, chunk1)

    # No start event yet (no name)
    assert not any("content_block_start" in e for e in events1)

    # Name arrives later
    chunk2 = {
        "choices": [
            {"delta": {"tool_calls": [{"index": 0, "id": "call_0", "function": {"name": "calc"}}]}}
        ]
    }
    events2 = ingest_openai_chunk(state, chunk2)

    # Now start event should be emitted
    assert any("content_block_start" in e for e in events2)


# =============================================================================
# Category 3: Multiple Concurrent Tools Tests (4 tests)
# =============================================================================


@pytest.mark.unit
def test_ingest_openai_chunk_multiple_tools_concurrent_indices(stream_state):
    """Test multiple tool calls with different indices."""
    state = stream_state()

    chunk = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_0",
                            "function": {"name": "calculator", "arguments": "{}"},
                        },
                        {
                            "index": 1,
                            "id": "call_1",
                            "function": {"name": "weather", "arguments": "{}"},
                        },
                    ]
                }
            }
        ]
    }

    events = ingest_openai_chunk(state, chunk)

    # Both indices tracked
    assert 0 in state.current_tool_calls
    assert 1 in state.current_tool_calls
    assert state.tool_block_counter == 2

    # Both start events emitted
    start_events = extract_events_by_type(events, "content_block_start")
    assert len(start_events) == 2


@pytest.mark.unit
def test_ingest_openai_chunk_multiple_tools_out_of_order_deltas(stream_state):
    """Test tool call arguments arriving out of order."""
    state = stream_state()

    # Start tool 0
    chunk0 = {
        "choices": [
            {"delta": {"tool_calls": [{"index": 0, "id": "call_0", "function": {"name": "tool0"}}]}}
        ]
    }
    ingest_openai_chunk(state, chunk0)

    # Start tool 1
    chunk1 = {
        "choices": [
            {"delta": {"tool_calls": [{"index": 1, "id": "call_1", "function": {"name": "tool1"}}]}}
        ]
    }
    ingest_openai_chunk(state, chunk1)

    # Args for tool 1 (out of order)
    chunk2 = {
        "choices": [
            {"delta": {"tool_calls": [{"index": 1, "function": {"arguments": '{"city":"NYC"}'}}]}}
        ]
    }
    ingest_openai_chunk(state, chunk2)

    # Tool 1 should emit delta
    assert state.current_tool_calls[1].json_sent

    # Args for tool 0 (after tool 1)
    chunk3 = {
        "choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"x":1}'}}]}}]
    }
    ingest_openai_chunk(state, chunk3)

    # Tool 0 should now emit delta
    assert state.current_tool_calls[0].json_sent


@pytest.mark.unit
def test_ingest_openai_chunk_interleaved_text_and_tools(stream_state):
    """Test text deltas interleaved with tool calls."""
    state = stream_state()

    chunks = [
        # Text first
        {"choices": [{"delta": {"content": "Let me calculate"}, "finish_reason": None}]},
        # Then tool call
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_0",
                                "function": {"name": "calc", "arguments": "{}"},
                            }
                        ]
                    }
                }
            ]
        },
    ]

    all_events = []
    for chunk in chunks:
        all_events.extend(ingest_openai_chunk(state, chunk))

    delta_events = extract_events_by_type(all_events, "content_block_delta")
    start_events = extract_events_by_type(all_events, "content_block_start")

    assert len(delta_events) >= 1
    assert delta_events[0]["delta"]["type"] == "text_delta"
    assert len(start_events) == 1


@pytest.mark.unit
def test_ingest_openai_chunk_three_tools_sequential_indices(stream_state):
    """Test three tool calls with indices 0, 1, 2."""
    state = stream_state()

    for i in range(3):
        chunk = {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": i,
                                "id": f"call_{i}",
                                "function": {"name": f"tool{i}", "arguments": "{}"},
                            }
                        ]
                    }
                }
            ]
        }
        ingest_openai_chunk(state, chunk)

    assert len(state.current_tool_calls) == 3
    assert state.tool_block_counter == 3
    assert all(tc.started for tc in state.current_tool_calls.values())


# =============================================================================
# Category 4: Edge Case Tests (6 tests)
# =============================================================================


@pytest.mark.unit
def test_ingest_openai_chunk_empty_choices_returns_empty(stream_state):
    """Test empty choices list returns no events."""
    state = stream_state()

    chunk = {"choices": []}
    events = ingest_openai_chunk(state, chunk)

    assert events == []


@pytest.mark.unit
def test_ingest_openai_chunk_missing_delta_no_error(stream_state):
    """Test missing delta field doesn't crash."""
    state = stream_state()

    chunk = {"choices": [{"finish_reason": None}]}
    events = ingest_openai_chunk(state, chunk)

    assert events == []


@pytest.mark.unit
def test_ingest_openai_chunk_done_returns_empty(stream_state):
    """Test _done marker returns empty list."""
    state = stream_state()

    chunk = {"_done": True}
    events = ingest_openai_chunk(state, chunk)

    assert events == []


@pytest.mark.unit
def test_ingest_openai_chunk_malformed_tool_calls_skipped(stream_state):
    """Test non-dict tool_calls are skipped."""
    state = stream_state()

    chunk = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {"index": 0, "id": "valid"},  # Valid
                        "invalid_string",  # Invalid - should skip
                        None,  # Invalid - should skip
                    ]
                }
            }
        ]
    }

    ingest_openai_chunk(state, chunk)

    # Only valid tool call tracked
    assert 0 in state.current_tool_calls
    assert len(state.current_tool_calls) == 1


@pytest.mark.unit
def test_ingest_openai_chunk_tool_call_missing_index_defaults_to_zero(stream_state):
    """Test tool call without index defaults to 0."""
    state = stream_state()

    chunk = {
        "choices": [{"delta": {"tool_calls": [{"id": "call_0", "function": {"name": "tool"}}]}}]
    }

    ingest_openai_chunk(state, chunk)

    # Should create at index 0 (default)
    assert 0 in state.current_tool_calls


@pytest.mark.unit
def test_ingest_openai_chunk_non_dict_function_skipped(stream_state):
    """Test non-dict function field is skipped."""
    state = stream_state()

    chunk = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_0",
                            "function": "not_a_dict",  # Invalid
                        }
                    ]
                }
            }
        ]
    }

    # Should not crash
    ingest_openai_chunk(state, chunk)

    # Tool call created but no name
    assert 0 in state.current_tool_calls
    assert state.current_tool_calls[0].tool_name is None


# =============================================================================
# Category 5: Stop Reason Transition Tests (4 tests)
# =============================================================================


@pytest.mark.unit
def test_ingest_openai_chunk_stop_reason_length_maps_to_max_tokens(stream_state):
    """Test finish_reason='length' maps to max_tokens."""
    state = stream_state()

    chunk = {"choices": [{"finish_reason": "length", "delta": {}}]}

    ingest_openai_chunk(state, chunk)

    assert state.final_stop_reason == "max_tokens"


@pytest.mark.unit
def test_ingest_openai_chunk_stop_reason_tool_calls(stream_state):
    """Test finish_reason='tool_calls' maps to tool_use."""
    state = stream_state()

    chunk = {"choices": [{"finish_reason": "tool_calls", "delta": {}}]}

    ingest_openai_chunk(state, chunk)

    assert state.final_stop_reason == "tool_use"


@pytest.mark.unit
def test_ingest_openai_chunk_stop_reason_function_call(stream_state):
    """Test finish_reason='function_call' maps to tool_use."""
    state = stream_state()

    chunk = {"choices": [{"finish_reason": "function_call", "delta": {}}]}

    ingest_openai_chunk(state, chunk)

    assert state.final_stop_reason == "tool_use"


@pytest.mark.unit
def test_ingest_openai_chunk_stop_reason_stop(stream_state):
    """Test finish_reason='stop' maps to end_turn."""
    state = stream_state()

    chunk = {"choices": [{"finish_reason": "stop", "delta": {}}]}

    ingest_openai_chunk(state, chunk)

    assert state.final_stop_reason == "end_turn"


@pytest.mark.unit
def test_ingest_openai_chunk_unknown_stop_reason_defaults_to_end_turn(stream_state):
    """Test unknown finish_reason defaults to end_turn."""
    state = stream_state()

    chunk = {"choices": [{"finish_reason": "unknown_reason", "delta": {}}]}

    ingest_openai_chunk(state, chunk)

    assert state.final_stop_reason == "end_turn"


# =============================================================================
# Category 6: Property-Based Invariant Tests (3 tests)
# =============================================================================


@pytest.mark.unit
def test_state_invariant_tool_block_counter_matches_started_tools(stream_state):
    """Property: tool_block_counter equals number of started tool calls."""
    state = stream_state()

    chunks = [
        # Tool 0 starts
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": 0, "id": "c0", "function": {"name": "t0"}}]}}
            ]
        },
        # Tool 1 starts
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": 1, "id": "c1", "function": {"name": "t1"}}]}}
            ]
        },
    ]

    for chunk in chunks:
        ingest_openai_chunk(state, chunk)

    started_count = sum(1 for tc in state.current_tool_calls.values() if tc.started)
    assert state.tool_block_counter == started_count == 2


@pytest.mark.unit
def test_state_invariant_claude_index_monotonically_increases(stream_state):
    """Property: Claude indices are monotonic increasing."""
    state = stream_state()

    indices_seen = []

    # Create multiple tools
    for i in range(3):
        chunk = {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": i,
                                "id": f"call_{i}",
                                "function": {"name": f"tool{i}", "arguments": "{}"},
                            }
                        ]
                    }
                }
            ]
        }
        events = ingest_openai_chunk(state, chunk)
        start_events = extract_events_by_type(events, "content_block_start")
        if start_events:
            indices_seen.append(start_events[0]["index"])

    # Indices should be strictly increasing
    assert indices_seen == sorted(indices_seen)
    assert indices_seen == [1, 2, 3]  # text_block_index=0, so tools at 1,2,3


@pytest.mark.unit
def test_state_invariant_final_stop_reason_always_valid(stream_state):
    """Property: final_stop_reason is always a valid Claude stop_reason."""
    state = stream_state()

    valid_reasons = {"end_turn", "max_tokens", "tool_use", "error"}

    # Test various finish reasons
    finish_reasons = ["length", "tool_calls", "stop", "unknown", None]

    for fr in finish_reasons:
        if fr is None:
            continue
        chunk = {"choices": [{"finish_reason": fr, "delta": {}}]}
        ingest_openai_chunk(state, chunk)

    assert state.final_stop_reason in valid_reasons


# =============================================================================
# Helper Functions Tests
# =============================================================================


@pytest.mark.unit
def test_parse_openai_sse_line_valid_json():
    """Test parsing valid SSE line with JSON."""
    line = 'data: {"choices": [{"delta": {"content": "test"}}]}'

    result = parse_openai_sse_line(line)

    assert result is not None
    assert result["choices"][0]["delta"]["content"] == "test"


@pytest.mark.unit
def test_parse_openai_sse_line_done_marker():
    """Test parsing [DONE] marker."""
    line = "data: [DONE]"

    result = parse_openai_sse_line(line)

    assert result == {"_done": True}


@pytest.mark.unit
def test_parse_openai_sse_line_empty_line():
    """Test parsing empty line returns None."""
    line = ""

    result = parse_openai_sse_line(line)

    assert result is None


@pytest.mark.unit
def test_parse_openai_sse_line_non_data_line():
    """Test parsing line without 'data: ' prefix returns None."""
    line = "event: message_start"

    result = parse_openai_sse_line(line)

    assert result is None


@pytest.mark.unit
def test_initial_events_structure():
    """Test initial_events returns correct structure."""
    events = initial_events(message_id="msg_123", model="gpt-4")

    assert len(events) == 3

    # Check message_start
    _, data = parse_sse_event(events[0])
    assert data["type"] == "message_start"
    assert data["message"]["id"] == "msg_123"
    assert data["message"]["model"] == "gpt-4"

    # Check content_block_start
    _, data = parse_sse_event(events[1])
    assert data["type"] == "content_block_start"
    assert data["index"] == 0

    # Check ping
    _, data = parse_sse_event(events[2])
    assert data["type"] == "ping"


@pytest.mark.unit
def test_final_events_basic():
    """Test final_events returns correct structure."""
    state = OpenAIToClaudeStreamState(message_id="msg_123", tool_name_map_inverse={})

    events = final_events(state, usage={"input_tokens": 10, "output_tokens": 5})

    # Should have: content_block_stop (text), message_delta, message_stop
    assert len(events) == 3

    # Check content_block_stop for text block
    _, data = parse_sse_event(events[0])
    assert data["type"] == "content_block_stop"
    assert data["index"] == 0

    # Check message_delta
    _, data = parse_sse_event(events[1])
    assert data["type"] == "message_delta"
    assert data["delta"]["stop_reason"] == "end_turn"
    assert data["usage"]["input_tokens"] == 10
    assert data["usage"]["output_tokens"] == 5

    # Check message_stop
    _, data = parse_sse_event(events[2])
    assert data["type"] == "message_stop"


@pytest.mark.unit
def test_final_events_with_tools():
    """Test final_events includes tool block stops."""
    from src.conversion.tool_call_delta import ToolCallIndexState

    state = OpenAIToClaudeStreamState(message_id="msg_123", tool_name_map_inverse={})

    # Simulate started tool call
    state.current_tool_calls[0] = ToolCallIndexState()
    state.current_tool_calls[0].started = True
    state.current_tool_calls[0].output_index = "1"  # Stored as string

    events = final_events(state)

    # Should have: text block stop, tool block stop, message_delta, message_stop
    assert len(events) == 4

    # Second event should be tool block stop
    _, data = parse_sse_event(events[1])
    assert data["type"] == "content_block_stop"
    # output_index is stored as string and serialized as-is
    assert data["index"] == "1"


@pytest.mark.unit
def test_final_events_without_message_stop():
    """Test final_events can exclude message_stop."""
    state = OpenAIToClaudeStreamState(message_id="msg_123", tool_name_map_inverse={})

    events = final_events(state, include_message_stop=False)

    # Should NOT have message_stop
    event_types = [parse_sse_event(e)[0] for e in events]
    assert "message_stop" not in event_types
