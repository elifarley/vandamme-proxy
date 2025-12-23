import pytest


@pytest.mark.unit
def test_top_models_row_data_shapes_fields():
    from src.dashboard.ag_grid.transformers import top_models_row_data

    rows = top_models_row_data(
        [
            {
                "provider": "openrouter",
                "sub_provider": "x",
                "id": "m1",
                "name": "Model 1",
                "context_window": 128000,
                "pricing": {"average_per_million": 1.23456},
                "capabilities": ["vision", "tools"],
            }
        ]
    )

    assert rows == [
        {
            "provider": "openrouter",
            "sub_provider": "x",
            "id": "m1",
            "name": "Model 1",
            "context_window": 128000,
            "avg_per_million": "1.235",
            "capabilities": "vision, tools",
        }
    ]
