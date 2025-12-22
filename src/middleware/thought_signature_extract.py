from __future__ import annotations

from typing import Any


def extract_message_from_response(response: dict[str, Any]) -> dict[str, Any]:
    """Normalize possible response shapes to an OpenAI-style message dict.

    Supported shapes:
    - {"choices": [{"message": {...}}]} (OpenAI chat completion)
    - {"message": {...}} (direct message wrapper)
    - {...} (flat dict)
    """

    if "choices" in response and response.get("choices"):
        choice0 = response["choices"][0]
        if isinstance(choice0, dict):
            msg = choice0.get("message")
            if isinstance(msg, dict):
                return msg
        return {}

    msg = response.get("message")
    if isinstance(msg, dict):
        return msg

    return response


def extract_reasoning_details(message: dict[str, Any]) -> list[dict[str, Any]]:
    reasoning_details = message.get("reasoning_details", [])
    if isinstance(reasoning_details, list):
        return [rd for rd in reasoning_details if isinstance(rd, dict)]
    return []


def extract_tool_call_ids(message: dict[str, Any]) -> set[str]:
    tool_calls = message.get("tool_calls", [])
    if not isinstance(tool_calls, list):
        return set()
    out: set[str] = set()
    for tc in tool_calls:
        if isinstance(tc, dict):
            tc_id = tc.get("id")
            if isinstance(tc_id, str) and tc_id:
                out.add(tc_id)
    return out
