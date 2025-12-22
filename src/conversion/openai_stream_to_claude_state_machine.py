from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.conversion.errors import SSEParseError
from src.conversion.tool_call_delta import (
    ToolCallArgsAssembler,
    ToolCallIdAllocator,
    ToolCallIndexState,
)
from src.core.constants import Constants


@dataclass
class OpenAIToClaudeStreamState:
    message_id: str
    tool_name_map_inverse: dict[str, str]

    text_block_index: int = 0
    tool_block_counter: int = 0

    tool_id_allocator: ToolCallIdAllocator = field(init=False)
    args_assembler: ToolCallArgsAssembler = field(default_factory=ToolCallArgsAssembler)
    current_tool_calls: dict[int, ToolCallIndexState] = field(default_factory=dict)

    final_stop_reason: str = Constants.STOP_END_TURN

    def __post_init__(self) -> None:
        self.tool_id_allocator = ToolCallIdAllocator(id_prefix=f"toolu_{self.message_id}")


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def initial_events(*, message_id: str, model: str) -> list[str]:
    return [
        _sse(
            Constants.EVENT_MESSAGE_START,
            {
                "type": Constants.EVENT_MESSAGE_START,
                "message": {
                    "id": message_id,
                    "type": "message",
                    "role": Constants.ROLE_ASSISTANT,
                    "model": model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            },
        ),
        _sse(
            Constants.EVENT_CONTENT_BLOCK_START,
            {
                "type": Constants.EVENT_CONTENT_BLOCK_START,
                "index": 0,
                "content_block": {"type": Constants.CONTENT_TEXT, "text": ""},
            },
        ),
        _sse(Constants.EVENT_PING, {"type": Constants.EVENT_PING}),
    ]


def parse_openai_sse_line(line: str) -> dict[str, Any] | None:
    if not (line.strip() and line.startswith("data: ")):
        return None

    chunk_data = line[6:]
    if chunk_data.strip() == "[DONE]":
        return {"_done": True}

    try:
        parsed: Any = json.loads(chunk_data)
        if isinstance(parsed, dict):
            return parsed
        return {"_parsed": parsed}
    except json.JSONDecodeError as e:
        raise SSEParseError(
            "Failed to parse OpenAI streaming chunk as JSON",
            context={"chunk_data": chunk_data, "json_error": str(e)},
        ) from e


def ingest_openai_chunk(state: OpenAIToClaudeStreamState, chunk: dict[str, Any]) -> list[str]:
    if chunk.get("_done"):
        return []

    choices = chunk.get("choices", [])
    if not choices:
        return []

    choice = choices[0]
    delta = choice.get("delta", {})
    finish_reason = choice.get("finish_reason")

    out: list[str] = []

    if delta and "content" in delta and delta["content"] is not None:
        out.append(
            _sse(
                Constants.EVENT_CONTENT_BLOCK_DELTA,
                {
                    "type": Constants.EVENT_CONTENT_BLOCK_DELTA,
                    "index": state.text_block_index,
                    "delta": {"type": Constants.DELTA_TEXT, "text": delta["content"]},
                },
            )
        )

    tool_calls = delta.get("tool_calls")
    if isinstance(tool_calls, list):
        for tc_delta in tool_calls:
            if not isinstance(tc_delta, dict):
                continue
            tc_index = tc_delta.get("index", 0)

            if tc_index not in state.current_tool_calls:
                state.current_tool_calls[tc_index] = ToolCallIndexState()

            tool_call = state.current_tool_calls[tc_index]

            provided_id = tc_delta.get("id")
            if isinstance(provided_id, str) and provided_id:
                tool_call.tool_id = state.tool_id_allocator.get(tc_index, provided_id=provided_id)

            function_data = tc_delta.get(Constants.TOOL_FUNCTION, {})
            if isinstance(function_data, dict):
                name = function_data.get("name")
                if name:
                    tool_call.tool_name = str(name)

            if tool_call.tool_id and tool_call.tool_name and not tool_call.started:
                state.tool_block_counter += 1
                claude_index = state.text_block_index + state.tool_block_counter
                tool_call.output_index = str(claude_index)
                tool_call.started = True

                tool_name = tool_call.tool_name
                original_name = state.tool_name_map_inverse.get(tool_name, tool_name)
                tool_call.tool_name = original_name

                out.append(
                    _sse(
                        Constants.EVENT_CONTENT_BLOCK_START,
                        {
                            "type": Constants.EVENT_CONTENT_BLOCK_START,
                            "index": claude_index,
                            "content_block": {
                                "type": Constants.CONTENT_TOOL_USE,
                                "id": tool_call.tool_id,
                                "name": original_name,
                                "input": {},
                            },
                        },
                    )
                )

            if (
                isinstance(function_data, dict)
                and function_data.get("arguments") is not None
                and tool_call.started
            ):
                args_delta = str(function_data["arguments"])
                tool_call.args_buffer = state.args_assembler.append(tc_index, args_delta)

                if (
                    tool_call.output_index is not None
                    and not tool_call.json_sent
                    and ToolCallArgsAssembler.is_complete_json(tool_call.args_buffer)
                ):
                    out.append(
                        _sse(
                            Constants.EVENT_CONTENT_BLOCK_DELTA,
                            {
                                "type": Constants.EVENT_CONTENT_BLOCK_DELTA,
                                "index": tool_call.output_index,
                                "delta": {
                                    "type": Constants.DELTA_INPUT_JSON,
                                    "partial_json": tool_call.args_buffer,
                                },
                            },
                        )
                    )
                    tool_call.json_sent = True

    if finish_reason:
        if finish_reason == "length":
            state.final_stop_reason = Constants.STOP_MAX_TOKENS
        elif finish_reason in ["tool_calls", "function_call"]:
            state.final_stop_reason = Constants.STOP_TOOL_USE
        elif finish_reason == "stop":
            state.final_stop_reason = Constants.STOP_END_TURN
        else:
            state.final_stop_reason = Constants.STOP_END_TURN

    return out


def final_events(
    state: OpenAIToClaudeStreamState,
    *,
    usage: dict[str, Any] | None = None,
    include_message_stop: bool = True,
) -> list[str]:
    out: list[str] = []

    out.append(
        _sse(
            Constants.EVENT_CONTENT_BLOCK_STOP,
            {"type": Constants.EVENT_CONTENT_BLOCK_STOP, "index": state.text_block_index},
        )
    )

    for tool_data in state.current_tool_calls.values():
        if tool_data.started and tool_data.output_index is not None:
            out.append(
                _sse(
                    Constants.EVENT_CONTENT_BLOCK_STOP,
                    {
                        "type": Constants.EVENT_CONTENT_BLOCK_STOP,
                        "index": tool_data.output_index,
                    },
                )
            )

    usage_data = usage or {"input_tokens": 0, "output_tokens": 0}
    out.append(
        _sse(
            Constants.EVENT_MESSAGE_DELTA,
            {
                "type": Constants.EVENT_MESSAGE_DELTA,
                "delta": {"stop_reason": state.final_stop_reason, "stop_sequence": None},
                "usage": usage_data,
            },
        )
    )
    if include_message_stop:
        out.append(_sse(Constants.EVENT_MESSAGE_STOP, {"type": Constants.EVENT_MESSAGE_STOP}))

    return out
