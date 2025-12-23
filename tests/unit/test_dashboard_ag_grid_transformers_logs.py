import pytest


@pytest.mark.unit
def test_provider_badge_color_known_and_default():
    from src.dashboard.ag_grid.transformers import provider_badge_color

    assert provider_badge_color("openai") == "primary"
    assert provider_badge_color("OpenRouter") == "info"
    assert provider_badge_color("anthropic") == "danger"
    assert provider_badge_color("poe") == "success"
    assert provider_badge_color("unknown") == "secondary"
    assert provider_badge_color("") == "secondary"


@pytest.mark.unit
def test_logs_errors_row_data_shapes_fields():
    from src.dashboard.ag_grid.transformers import logs_errors_row_data

    rows = logs_errors_row_data(
        [
            {
                "seq": 1,
                "ts": 1710000000,
                "provider": "openai",
                "model": "gpt",
                "error_type": "timeout",
                "error": "boom",
                "request_id": "r1",
            }
        ]
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["provider_color"] == "primary"
    assert row["model"] == "gpt"
    assert row["error_type"] == "timeout"


@pytest.mark.unit
def test_logs_traces_row_data_formats_numbers_and_duration():
    from src.dashboard.ag_grid.transformers import logs_traces_row_data

    rows = logs_traces_row_data(
        [
            {
                "seq": 2,
                "ts": 1710000000,
                "provider": "poe",
                "model": "x",
                "status": "ok",
                "duration_ms": 1234,
                "input_tokens": 1200,
                "output_tokens": 34,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
                "tool_use_count": 2,
                "request_id": "r2",
                "is_streaming": True,
            }
        ]
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["provider_color"] == "success"
    assert row["duration_formatted"] == "1.23s"
    assert row["input_tokens"] == "1,200"
    assert row["output_tokens_raw"] == 34
