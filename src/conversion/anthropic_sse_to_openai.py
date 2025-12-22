from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from typing import Any


def _parse_sse_event(raw: str) -> tuple[str | None, str | None]:
    """Parse a single SSE event payload into (event, data).

    Expects a single event block containing lines like:
      event: message_start
      data: {...}

    Returns (None, None) if not parseable.
    """
    event: str | None = None
    data: str | None = None

    for line in raw.splitlines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data = line.split(":", 1)[1].strip()

    return event, data


async def anthropic_sse_to_openai_chat_completions_sse(
    *,
    anthropic_sse_lines: AsyncGenerator[str, None],
    model: str,
    completion_id: str,
) -> AsyncGenerator[str, None]:
    """Translate Anthropic Messages SSE events into OpenAI Chat Completions SSE.

    Subset mapping:
    - text deltas -> choices[].delta.content
    - message_delta stop_reason -> finish_reason

    Emits OpenAI-style SSE lines:
      data: {"object":"chat.completion.chunk", ...}\n\n
    and terminates with:
      data: [DONE]\n\n
    Notes:
    - This expects upstream lines to contain the full SSE event lines (`event:` + `data:`).
    - In this codebase `AnthropicClient.create_chat_completion_stream` yields lines prefixed
      with `data: ` and without SSE newlines. To make translation robust, we treat the
      payload after `data:` as either:
        (a) a full SSE block (with embedded newlines), or
        (b) a single SSE line (e.g. `event: ...` or `data: {...}`), in which case we buffer
            until we have both event and data.
    """

    created = int(time.time())

    pending_event: str | None = None
    pending_data: str | None = None
    tool_call_ids_by_index: dict[int, str] = {}
    tool_names_by_index: dict[int, str] = {}
    emitted_tool_start: set[int] = set()
    emitted_role: bool = False
    finished: bool = False

    def _emit_role_delta() -> str:
        nonlocal emitted_role
        if emitted_role:
            return ""
        emitted_role = True
        chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }
        return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    def _emit_tool_delta(
        index: int, *, name: str | None = None, args_delta: str | None = None
    ) -> str:
        # OpenAI tool delta format: tool_calls is a list; each entry has index, id, function fields.
        tool_id = tool_call_ids_by_index.get(index) or f"call-{completion_id}-{index}"
        tool_call_ids_by_index[index] = tool_id

        fn: dict[str, str] = {}
        if name is not None:
            fn["name"] = name
        if args_delta is not None:
            fn["arguments"] = args_delta

        entry: dict[str, Any] = {"index": index, "id": tool_id, "type": "function"}
        if fn:
            entry["function"] = fn

        chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"tool_calls": [entry]}, "finish_reason": None}],
        }
        return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    def _emit_text_delta(text: str) -> str:
        chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
        }
        return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    def _emit_finish(finish_reason: str) -> str:
        chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
        }
        return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    def _finish_reason_from_stop_reason(stop_reason: str | None) -> str:
        if stop_reason == "tool_use":
            return "tool_calls"
        if stop_reason == "max_tokens":
            return "length"
        return "stop"

    async for raw_line in anthropic_sse_lines:
        line = raw_line.strip()
        if not line:
            continue

        # Handle wrappers that yield `data: ...` for each upstream line.
        if line.startswith("data: "):
            line = line[len("data: ") :]

        # Anthropic stream may include [DONE] sentinel from our passthrough client.
        if line == "[DONE]":
            break

        # Case (a): the payload is a full SSE block containing both event + data.
        event, data = _parse_sse_event(line)

        # Case (b): payload is a single SSE line; buffer until we have both.
        if event is None and data is None:
            if line.startswith("event:"):
                pending_event = line.split(":", 1)[1].strip()
                continue
            if line.startswith("data:"):
                line.split(":", 1)[1].strip()
                continue
            continue

        # If we only received an event name, buffer it and wait for a data line.
        if event is not None and data is None:
            pending_event = event
            continue

        # If we only received data, use buffered event if available.
        if event is None and pending_event is not None:
            event = pending_event

        # If we received a data line without an event line, ignore.
        if event is None or data is None:
            continue

        # Clear buffers after successful assembly.
        pending_event = None

        # Handle out-of-band data buffering for implementations that send `event:` and
        # `data:` as separate chunks.
        if event is not None and data is None:
            pending_event = event
            continue
        if event is not None and data is not None:
            pending_data = data

        if pending_data is not None:
            data = pending_data
            pending_data = None

        role_delta = _emit_role_delta()
        if role_delta:
            yield role_delta

        if event == "content_block_start":
            try:
                payload = json.loads(data)
            except Exception:
                continue
            idx = payload.get("index")
            block = payload.get("content_block") or {}
            if not isinstance(idx, int) or not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                name = block.get("name")
                tool_id = block.get("id")
                if isinstance(name, str):
                    tool_names_by_index[idx] = name
                if isinstance(tool_id, str):
                    tool_call_ids_by_index[idx] = tool_id
                emitted_tool_start.add(idx)
                yield _emit_tool_delta(idx, name=tool_names_by_index.get(idx))
            continue

        if event == "content_block_delta":
            try:
                payload = json.loads(data)
            except Exception:
                continue
            idx = payload.get("index")
            delta = payload.get("delta") or {}
            if not isinstance(idx, int) or not isinstance(delta, dict):
                continue

            delta_type = delta.get("type")
            if delta_type == "text_delta":
                text = delta.get("text")
                if isinstance(text, str) and text:
                    yield _emit_text_delta(text)
                continue

            if delta_type == "input_json_delta":
                partial = delta.get("partial_json")
                if not isinstance(partial, str) or partial == "":
                    continue

                # Emit tool call start if we didn't see content_block_start for some reason.
                if idx not in emitted_tool_start:
                    emitted_tool_start.add(idx)
                    yield _emit_tool_delta(idx, name=tool_names_by_index.get(idx))

                yield _emit_tool_delta(idx, args_delta=partial)
                continue

        if event == "message_delta":
            try:
                payload = json.loads(data)
            except Exception:
                continue

            stop_reason = (payload.get("delta") or {}).get("stop_reason")
            finish_reason = _finish_reason_from_stop_reason(stop_reason)
            if not finished:
                finished = True
                yield _emit_finish(finish_reason)
            continue

        if event == "message_stop":
            break

        # Unhandled events are ignored.
        continue

    if not finished:
        yield _emit_finish("stop")

    yield "data: [DONE]\n\n"
