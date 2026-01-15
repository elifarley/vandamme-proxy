"""Unit tests for endpoint utility functions.

This test file ensures the utility functions in src/api/endpoints.py work correctly.
"""

import logging

import pytest


@pytest.mark.unit
class TestIsTimeoutError:
    """Test the _is_timeout_error utility function."""

    def test_detects_httpx_timeout_exception(self):
        """Should detect httpx.TimeoutException."""
        import httpx

        from src.api.endpoints import _is_timeout_error

        exc = httpx.TimeoutException("Request timed out")
        assert _is_timeout_error(exc) is True

    def test_detects_httpx_read_timeout(self):
        """Should detect httpx.ReadTimeout."""
        import httpx

        from src.api.endpoints import _is_timeout_error

        exc = httpx.ReadTimeout("Read timed out")
        assert _is_timeout_error(exc) is True

    def test_returns_false_for_asyncio_timeout(self):
        """Should return False for asyncio.TimeoutError (different base class)."""
        import asyncio

        from src.api.endpoints import _is_timeout_error

        # asyncio.TimeoutError is NOT an httpx.TimeoutException
        # so it should return False
        exc = asyncio.TimeoutError("Async operation timed out")
        assert _is_timeout_error(exc) is False

    def test_returns_false_for_non_timeout_errors(self):
        """Should return False for exceptions that are not httpx.TimeoutException."""
        from src.api.endpoints import _is_timeout_error

        # Custom exceptions without timeout keywords should return False
        # String-based detection was removed as it was brittle
        exc = ValueError("Some other error")
        assert _is_timeout_error(exc) is False

        # Even custom exceptions with "timeout" in message are not detected
        # because we rely on proper exception types, not string matching
        class CustomError(Exception):
            pass

        exc = CustomError("Operation timed out")
        assert _is_timeout_error(exc) is False


@pytest.mark.unit
class TestMapTimeoutTo504:
    """Test the _map_timeout_to_504 utility function."""

    def test_returns_http_exception_with_504_status(self):
        """Should return HTTPException with status code 504."""
        from fastapi import HTTPException

        from src.api.endpoints import _map_timeout_to_504

        result = _map_timeout_to_504()

        assert isinstance(result, HTTPException)
        assert result.status_code == 504

    def test_includes_timeout_message_in_detail(self):
        """Should include helpful timeout message in exception detail."""
        from src.api.endpoints import _map_timeout_to_504

        result = _map_timeout_to_504()

        assert "timed out" in result.detail.lower()
        assert "REQUEST_TIMEOUT" in result.detail


@pytest.mark.unit
class TestLogTraceback:
    """Test the _log_traceback utility function."""

    def test_logs_traceback_to_default_logger(self, caplog):
        """Should log traceback to the default module logger."""
        from src.api.endpoints import _log_traceback

        with caplog.at_level(logging.ERROR):
            _log_traceback()

        # Should have logged an error
        assert any(record.levelname == "ERROR" for record in caplog.records)

    def test_logs_traceback_to_custom_logger(self, caplog):
        """Should log traceback to a custom logger when provided."""
        from src.api.endpoints import _log_traceback

        custom_logger = logging.getLogger("test.custom.logger")

        with caplog.at_level(logging.ERROR):
            _log_traceback(custom_logger)

        # Should have logged to the custom logger
        assert any(record.name == "test.custom.logger" for record in caplog.records)

    def test_logs_at_error_level(self, caplog):
        """Should log at ERROR level."""
        from src.api.endpoints import _log_traceback

        with caplog.at_level(logging.ERROR):
            _log_traceback()

        # All log records should be at ERROR level
        error_records = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(error_records) > 0


@pytest.mark.unit
class TestCountToolCalls:
    """Test the count_tool_calls utility function."""

    def test_counts_tool_use_blocks(self):
        """Should count tool_use content blocks."""
        from src.api.services.metrics_helper import count_tool_calls
        from src.models.claude import ClaudeContentBlockToolUse, ClaudeMessage

        request = type(
            "Request",
            (),
            {
                "messages": [
                    ClaudeMessage(
                        role="assistant",
                        content=[
                            ClaudeContentBlockToolUse(
                                type="tool_use",
                                id="tool-1",
                                name="search",
                                input={"query": "test"},
                            ),
                            ClaudeContentBlockToolUse(
                                type="tool_use",
                                id="tool-2",
                                name="calculate",
                                input={"expression": "1+1"},
                            ),
                        ],
                    )
                ]
            },
        )()

        tool_use_count, tool_result_count = count_tool_calls(request)

        assert tool_use_count == 2
        assert tool_result_count == 0

    def test_counts_tool_result_blocks(self):
        """Should count tool_result content blocks."""
        from src.api.services.metrics_helper import count_tool_calls
        from src.models.claude import ClaudeContentBlockToolResult, ClaudeMessage

        request = type(
            "Request",
            (),
            {
                "messages": [
                    ClaudeMessage(
                        role="user",
                        content=[
                            ClaudeContentBlockToolResult(
                                type="tool_result",
                                tool_use_id="tool-1",
                                content="Result 1",
                            ),
                            ClaudeContentBlockToolResult(
                                type="tool_result",
                                tool_use_id="tool-2",
                                content="Result 2",
                            ),
                            ClaudeContentBlockToolResult(
                                type="tool_result",
                                tool_use_id="tool-3",
                                content="Result 3",
                            ),
                        ],
                    )
                ]
            },
        )()

        tool_use_count, tool_result_count = count_tool_calls(request)

        assert tool_use_count == 0
        assert tool_result_count == 3

    def test_counts_mixed_blocks(self):
        """Should count both tool_use and tool_result blocks."""
        from src.api.services.metrics_helper import count_tool_calls
        from src.models.claude import (
            ClaudeContentBlockToolResult,
            ClaudeContentBlockToolUse,
            ClaudeMessage,
        )

        request = type(
            "Request",
            (),
            {
                "messages": [
                    ClaudeMessage(
                        role="assistant",
                        content=[
                            ClaudeContentBlockToolUse(
                                type="tool_use",
                                id="tool-1",
                                name="search",
                                input={"query": "test"},
                            ),
                        ],
                    ),
                    ClaudeMessage(
                        role="user",
                        content=[
                            ClaudeContentBlockToolResult(
                                type="tool_result",
                                tool_use_id="tool-1",
                                content="Result",
                            ),
                        ],
                    ),
                    ClaudeMessage(
                        role="assistant",
                        content=[
                            ClaudeContentBlockToolUse(
                                type="tool_use",
                                id="tool-2",
                                name="calculate",
                                input={"expression": "1+1"},
                            ),
                        ],
                    ),
                ]
            },
        )()

        tool_use_count, tool_result_count = count_tool_calls(request)

        assert tool_use_count == 2
        assert tool_result_count == 1

    def test_ignores_text_blocks(self):
        """Should ignore non-tool content blocks."""
        from src.api.services.metrics_helper import count_tool_calls
        from src.models.claude import ClaudeContentBlockText, ClaudeMessage

        request = type(
            "Request",
            (),
            {
                "messages": [
                    ClaudeMessage(
                        role="user",
                        content=[
                            ClaudeContentBlockText(type="text", text="Hello world"),
                            ClaudeContentBlockText(type="text", text="How are you?"),
                        ],
                    )
                ]
            },
        )()

        tool_use_count, tool_result_count = count_tool_calls(request)

        assert tool_use_count == 0
        assert tool_result_count == 0

    def test_handles_empty_messages(self):
        """Should handle messages list with no content blocks."""
        from src.api.services.metrics_helper import count_tool_calls
        from src.models.claude import ClaudeMessage

        request = type(
            "Request",
            (),
            {
                "messages": [
                    ClaudeMessage(role="user", content="Simple text message"),
                    ClaudeMessage(role="assistant", content="Response"),
                ]
            },
        )()

        tool_use_count, tool_result_count = count_tool_calls(request)

        assert tool_use_count == 0
        assert tool_result_count == 0

    def test_uses_constants_for_block_types(self):
        """Should use Constants.CONTENT_TOOL_USE and CONTENT_TOOL_RESULT."""
        from src.api.services.metrics_helper import count_tool_calls
        from src.models.claude import (
            ClaudeContentBlockToolResult,
            ClaudeContentBlockToolUse,
            ClaudeMessage,
        )

        request = type(
            "Request",
            (),
            {
                "messages": [
                    ClaudeMessage(
                        role="assistant",
                        content=[
                            ClaudeContentBlockToolUse(
                                type="tool_use",
                                id="tool-1",
                                name="test",
                                input={},
                            ),
                            ClaudeContentBlockToolResult(
                                type="tool_result",
                                tool_use_id="tool-1",
                                content="Result",
                            ),
                        ],
                    )
                ]
            },
        )()

        tool_use_count, tool_result_count = count_tool_calls(request)

        assert tool_use_count == 1
        assert tool_result_count == 1
