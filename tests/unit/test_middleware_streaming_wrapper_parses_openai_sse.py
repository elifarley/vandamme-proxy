import pytest

from src.api.middleware_integration import MiddlewareAwareRequestProcessor, MiddlewareStreamingWrapper
from src.middleware.base import RequestContext


class _RecorderProcessor(MiddlewareAwareRequestProcessor):
    def __init__(self) -> None:
        super().__init__()
        self.seen: list[dict] = []

    async def process_stream_chunk(self, chunk, request_context, accumulated_metadata):
        self.seen.append(chunk)
        return chunk

    async def finalize_stream(self, request_context, accumulated_metadata):
        # no-op for test
        return None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_streaming_wrapper_extracts_openai_delta_from_sse_lines():
    async def stream():
        yield 'data: {"choices":[{"delta":{"tool_calls":[{"id":"call_1"}]}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"reasoning_details":[{"thought_signature":"sig"}]}}]}\n\n'
        yield 'data: [DONE]\n\n'

    proc = _RecorderProcessor()
    req_ctx = RequestContext(messages=[], provider="vertex", model="gemini-3-pro", request_id="r1")

    wrapper = MiddlewareStreamingWrapper(original_stream=stream(), request_context=req_ctx, processor=proc)

    # drain wrapper
    async for _ in wrapper:
        pass

    assert proc.seen == [
        {"tool_calls": [{"id": "call_1"}]},
        {"reasoning_details": [{"thought_signature": "sig"}]},
    ]
