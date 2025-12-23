from __future__ import annotations

from src.dashboard.ag_grid.transformers import format_model_page_url


def test_format_model_page_url_poe_uses_hyphenated_display_name_slug() -> None:
    url = format_model_page_url(
        template="https://poe.com/{display_name}/api",
        model_id="irrelevant",
        display_name="Kat Coder Pro",
    )
    assert url == "https://poe.com/Kat-Coder-Pro/api"


def test_format_model_page_url_non_poe_preserves_standard_url_encoding() -> None:
    url = format_model_page_url(
        template="https://openrouter.ai/{id}",
        model_id="foo bar",
        display_name="does not matter",
    )
    assert url == "https://openrouter.ai/foo%20bar"
