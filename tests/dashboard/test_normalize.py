from __future__ import annotations

from src.dashboard.normalize import (
    detect_metrics_disabled,
    error_rate,
    parse_metric_totals,
    provider_rows,
)


def test_error_rate_zero_when_no_requests() -> None:
    assert error_rate(total_requests=0, total_errors=10) == 0.0


def test_detect_metrics_disabled() -> None:
    assert detect_metrics_disabled({"# Message": "Request metrics logging is disabled"})


def test_parse_metric_totals_disabled_returns_zeros() -> None:
    totals = parse_metric_totals({"# Message": "Request metrics logging is disabled"})
    assert totals.total_requests == 0
    assert totals.total_errors == 0


def test_parse_metric_totals_prefers_total_tool_calls() -> None:
    totals = parse_metric_totals(
        {
            "summary": {
                "total_requests": 1,
                "total_tool_calls": 7,
                "tool_calls": 2,
            }
        }
    )
    assert totals.tool_calls == 7


def test_provider_rows_basic_shape() -> None:
    rows = provider_rows(
        {
            "total_requests": 10,
            "providers": {
                "openai": {
                    "rollup": {
                        "total": {
                            "requests": 7,
                            "errors": 1,
                            "input_tokens": 100,
                            "output_tokens": 200,
                        },
                        "streaming": {"average_duration_ms": 100},
                        "non_streaming": {"average_duration_ms": 150},
                    },
                    "models": {},
                },
                "anthropic": {
                    "rollup": {
                        "total": {
                            "requests": 3,
                            "errors": 0,
                            "input_tokens": 30,
                            "output_tokens": 40,
                        },
                        "streaming": {"average_duration_ms": 80},
                        "non_streaming": {"average_duration_ms": 120},
                    },
                    "models": {},
                },
            },
        }
    )

    assert {r["provider"] for r in rows} == {"openai", "anthropic"}
    openai = next(r for r in rows if r["provider"] == "openai")
    assert openai["requests"] == 7
    assert openai["errors"] == 1
