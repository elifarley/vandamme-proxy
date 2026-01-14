"""Tests for RequestOrchestrator."""

import time
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException

from src.api.orchestrator.request_orchestrator import RequestOrchestrator
from src.models.claude import ClaudeMessagesRequest


def _create_mock_provider_manager(
    provider_config: Mock | None = None,
    client: Mock | None = None,
    api_key: str | None = "sk-prov-key",
    has_middleware: bool = False,
    middleware_chain: Mock | None = None,
) -> Mock:
    """Create a mock provider manager with proper attribute control.

    Args:
        provider_config: Mock provider config to return
        client: Mock client to return
        api_key: API key to return from get_next_provider_api_key
        has_middleware: Whether to include middleware_chain attribute
        middleware_chain: Mock middleware chain to use

    Returns:
        A properly configured mock provider manager
    """
    if has_middleware and middleware_chain is not None:
        # Include middleware_chain in spec_set
        pm = Mock(
            spec_set=[
                "get_provider_config",
                "get_client",
                "get_next_provider_api_key",
                "middleware_chain",
            ]
        )
        pm.middleware_chain = middleware_chain
    else:
        # No middleware_chain attribute at all
        pm = Mock(spec_set=["get_provider_config", "get_client", "get_next_provider_api_key"])
    pm.get_provider_config = Mock(return_value=provider_config)
    pm.get_client = Mock(return_value=client)
    pm.get_next_provider_api_key = AsyncMock(return_value=api_key)
    return pm


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_prepares_basic_context() -> None:
    """Test that orchestrator can prepare a basic RequestContext."""
    request = ClaudeMessagesRequest(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello"}],
    )

    mock_http_request = MagicMock()
    mock_http_request.is_disconnected = AsyncMock(return_value=False)

    # Create mock config with provider_manager
    mock_provider_config = MagicMock(
        name="openai", uses_passthrough=False, is_anthropic_format=False
    )
    mock_config = MagicMock(
        log_request_metrics=False,
        provider_manager=_create_mock_provider_manager(
            provider_config=mock_provider_config,
            client=MagicMock(),
            api_key="sk-prov-key",
            has_middleware=False,
        ),
    )

    orchestrator = RequestOrchestrator(config=mock_config)

    with (
        patch("src.api.orchestrator.request_orchestrator.get_model_manager") as mock_mm,
        patch("src.api.orchestrator.request_orchestrator.convert_claude_to_openai") as mock_convert,
    ):
        # Setup mocks
        mock_mm.return_value.resolve_model.return_value = ("openai", "gpt-4o")
        mock_convert.return_value = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}],
            "_provider": "openai",
        }

        ctx = await orchestrator.prepare_request_context(
            request=request,
            http_request=mock_http_request,
            client_api_key=None,
        )

        assert ctx.request_id is not None
        assert ctx.provider_name == "openai"
        assert ctx.resolved_model == "gpt-4o"
        assert ctx.is_metrics_enabled is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_with_metrics_enabled() -> None:
    """Test that orchestrator initializes metrics when enabled."""
    request = ClaudeMessagesRequest(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello"}],
    )

    mock_http_request = MagicMock()
    mock_http_request.is_disconnected = AsyncMock(return_value=False)

    mock_tracker = MagicMock()
    mock_metrics = MagicMock(start_time_iso="2024-01-01T00:00:00Z", tool_result_count=0)
    mock_tracker.start_request = AsyncMock(return_value=mock_metrics)
    mock_tracker.update_last_accessed = AsyncMock()
    mock_tracker.end_request = AsyncMock()

    # Create mock config with provider_manager
    mock_provider_config = MagicMock(
        name="openai", uses_passthrough=False, is_anthropic_format=False
    )
    mock_config = MagicMock(
        log_request_metrics=True,
        provider_manager=_create_mock_provider_manager(
            provider_config=mock_provider_config,
            client=MagicMock(),
            api_key="sk-prov-key",
            has_middleware=False,
        ),
    )

    orchestrator = RequestOrchestrator(config=mock_config)

    with (
        patch(
            "src.api.orchestrator.request_orchestrator.get_request_tracker",
            return_value=mock_tracker,
        ),
        patch("src.api.orchestrator.request_orchestrator.get_model_manager") as mock_mm,
        patch("src.api.orchestrator.request_orchestrator.convert_claude_to_openai") as mock_convert,
        patch(
            "src.api.orchestrator.request_orchestrator.populate_request_metrics",
            return_value=(1, 100, 0),
        ),
    ):
        mock_mm.return_value.resolve_model.return_value = ("openai", "gpt-4o")
        mock_convert.return_value = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}],
            "_provider": "openai",
        }

        ctx = await orchestrator.prepare_request_context(
            request=request,
            http_request=mock_http_request,
            client_api_key=None,
        )

        assert ctx.is_metrics_enabled is True
        assert ctx.metrics is not None
        assert ctx.tracker is not None
        mock_tracker.start_request.assert_called_once()
        mock_tracker.update_last_accessed.assert_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_passthrough_validation_requires_client_key() -> None:
    """Test that orchestrator raises error when passthrough requires client API key."""
    request = ClaudeMessagesRequest(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello"}],
    )

    mock_http_request = MagicMock()
    mock_http_request.is_disconnected = AsyncMock(return_value=False)

    # Create mock config with provider_manager for passthrough provider
    mock_provider_config = MagicMock(
        name="anthropic", uses_passthrough=True, is_anthropic_format=True
    )
    mock_config = MagicMock(
        log_request_metrics=False,
        provider_manager=_create_mock_provider_manager(
            provider_config=mock_provider_config,
            client=MagicMock(),
            api_key=None,
            has_middleware=False,
        ),
    )

    orchestrator = RequestOrchestrator(config=mock_config)

    with (
        patch("src.api.orchestrator.request_orchestrator.get_model_manager") as mock_mm,
        patch("src.api.orchestrator.request_orchestrator.convert_claude_to_openai") as mock_convert,
        patch(
            "src.api.orchestrator.request_orchestrator.populate_request_metrics",
            return_value=(1, 100, 0),
        ),
    ):
        mock_mm.return_value.resolve_model.return_value = (
            "anthropic",
            "claude-3-5-sonnet-20241022",
        )
        mock_convert.return_value = {
            "model": "claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": "Hello"}],
            "_provider": "anthropic",
        }

        with pytest.raises(HTTPException) as exc_info:
            await orchestrator.prepare_request_context(
                request=request,
                http_request=mock_http_request,
                client_api_key=None,  # No client key provided
            )

        assert exc_info.value.status_code == 401
        assert "passthrough" in exc_info.value.detail.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_client_disconnect_before_processing() -> None:
    """Test that orchestrator handles client disconnection."""
    request = ClaudeMessagesRequest(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello"}],
    )

    mock_http_request = MagicMock()
    # Simulate client is disconnected
    mock_http_request.is_disconnected = AsyncMock(return_value=True)

    mock_tracker = MagicMock()
    mock_metrics = MagicMock(start_time_iso="2024-01-01T00:00:00Z", tool_result_count=0)
    mock_tracker.start_request = AsyncMock(return_value=mock_metrics)
    mock_tracker.update_last_accessed = AsyncMock()
    mock_tracker.end_request = AsyncMock()

    # Create mock config with provider_manager
    mock_provider_config = MagicMock(
        name="openai", uses_passthrough=False, is_anthropic_format=False
    )
    mock_config = MagicMock(
        log_request_metrics=True,
        provider_manager=_create_mock_provider_manager(
            provider_config=mock_provider_config,
            client=MagicMock(),
            api_key="sk-prov-key",
            has_middleware=False,
        ),
    )

    orchestrator = RequestOrchestrator(config=mock_config)

    with (
        patch(
            "src.api.orchestrator.request_orchestrator.get_request_tracker",
            return_value=mock_tracker,
        ),
        patch("src.api.orchestrator.request_orchestrator.get_model_manager") as mock_mm,
        patch("src.api.orchestrator.request_orchestrator.convert_claude_to_openai") as mock_convert,
        patch(
            "src.api.orchestrator.request_orchestrator.populate_request_metrics",
            return_value=(1, 100, 0),
        ),
    ):
        mock_mm.return_value.resolve_model.return_value = ("openai", "gpt-4o")
        mock_convert.return_value = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}],
            "_provider": "openai",
        }

        with pytest.raises(HTTPException) as exc_info:
            await orchestrator.prepare_request_context(
                request=request,
                http_request=mock_http_request,
                client_api_key=None,
            )

        assert exc_info.value.status_code == 499
        assert "disconnected" in exc_info.value.detail.lower()
        mock_tracker.end_request.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_applies_middleware_preprocessing() -> None:
    """Test that orchestrator applies middleware to requests."""
    request = ClaudeMessagesRequest(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello"}],
    )

    mock_http_request = MagicMock()
    mock_http_request.is_disconnected = AsyncMock(return_value=False)

    # Mock middleware chain
    mock_middleware_chain = MagicMock()
    mock_processed_context = MagicMock(
        messages=[{"role": "user", "content": "Modified by middleware"}]
    )
    mock_middleware_chain.process_request = AsyncMock(return_value=mock_processed_context)

    # Create mock config with provider_manager and middleware
    mock_provider_config = MagicMock(
        name="gemini", uses_passthrough=False, is_anthropic_format=False
    )
    mock_config = MagicMock(
        log_request_metrics=False,
        provider_manager=_create_mock_provider_manager(
            provider_config=mock_provider_config,
            client=MagicMock(),
            api_key="gemini-key",
            has_middleware=True,
            middleware_chain=mock_middleware_chain,
        ),
    )

    orchestrator = RequestOrchestrator(config=mock_config)

    with (
        patch("src.api.orchestrator.request_orchestrator.get_model_manager") as mock_mm,
        patch("src.api.orchestrator.request_orchestrator.convert_claude_to_openai") as mock_convert,
        patch(
            "src.api.orchestrator.request_orchestrator.populate_request_metrics",
            return_value=(1, 100, 0),
        ),
    ):
        mock_mm.return_value.resolve_model.return_value = ("gemini", "gemini-2.0-flash")
        mock_convert.return_value = {
            "model": "gemini-2.0-flash",
            "messages": [{"role": "user", "content": "Hello"}],
            "_provider": "gemini",
        }

        ctx = await orchestrator.prepare_request_context(
            request=request,
            http_request=mock_http_request,
            client_api_key=None,
        )

        # Verify middleware was called
        mock_middleware_chain.process_request.assert_called_once()
        # Verify messages were modified by middleware
        assert ctx.openai_messages == [{"role": "user", "content": "Modified by middleware"}]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_no_middleware_when_not_configured() -> None:
    """Test that orchestrator skips middleware when not configured."""
    request = ClaudeMessagesRequest(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello"}],
    )

    mock_http_request = MagicMock()
    mock_http_request.is_disconnected = AsyncMock(return_value=False)

    # Create mock config with provider_manager (no middleware)
    mock_provider_config = MagicMock(
        name="openai", uses_passthrough=False, is_anthropic_format=False
    )
    mock_config = MagicMock(
        log_request_metrics=False,
        provider_manager=_create_mock_provider_manager(
            provider_config=mock_provider_config,
            client=MagicMock(),
            api_key="sk-prov-key",
            has_middleware=False,
        ),
    )

    orchestrator = RequestOrchestrator(config=mock_config)

    with (
        patch("src.api.orchestrator.request_orchestrator.get_model_manager") as mock_mm,
        patch("src.api.orchestrator.request_orchestrator.convert_claude_to_openai") as mock_convert,
        patch(
            "src.api.orchestrator.request_orchestrator.populate_request_metrics",
            return_value=(1, 100, 0),
        ),
    ):
        mock_mm.return_value.resolve_model.return_value = ("openai", "gpt-4o")
        mock_convert.return_value = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}],
            "_provider": "openai",
        }

        # Should not raise any errors
        ctx = await orchestrator.prepare_request_context(
            request=request,
            http_request=mock_http_request,
            client_api_key=None,
        )

        assert ctx.request_id is not None


@pytest.mark.unit
def test_orchestrator_initialization() -> None:
    """Test RequestOrchestrator initialization."""
    # Default: metrics enabled
    orchestrator = RequestOrchestrator(config=MagicMock(log_request_metrics=True))
    assert orchestrator.config.log_request_metrics is True
    assert orchestrator.log_request_metrics is True

    # Metrics disabled
    orchestrator_no_metrics = RequestOrchestrator(config=MagicMock(log_request_metrics=False))
    assert orchestrator_no_metrics.config.log_request_metrics is False
    assert orchestrator_no_metrics.log_request_metrics is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_context_contains_all_required_fields() -> None:
    """Test that prepared context contains all expected fields."""
    request = ClaudeMessagesRequest(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello"}],
    )

    mock_http_request = MagicMock()
    mock_http_request.is_disconnected = AsyncMock(return_value=False)

    start = time.time()

    # Create mock config with provider_manager
    mock_provider_config = MagicMock(
        name="openai", uses_passthrough=False, is_anthropic_format=False
    )
    mock_config = MagicMock(
        log_request_metrics=False,
        provider_manager=_create_mock_provider_manager(
            provider_config=mock_provider_config,
            client=MagicMock(),
            api_key="sk-test-key",
            has_middleware=False,
        ),
    )

    orchestrator = RequestOrchestrator(config=mock_config)

    with (
        patch("src.api.orchestrator.request_orchestrator.get_model_manager") as mock_mm,
        patch("src.api.orchestrator.request_orchestrator.convert_claude_to_openai") as mock_convert,
        patch(
            "src.api.orchestrator.request_orchestrator.populate_request_metrics",
            return_value=(1, 150, 0),
        ),
    ):
        mock_mm.return_value.resolve_model.return_value = ("openai", "gpt-4o")
        mock_convert.return_value = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}],
            "_provider": "openai",
        }

        ctx = await orchestrator.prepare_request_context(
            request=request,
            http_request=mock_http_request,
            client_api_key=None,
        )

        # Verify all required fields are set
        assert ctx.request == request
        assert ctx.openai_request is not None
        assert ctx.request_id is not None
        assert ctx.http_request == mock_http_request
        assert ctx.provider_name == "openai"
        assert ctx.resolved_model == "gpt-4o"
        assert ctx.provider_config == mock_provider_config
        assert ctx.client_api_key is None
        assert ctx.provider_api_key == "sk-test-key"
        assert ctx.openai_client is not None
        assert ctx.metrics is None  # Metrics disabled
        assert ctx.tracker is None
        assert ctx.config is not None
        assert ctx.start_time >= start
        assert ctx.tool_use_count == 0
        assert ctx.tool_result_count == 0
        assert ctx.request_size == 150
        assert ctx.message_count == 1
