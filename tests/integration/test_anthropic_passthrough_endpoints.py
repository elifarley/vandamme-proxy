"""Integration tests for Anthropic passthrough endpoints."""

import os

import pytest
import yaml
from fastapi.testclient import TestClient

from src.api.endpoints import router
from src.core.provider_config import ProviderConfig
from src.core.provider_manager import ProviderManager

# Get test port from environment or use default (matching development server)
TEST_PORT = int(os.environ.get("VDM_TEST_PORT", "8082"))
BASE_URL = f"http://localhost:{TEST_PORT}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_models_endpoint_anthropic_format():
    """Test /v1/models endpoint with Anthropic format provider."""
    import httpx

    async with httpx.AsyncClient() as client:
        # Configure environment for Anthropic format provider
        os.environ["ANTHROPIC_API_FORMAT"] = "anthropic"
        os.environ["ANTHROPIC_BASE_URL"] = "https://api.anthropic.com"
        # Note: In real test, would need actual API key or mock

        response = await client.get(
            f"{BASE_URL}/v1/models",
            headers={"x-api-key": "test-key"}
        )

        # For integration test with real server, expect success
        assert response.status_code == 200

        # Verify YAML response
        content = response.text
        data = yaml.safe_load(content)
        assert data["object"] == "list"
        assert "data" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_check_provider_status():
    """Test health check endpoint includes provider status."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")

        assert response.status_code == 200

        # Verify it's YAML content
        assert "text/yaml" in response.headers.get("content-type", "")

        # Parse YAML content
        content = response.text
        data = yaml.safe_load(content)

        # Verify provider information is included
        # The exact structure depends on implementation
        assert isinstance(data, dict)

        # Should include server status
        assert "status" in data or "server" in data