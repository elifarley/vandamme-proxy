import json

import pytest

from src.conversion.response_converter import convert_openai_streaming_to_claude
from src.models.claude import ClaudeMessage, ClaudeMessagesRequest


def _parse_sse_events(sse_text: str) -> list[tuple[str, dict]]:
    """Parse `event: X\ndata: {...}\n\n` blocks.

    This is intentionally minimal and tailored to the converter's output.
    """

    events: list[tuple[str, dict]] = []
    blocks = [b for b in sse_text.split("\n\n") if b.strip()]
    for block in blocks:
        lines = block.splitlines()
        if not lines:
            continue
        assert lines[0].startswith("event: ")
        event_name = lines[0].split("event: ", 1)[1]
        assert lines[1].startswith("data: ")
        data = json.loads(lines[1].split("data: ", 1)[1])
        events.append((event_name, data))
    return events


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openai_streaming_sse_invariants_ordering_and_closure() -> None:
    # Arrange: OpenAI SSE lines that yield a tool_use with JSON args in multiple deltas.
    openai_lines = [
        "data: "
        + json.dumps(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_0",
                                    "type": "function",
                                    "function": {
                                        "name": "calculator",
                                        "arguments": '{"expression":',
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        )
        + "\n",
        "data: "
        + json.dumps(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "type": "function",
                                    "function": {"arguments": '"2+2"}'},
                                }
                            ]
                        }
                    }
                ]
            }
        )
        + "\n",
        "data: " + json.dumps({"choices": [{"finish_reason": "tool_calls", "delta": {}}]}) + "\n",
        "data: [DONE]\n",
    ]

    async def _gen():
        for line in openai_lines:
            yield line

    original_request = ClaudeMessagesRequest(
        model="openai:gpt-4",
        max_tokens=10,
        messages=[ClaudeMessage(role="user", content="hi")],
    )

    # Act
    body = "".join(
        [
            chunk
            async for chunk in convert_openai_streaming_to_claude(
                _gen(),
                original_request,
                logger=None,
            )
        ]
    )
    events = _parse_sse_events(body)

    # Assert invariants:
    # 1) We must start a tool_use content block before sending input_json_delta for it.
    tool_start_idx = next(
        i
        for i, (_name, data) in enumerate(events)
        if data.get("type") == "content_block_start"
        and data.get("content_block", {}).get("type") == "tool_use"
    )
    input_json_idx = next(
        i
        for i, (_name, data) in enumerate(events)
        if data.get("type") == "content_block_delta"
        and data.get("delta", {}).get("type") == "input_json_delta"
    )
    assert tool_start_idx < input_json_idx

    # 2) Any started content block should be stopped.
    started_indices = [
        str(data["index"]) for _name, data in events if data.get("type") == "content_block_start"
    ]
    stopped_indices = [
        str(data["index"]) for _name, data in events if data.get("type") == "content_block_stop"
    ]
    for idx in started_indices:
        assert idx in stopped_indices

    # 3) message_delta must precede message_stop.
    msg_delta_idx = next(i for i, (_n, d) in enumerate(events) if d.get("type") == "message_delta")
    msg_stop_idx = next(i for i, (_n, d) in enumerate(events) if d.get("type") == "message_stop")
    assert msg_delta_idx < msg_stop_idx
