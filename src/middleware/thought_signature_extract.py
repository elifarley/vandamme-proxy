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


def extract_reasoning_details_from_openai_format(tool_calls: list[dict]) -> list[dict[str, Any]]:
    """Extract thought signatures from tool_calls in OpenAI-compatible format.

    Google's OpenAI compatibility mode puts thought_signature in:
    tool_call.extra_content.google.thought_signature

    Returns list of reasoning_details entries with tool_call_ids tracking.
    """
    if not isinstance(tool_calls, list):
        return []

    reasoning_details = []
    for i, tc in enumerate(tool_calls):
        if not isinstance(tc, dict):
            continue

        # Check for OpenAI-compatible format
        extra_content = tc.get("extra_content", {})
        if not isinstance(extra_content, dict):
            continue

        google = extra_content.get("google", {})
        if not isinstance(google, dict):
            continue

        thought_signature = google.get("thought_signature")
        if thought_signature:
            tc_id = tc.get("id")
            reasoning_details.append(
                {
                    "thought_signature": thought_signature,
                    "tool_call_ids": {tc_id} if tc_id else set(),
                    "index": i,
                }
            )

    return reasoning_details


def extract_reasoning_details(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract reasoning_details from message (legacy format) or tool_calls (OpenAI format).

    Priority order:
    1. OpenAI format from tool_calls (extra_content.google.thought_signature)
    2. Legacy message-level format (reasoning_details field)
    """
    # First try OpenAI format from tool_calls
    tool_calls = message.get("tool_calls", [])
    openai_format = extract_reasoning_details_from_openai_format(tool_calls)
    if openai_format:
        return openai_format

    # Fallback to legacy message-level format
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
