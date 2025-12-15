"""Unit tests for API endpoints."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.models.claude import (
    ClaudeMessage,
    ClaudeMessagesRequest,
)


class TestCountToolCalls:
    """Test the count_tool_calls helper function."""

    def test_count_tool_calls_empty_request(self):
        """Test counting tool calls in a request with no tools."""
        from src.api.endpoints import count_tool_calls

        request = ClaudeMessagesRequest(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[
                ClaudeMessage(role="user", content="Hello"),
                ClaudeMessage(role="assistant", content="Hi there!"),
            ],
        )

        tool_use_count, tool_result_count = count_tool_calls(request)
        assert tool_use_count == 0
        assert tool_result_count == 0

    def test_count_tool_calls_with_string_content(self):
        """Test counting tool calls in a request with string content."""
        from src.api.endpoints import count_tool_calls

        request = ClaudeMessagesRequest(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[
                ClaudeMessage(role="user", content="Hello"),
                ClaudeMessage(role="assistant", content="Hi there!"),
            ],
        )

        tool_use_count, tool_result_count = count_tool_calls(request)
        assert tool_use_count == 0
        assert tool_result_count == 0

    def test_count_tool_calls_with_tool_uses(self):
        """Test counting tool calls in a request with tool_use blocks."""
        from src.api.endpoints import count_tool_calls

        request = ClaudeMessagesRequest(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[
                ClaudeMessage(
                    role="assistant",
                    content=[
                        {"type": "text", "text": "I'll help you with that."},
                        {
                            "type": "tool_use",
                            "id": "tool_1",
                            "name": "get_weather",
                            "input": {"location": "San Francisco"},
                        },
                        {
                            "type": "tool_use",
                            "id": "tool_2",
                            "name": "get_time",
                            "input": {"timezone": "UTC"},
                        },
                    ],
                ),
            ],
        )

        tool_use_count, tool_result_count = count_tool_calls(request)
        assert tool_use_count == 2
        assert tool_result_count == 0

    def test_count_tool_calls_with_tool_results(self):
        """Test counting tool calls in a request with tool_result blocks."""
        from src.api.endpoints import count_tool_calls

        request = ClaudeMessagesRequest(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[
                ClaudeMessage(
                    role="user",
                    content=[
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool_1",
                            "content": '{"temperature": "72°F", "conditions": "sunny"}',
                        },
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool_2",
                            "content": "12:00 PM",
                        },
                    ],
                ),
            ],
        )

        tool_use_count, tool_result_count = count_tool_calls(request)
        assert tool_use_count == 0
        assert tool_result_count == 2

    def test_count_tool_calls_mixed_content(self):
        """Test counting tool calls in a request with mixed content."""
        from src.api.endpoints import count_tool_calls

        request = ClaudeMessagesRequest(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[
                ClaudeMessage(role="user", content="What's the weather?"),
                ClaudeMessage(
                    role="assistant",
                    content=[
                        {"type": "text", "text": "I'll check the weather for you."},
                        {
                            "type": "tool_use",
                            "id": "tool_1",
                            "name": "get_weather",
                            "input": {"location": "San Francisco"},
                        },
                    ],
                ),
                ClaudeMessage(
                    role="user",
                    content=[
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool_1",
                            "content": '{"temperature": "72°F"}',
                        },
                    ],
                ),
            ],
        )

        tool_use_count, tool_result_count = count_tool_calls(request)
        assert tool_use_count == 1
        assert tool_result_count == 1

    def test_count_tool_calls_across_multiple_messages(self):
        """Test counting tool calls across multiple messages."""
        from src.api.endpoints import count_tool_calls

        request = ClaudeMessagesRequest(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[
                ClaudeMessage(
                    role="assistant",
                    content=[
                        {
                            "type": "tool_use",
                            "id": "tool_1",
                            "name": "get_weather",
                            "input": {"location": "NYC"},
                        },
                    ],
                ),
                ClaudeMessage(
                    role="assistant",
                    content=[
                        {
                            "type": "tool_use",
                            "id": "tool_2",
                            "name": "get_weather",
                            "input": {"location": "London"},
                        },
                    ],
                ),
                ClaudeMessage(
                    role="user",
                    content=[
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool_1",
                            "content": "65°F",
                        },
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool_2",
                            "content": "60°F",
                        },
                    ],
                ),
            ],
        )

        tool_use_count, tool_result_count = count_tool_calls(request)
        assert tool_use_count == 2
        assert tool_result_count == 2


class TestFilteredRunningTotals:
    """Test the filtered running totals functionality."""

    @pytest.fixture
    def mock_request_tracker(self):
        """Create a mock request tracker with test data."""
        from src.core.logging import ProviderModelMetrics, RequestTracker, SummaryMetrics

        tracker = RequestTracker()
        tracker.initialized = True
        tracker.total_completed_requests = 10

        # Setup summary metrics with provider/model data
        tracker.summary_metrics = SummaryMetrics()
        tracker.summary_metrics.total_requests = 10
        tracker.summary_metrics.total_input_tokens = 5000
        tracker.summary_metrics.total_output_tokens = 3000
        tracker.summary_metrics.total_cache_read_tokens = 100
        tracker.summary_metrics.total_cache_creation_tokens = 50
        tracker.summary_metrics.total_duration_ms = 5000
        tracker.summary_metrics.total_tool_uses = 5
        tracker.summary_metrics.total_tool_results = 3
        tracker.summary_metrics.total_tool_calls = 4

        # Add provider/model metrics
        tracker.summary_metrics.provider_model_metrics["openai:gpt-4"] = ProviderModelMetrics(
            total_requests=5,
            total_input_tokens=2500,
            total_output_tokens=1500,
            total_cache_read_tokens=50,
            total_cache_creation_tokens=25,
            total_duration_ms=2500,
            total_tool_uses=3,
            total_tool_results=2,
            total_tool_calls=2,
        )

        tracker.summary_metrics.provider_model_metrics["anthropic:claude-3-sonnet"] = (
            ProviderModelMetrics(
                total_requests=3,
                total_input_tokens=1500,
                total_output_tokens=900,
                total_cache_read_tokens=30,
                total_cache_creation_tokens=15,
                total_duration_ms=1500,
                total_tool_uses=1,
                total_tool_results=1,
                total_tool_calls=1,
            )
        )

        tracker.summary_metrics.provider_model_metrics["openai:gpt-3.5-turbo"] = (
            ProviderModelMetrics(
                total_requests=2,
                total_input_tokens=1000,
                total_output_tokens=600,
                total_cache_read_tokens=20,
                total_cache_creation_tokens=10,
                total_duration_ms=1000,
                total_tool_uses=1,
                total_tool_results=0,
                total_tool_calls=1,
            )
        )

        return tracker

    def test_get_filtered_running_totals_no_filters(self, mock_request_tracker):
        """Test getting running totals without any filters."""
        totals = mock_request_tracker.get_filtered_running_totals()

        assert totals["total_requests"] == 10
        assert totals["total_input_tokens"] == 5000
        assert totals["total_output_tokens"] == 3000
        assert totals["total_cache_read_tokens"] == 100
        assert totals["total_cache_creation_tokens"] == 50
        assert totals["total_tool_uses"] == 5
        assert totals["total_tool_results"] == 3
        assert totals["total_tool_calls"] == 4
        assert len(totals["provider_model_distribution"]) == 3
        assert totals["average_duration_ms"] == 500.0  # 5000ms / 10 requests

    def test_get_filtered_running_totals_by_provider(self, mock_request_tracker):
        """Test filtering running totals by provider."""
        totals = mock_request_tracker.get_filtered_running_totals(provider_filter="openai")

        # Should only include openai models (gpt-4 and gpt-3.5-turbo)
        assert totals["total_requests"] == 7  # 5 + 2
        assert totals["total_input_tokens"] == 3500  # 2500 + 1000
        assert totals["total_output_tokens"] == 2100  # 1500 + 600
        assert len(totals["provider_model_distribution"]) == 2

        provider_models = [pm["provider_model"] for pm in totals["provider_model_distribution"]]
        assert "openai:gpt-4" in provider_models
        assert "openai:gpt-3.5-turbo" in provider_models
        assert "anthropic:claude-3-sonnet" not in provider_models

    def test_get_filtered_running_totals_by_model(self, mock_request_tracker):
        """Test filtering running totals by model."""
        totals = mock_request_tracker.get_filtered_running_totals(model_filter="gpt-4")

        # Should only include gpt-4
        assert totals["total_requests"] == 5
        assert totals["total_input_tokens"] == 2500
        assert totals["total_output_tokens"] == 1500
        assert len(totals["provider_model_distribution"]) == 1

        provider_models = [pm["provider_model"] for pm in totals["provider_model_distribution"]]
        assert "openai:gpt-4" in provider_models
        assert "openai:gpt-3.5-turbo" not in provider_models
        assert "anthropic:claude-3-sonnet" not in provider_models

    def test_get_filtered_running_totals_by_provider_and_model(self, mock_request_tracker):
        """Test filtering running totals by both provider and model."""
        totals = mock_request_tracker.get_filtered_running_totals(
            provider_filter="openai", model_filter="gpt-4"
        )

        # Should only include openai:gpt-4
        assert totals["total_requests"] == 5
        assert totals["total_input_tokens"] == 2500
        assert totals["total_output_tokens"] == 1500
        assert len(totals["provider_model_distribution"]) == 1

        provider_models = [pm["provider_model"] for pm in totals["provider_model_distribution"]]
        assert "openai:gpt-4" in provider_models
        assert "openai:gpt-3.5-turbo" not in provider_models
        assert "anthropic:claude-3-sonnet" not in provider_models

    def test_get_filtered_running_totals_no_matches(self, mock_request_tracker):
        """Test filtering with no matching results."""
        totals = mock_request_tracker.get_filtered_running_totals(provider_filter="nonexistent")

        assert totals["total_requests"] == 0
        assert totals["total_input_tokens"] == 0
        assert totals["total_output_tokens"] == 0
        assert len(totals["provider_model_distribution"]) == 0
        assert totals["average_duration_ms"] == 0


class TestListAliases:
    """Test the /v1/aliases endpoint."""

    @pytest.mark.asyncio
    async def test_list_aliases_with_data(self):
        """Test listing aliases when aliases are configured."""
        import src.api.endpoints as endpoints_module
        from src.api.endpoints import list_aliases

        mock_alias_manager = MagicMock()
        mock_alias_manager.get_all_aliases.return_value = {
            "poe": {"haiku": "gpt-4o-mini", "sonnet": "gpt-4o"},
            "openai": {"fast": "gpt-4o-mini"},
        }

        # Patch the config in the endpoints module directly
        with patch.object(endpoints_module.config, "_alias_manager", mock_alias_manager):
            response = await list_aliases(_=None)

            assert response.status_code == 200
            content = json.loads(response.body)
            assert content["object"] == "list"
            assert "aliases" in content
            assert content["total"] == 3

            # Check aliases structure (grouped by provider)
            assert content["aliases"]["poe"]["haiku"] == "gpt-4o-mini"
            assert content["aliases"]["poe"]["sonnet"] == "gpt-4o"
            assert content["aliases"]["openai"]["fast"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_list_aliases_no_data(self):
        """Test listing aliases when no aliases are configured."""
        import src.api.endpoints as endpoints_module
        from src.api.endpoints import list_aliases

        mock_alias_manager = MagicMock()
        mock_alias_manager.get_all_aliases.return_value = {}

        # Patch the config in the endpoints module directly
        with patch.object(endpoints_module.config, "_alias_manager", mock_alias_manager):
            response = await list_aliases(_=None)

            assert response.status_code == 200
            content = json.loads(response.body)
            assert content["object"] == "list"
            assert content["aliases"] == {}
            assert content["total"] == 0

    @pytest.mark.asyncio
    async def test_list_aliases_error_handling(self):
        """Test error handling in list_aliases endpoint."""
        import src.api.endpoints as endpoints_module
        from src.api.endpoints import list_aliases

        mock_alias_manager = MagicMock()
        mock_alias_manager.get_all_aliases.side_effect = Exception("Test error")

        # Patch the config in the endpoints module directly
        with patch.object(endpoints_module.config, "_alias_manager", mock_alias_manager):
            response = await list_aliases(_=None)

            assert response.status_code == 500
            content = json.loads(response.body)
            assert content["type"] == "error"
            assert content["error"]["type"] == "api_error"
            assert "Failed to list aliases" in content["error"]["message"]
