import pytest

from src.conversion.content_utils import (
    extract_anthropic_text,
    extract_openai_text_parts,
    safe_json_loads,
)
from src.conversion.tool_call_delta import ToolCallArgsAssembler, ToolCallIdAllocator


@pytest.mark.unit
def test_safe_json_loads_returns_default_on_none() -> None:
    assert safe_json_loads(None, default={"ok": True}) == {"ok": True}


@pytest.mark.unit
def test_safe_json_loads_parses_valid_json() -> None:
    assert safe_json_loads('{"a": 1}', default={}) == {"a": 1}


@pytest.mark.unit
def test_extract_openai_text_parts_from_string() -> None:
    assert extract_openai_text_parts("hi") == [{"type": "text", "text": "hi"}]


@pytest.mark.unit
def test_extract_openai_text_parts_filters_non_text_parts() -> None:
    parts = extract_openai_text_parts(
        [{"type": "text", "text": "a"}, {"type": "image_url", "image_url": {"url": "x"}}]
    )
    assert parts == [{"type": "text", "text": "a"}]


@pytest.mark.unit
def test_extract_anthropic_text_concatenates_text_blocks() -> None:
    assert (
        extract_anthropic_text([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])
        == "ab"
    )


@pytest.mark.unit
def test_tool_call_args_assembler_detects_complete_json() -> None:
    assembler = ToolCallArgsAssembler()
    buf = assembler.append(0, '{"a"')
    assert ToolCallArgsAssembler.is_complete_json(buf) is False

    buf = assembler.append(0, ": 1}")
    assert ToolCallArgsAssembler.is_complete_json(buf) is True


@pytest.mark.unit
def test_tool_call_id_allocator_is_stable_per_index() -> None:
    allocator = ToolCallIdAllocator(id_prefix="toolu_msg")
    first = allocator.get(2)
    second = allocator.get(2)
    assert first == second


@pytest.mark.unit
def test_tool_call_id_allocator_uses_provided_id() -> None:
    allocator = ToolCallIdAllocator(id_prefix="toolu_msg")
    assert allocator.get(0, provided_id="abc") == "abc"
    # subsequent calls should keep the provided id
    assert allocator.get(0) == "abc"
