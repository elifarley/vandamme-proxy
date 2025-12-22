import json

import pytest

from src.conversion.openai_stream_to_claude_state_machine import (
    OpenAIToClaudeStreamState,
    final_events,
)


@pytest.mark.unit
def test_final_events_uses_provided_usage_in_message_delta() -> None:
    state = OpenAIToClaudeStreamState(message_id="msg_x", tool_name_map_inverse={})
    state.final_stop_reason = "tool_use"

    events = final_events(state, usage={"input_tokens": 12, "output_tokens": 34})

    message_delta = next(e for e in events if e.startswith("event: message_delta"))
    payload = json.loads(message_delta.split("data: ", 1)[1])

    assert payload["usage"]["input_tokens"] == 12
    assert payload["usage"]["output_tokens"] == 34
