"""Tests for RequestContext dataclass."""

import pytest

from src.api.context.request_context import RequestContext, RequestContextBuilder
from src.core.provider_config import ProviderConfig
from src.models.claude import ClaudeMessagesRequest


@pytest.mark.unit
def test_request_context_creation() -> None:
    """Test that RequestContext can be created with all required fields."""
    request = ClaudeMessagesRequest(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello"}],
    )
    provider_config = ProviderConfig(
        name="openai",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
    )

    ctx = RequestContext(
        request=request,
        openai_request={"model": "gpt-4", "messages": []},
        request_id="test-123",
        http_request=None,
        provider_name="openai",
        resolved_model="gpt-4",
        provider_config=provider_config,
        client_api_key=None,
        provider_api_key="sk-test",
        tool_name_map_inverse=None,
        openai_client=None,
        metrics=None,
        tracker=None,
        config=None,
        start_time=0.0,
        tool_use_count=0,
        tool_result_count=0,
        request_size=100,
        message_count=1,
    )

    assert ctx.request_id == "test-123"
    assert ctx.provider_name == "openai"
    assert ctx.is_streaming is False


@pytest.mark.unit
def test_request_context_properties() -> None:
    """Test computed properties of RequestContext."""
    request = ClaudeMessagesRequest(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello"}],
        stream=True,
    )
    provider_config = ProviderConfig(
        name="anthropic",
        api_key="!PASSTHRU",
        base_url="https://api.anthropic.com",
        api_format="anthropic",
    )

    ctx = RequestContext(
        request=request,
        openai_request={
            "model": "claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": "Hello"}],
        },
        request_id="test-456",
        http_request=None,
        provider_name="anthropic",
        resolved_model="claude-3-5-sonnet-20241022",
        provider_config=provider_config,
        client_api_key="sk-ant-test",
        provider_api_key=None,
        tool_name_map_inverse=None,
        openai_client=None,
        metrics=None,
        tracker=None,
        config=None,
        start_time=0.0,
        tool_use_count=0,
        tool_result_count=0,
        request_size=100,
        message_count=1,
    )

    assert ctx.is_streaming is True
    assert ctx.is_metrics_enabled is False
    assert ctx.uses_passthrough is True
    assert ctx.is_anthropic_format is True
    assert ctx.openai_messages == [{"role": "user", "content": "Hello"}]


@pytest.mark.unit
def test_request_context_immutability() -> None:
    """Test that RequestContext is immutable and with_updates creates new instance."""
    from dataclasses import FrozenInstanceError

    request = ClaudeMessagesRequest(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello"}],
    )
    provider_config = ProviderConfig(
        name="openai",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
    )

    ctx = RequestContext(
        request=request,
        openai_request={"model": "gpt-4", "messages": []},
        request_id="test-789",
        http_request=None,
        provider_name="openai",
        resolved_model="gpt-4",
        provider_config=provider_config,
        client_api_key=None,
        provider_api_key="sk-test",
        tool_name_map_inverse=None,
        openai_client=None,
        metrics=None,
        tracker=None,
        config=None,
        start_time=0.0,
        tool_use_count=0,
        tool_result_count=0,
        request_size=100,
        message_count=1,
    )

    # Verify immutability - dataclass with frozen=True prevents direct assignment
    with pytest.raises(FrozenInstanceError):
        ctx.provider_name = "changed"  # type: ignore[misc]

    # Verify with_updates creates new instance
    new_ctx = ctx.with_updates(provider_name="anthropic")
    assert new_ctx.provider_name == "anthropic"
    assert ctx.provider_name == "openai"  # Original unchanged


@pytest.mark.unit
def test_request_context_builder() -> None:
    """Test RequestContextBuilder fluent API."""
    request = ClaudeMessagesRequest(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello"}],
    )
    provider_config = ProviderConfig(
        name="openai",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
    )

    builder = RequestContextBuilder()
    ctx = (
        builder.with_request(request)
        .with_openai_request({"model": "gpt-4", "messages": []})
        .with_request_id("builder-test-123")
        .with_http_request(None)
        .with_provider("openai", "gpt-4", provider_config)
        .with_auth(None, "sk-test")
        .with_tool_mapping(None)
        .with_client(None)
        .with_metrics(None, None, None)
        .with_timing(0.0, 0, 0, 100, 1)
        .build()
    )

    assert ctx.request_id == "builder-test-123"
    assert ctx.provider_name == "openai"
    assert ctx.resolved_model == "gpt-4"


@pytest.mark.unit
def test_request_context_builder_missing_required_fields() -> None:
    """Test that builder raises ValueError when required fields are missing."""
    builder = RequestContextBuilder()
    builder.with_request_id = "test-123"  # Only set non-required fields

    with pytest.raises(ValueError, match="Missing required fields"):
        builder.build()


@pytest.mark.unit
def test_request_context_openai_messages_empty() -> None:
    """Test openai_messages property returns empty list when no messages."""
    request = ClaudeMessagesRequest(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello"}],
    )
    provider_config = ProviderConfig(
        name="openai",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
    )

    ctx = RequestContext(
        request=request,
        openai_request={"model": "gpt-4"},  # No messages key
        request_id="test-empty",
        http_request=None,
        provider_name="openai",
        resolved_model="gpt-4",
        provider_config=provider_config,
        client_api_key=None,
        provider_api_key="sk-test",
        tool_name_map_inverse=None,
        openai_client=None,
        metrics=None,
        tracker=None,
        config=None,
        start_time=0.0,
        tool_use_count=0,
        tool_result_count=0,
        request_size=100,
        message_count=1,
    )

    assert ctx.openai_messages == []


@pytest.mark.unit
def test_request_context_with_provider_config_none() -> None:
    """Test that properties handle None provider_config gracefully."""
    request = ClaudeMessagesRequest(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello"}],
    )

    ctx = RequestContext(
        request=request,
        openai_request={"model": "gpt-4", "messages": []},
        request_id="test-none-config",
        http_request=None,
        provider_name="openai",
        resolved_model="gpt-4",
        provider_config=None,  # None provider_config
        client_api_key=None,
        provider_api_key="sk-test",
        tool_name_map_inverse=None,
        openai_client=None,
        metrics=None,
        tracker=None,
        config=None,
        start_time=0.0,
        tool_use_count=0,
        tool_result_count=0,
        request_size=100,
        message_count=1,
    )

    # Properties should return False when provider_config is None
    assert ctx.uses_passthrough is False
    assert ctx.is_anthropic_format is False
