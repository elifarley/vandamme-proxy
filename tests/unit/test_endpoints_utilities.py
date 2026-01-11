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

    def test_detects_timeout_in_string_message(self):
        """Should detect timeout from exception string message."""
        from src.api.endpoints import _is_timeout_error

        class CustomError(Exception):
            pass

        exc = CustomError("Operation timed out")
        assert _is_timeout_error(exc) is True

    def test_detects_timed_out_in_string_message(self):
        """Should detect 'timed out' phrase in exception message."""
        from src.api.endpoints import _is_timeout_error

        class CustomError(Exception):
            pass

        exc = CustomError("Connection timed out waiting for response")
        assert _is_timeout_error(exc) is True

    def test_detects_read_timeout_in_string_message(self):
        """Should detect 'read timeout' phrase in exception message."""
        from src.api.endpoints import _is_timeout_error

        class CustomError(Exception):
            pass

        exc = CustomError("Server read timeout error")
        assert _is_timeout_error(exc) is True

    def test_detects_connect_timeout_in_string_message(self):
        """Should detect 'connect timeout' phrase in exception message."""
        from src.api.endpoints import _is_timeout_error

        class CustomError(Exception):
            pass

        exc = CustomError("Failed to connect: connect timeout")
        assert _is_timeout_error(exc) is True

    def test_returns_false_for_non_timeout_errors(self):
        """Should return False for exceptions without timeout indicators."""
        from src.api.endpoints import _is_timeout_error

        exc = ValueError("Some other error")
        assert _is_timeout_error(exc) is False

    def test_case_insensitive_timeout_detection(self):
        """Should detect timeout regardless of case."""
        from src.api.endpoints import _is_timeout_error

        class CustomError(Exception):
            pass

        exc = CustomError("TIMEOUT occurred")
        assert _is_timeout_error(exc) is True


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
class TestIsErrorResponse:
    """Test the _is_error_response utility function."""

    def test_returns_false_for_non_dict(self):
        """Should return False for non-dict input."""
        from src.api.endpoints import _is_error_response

        result = _is_error_response("not a dict")
        assert result is False

        result = _is_error_response(None)
        assert result is False

        result = _is_error_response(123)
        assert result is False

    def test_returns_true_when_success_is_false(self):
        """Should detect explicit success: false flag."""
        from src.api.endpoints import _is_error_response

        response = {"success": False, "data": {}}
        assert _is_error_response(response) is True

    def test_returns_false_when_success_is_true(self):
        """Should return False when success is explicitly True."""
        from src.api.endpoints import _is_error_response

        response = {"success": True, "data": {}}
        assert _is_error_response(response) is False

    def test_returns_true_for_error_code_without_choices(self):
        """Should detect error code in OpenAI-style responses."""
        from src.api.endpoints import _is_error_response

        response = {"error": {"code": "invalid_api_key"}, "choices": []}
        assert _is_error_response(response) is True

    def test_returns_true_for_error_field_presence(self):
        """Should detect presence of error field."""
        from src.api.endpoints import _is_error_response

        response = {"error": {"message": "Something went wrong"}}
        assert _is_error_response(response) is True

    def test_returns_false_for_valid_response(self):
        """Should return False for valid responses."""
        from src.api.endpoints import _is_error_response

        response = {"choices": [{"message": {"content": "Hello"}}]}
        assert _is_error_response(response) is False

    def test_returns_false_for_empty_dict(self):
        """Should return False for empty dictionary."""
        from src.api.endpoints import _is_error_response

        result = _is_error_response({})
        assert result is False


@pytest.mark.unit
class TestCountToolCalls:
    """Test the count_tool_calls utility function."""

    def test_counts_tool_use_blocks(self):
        """Should count tool_use content blocks."""
        from src.api.endpoints import count_tool_calls
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
        from src.api.endpoints import count_tool_calls
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
        from src.api.endpoints import count_tool_calls
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
        from src.api.endpoints import count_tool_calls
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
        from src.api.endpoints import count_tool_calls
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
        from src.api.endpoints import count_tool_calls
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
