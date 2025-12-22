from __future__ import annotations


def anthropic_tool_use_stream_events() -> list[bytes]:
    """Minimal Anthropic SSE stream that includes a tool_use with input_json_delta.

    Mirrors the same event framing as tests/fixtures/mock_http.py::anthropic_streaming_events.
    """
    return [
        (
            b'event: message_start\ndata: {"type":"message_start","message":{'
            b'"id":"msg_tool_stream_1","type":"message","role":"assistant",'
            b'"content":[],"model":"claude-3-5-sonnet-20241022","usage":{'
            b'"input_tokens":10,"output_tokens":0}}}\n\n'
        ),
        (
            b'event: content_block_start\ndata: {"type":"content_block_start",'
            b'"index":0,"content_block":{"type":"tool_use","id":"toolu_test123",'
            b'"name":"calculator","input":{}}}\n\n'
        ),
        (
            b'event: content_block_delta\ndata: {"type":"content_block_delta",'
            b'"index":0,"delta":{"type":"input_json_delta","partial_json":"{\\"expression\\":"}}}\n\n'
        ),
        (
            b'event: content_block_delta\ndata: {"type":"content_block_delta",'
            b'"index":0,"delta":{"type":"input_json_delta","partial_json":"2 + 2\\"}"}}\n\n'
        ),
        b'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
        (
            b'event: message_delta\ndata: {"type":"message_delta","delta":{'
            b'"stop_reason":"tool_use"},"usage":{"output_tokens":5}}\n\n'
        ),
        b'event: message_stop\ndata: {"type":"message_stop"}\n\n',
    ]
