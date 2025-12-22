from __future__ import annotations

import httpx
import pytest

from src.dashboard.components.ag_grid import models_ag_grid
from src.dashboard.data_sources import DashboardConfig, fetch_models


class _DummyResponse:
    def __init__(self, status_code: int, json_payload: object):
        self.status_code = status_code
        self._json_payload = json_payload

    def json(self):
        return self._json_payload


@pytest.mark.asyncio
async def test_fetch_models_requests_openai_format(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = DashboardConfig(api_base_url="http://example")

    captured: dict[str, object] = {}

    async def fake_get(self, url: str, params=None, headers=None):  # noqa: ANN001
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return _DummyResponse(status_code=200, json_payload={"object": "list", "data": []})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    await fetch_models(cfg=cfg, provider=None)

    assert captured["url"] == "http://example/v1/models"
    assert isinstance(captured["params"], dict)
    assert captured["params"].get("format") == "openai"


@pytest.mark.parametrize(
    ("model_patch", "expected_url"),
    [
        # OpenAI-style nested metadata.
        (
            {"metadata": {"image": {"url": "https://example.com/icon.jpeg"}}},
            "https://example.com/icon.jpeg",
        ),
        # Flattened metadata variants.
        (
            {"metadata": {"image_url": "https://example.com/icon-flat.jpeg"}},
            "https://example.com/icon-flat.jpeg",
        ),
        (
            {"metadata": {"image": "https://example.com/icon-str.jpeg"}},
            "https://example.com/icon-str.jpeg",
        ),
        (
            {"metadata": {"icon": {"url": "https://example.com/icon-alt.jpeg"}}},
            "https://example.com/icon-alt.jpeg",
        ),
        # Top-level fallback.
        ({"image_url": "https://example.com/icon-top.jpeg"}, "https://example.com/icon-top.jpeg"),
    ],
)
def test_models_ag_grid_extracts_model_icon_url_variants(
    model_patch: dict[str, object],
    expected_url: str,
) -> None:
    models = [
        {
            "id": "Claude-Sonnet-4.5",
            "created": 1758868894776,
            "description": "Claude Sonnet 4.5 represents a major leap forward...",
            "owned_by": "Anthropic",
            "architecture": {"modality": "text,image->text"},
            "context_window": {"context_length": 128000, "max_output_tokens": 16384},
            "pricing": {"prompt": "0.0000026", "completion": "0.000013"},
            **model_patch,
        }
    ]

    grid = models_ag_grid(models)
    row = grid.rowData[0]

    assert row["owned_by"] == "Anthropic"
    assert row["architecture_modality"] == "text,image->text"
    assert row["description_full"].startswith("Claude Sonnet")
    assert row["description_preview"].startswith("Claude Sonnet")
    assert row["description_preview"].endswith("...")

    assert row["context_length"] == 128000
    assert row["max_output_tokens"] == 16384

    assert row["model_icon_url"] == expected_url

    # pricing is in USD/token; table shows USD per million tokens
    assert row["pricing_prompt_per_million"] == "2.60"
    assert row["pricing_completion_per_million"] == "13.00"

    # created is in ms; should be normalized to seconds as int
    assert isinstance(row["created"], int)
    assert row["created"] == 1758868894


def test_models_ag_grid_rejects_unsafe_icon_urls() -> None:
    models = [
        {
            "id": "Claude-Sonnet-4.5",
            "created": 1758868894776,
            "owned_by": "Anthropic",
            "metadata": {"image": {"url": "javascript:alert(1)"}},
        }
    ]

    grid = models_ag_grid(models)
    row = grid.rowData[0]

    assert row["model_icon_url"] is None
    # Ensure we still render the row and ID.
    assert row["id"] == "Claude-Sonnet-4.5"
