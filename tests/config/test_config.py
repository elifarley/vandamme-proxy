"""Centralized test configuration constants for Vandamme Proxy tests.

This module provides a single source of truth for all test-related constants
to ensure consistency across the entire test suite.
"""

# Standardized test API keys - used across all test files
# These are NOT real API keys and should never be used in production
TEST_API_KEYS = {
    "OPENAI": "test-openai-key",
    "ANTHROPIC": "test-anthropic-key",
    "AZURE": "test-azure-key",
    "GLM": "test-glm-key",
    "BEDROCK": "test-bedrock-key",
    "VERTEX": "test-vertex-key",
    "POE": "test-poe-key",
    "CUSTOM": "test-custom-key",
}

# Test endpoints for various providers
TEST_ENDPOINTS = {
    "OPENAI": "https://api.openai.com",
    "ANTHROPIC": "https://api.anthropic.com",
    "AZURE": "https://your-resource.openai.azure.com",
    "GLM": "https://open.bigmodel.cn",
    "BEDROCK": "https://bedrock-runtime.us-east-1.amazonaws.com",
    "VERTEX": "https://generativelanguage.googleapis.com",
    "POE": "https://poe.com",
    "CUSTOM": "https://api.custom-provider.com",
}

# Default test configuration
DEFAULT_TEST_CONFIG = {
    "DEFAULT_PROVIDER": "openai",
    "HOST": "0.0.0.0",
    "PORT": "8082",
    "LOG_LEVEL": "DEBUG",
    "MAX_TOKENS_LIMIT": "4096",
    "MIN_TOKENS_LIMIT": "100",
    "REQUEST_TIMEOUT": "30",
    "MAX_RETRIES": "1",
}

# Common test headers
TEST_HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": TEST_API_KEYS["ANTHROPIC"],
}

# Test model configurations
TEST_MODELS = {
    "OPENAI_GPT4": "openai:gpt-4",
    "OPENAI_GPT35": "openai:gpt-3.5-turbo",
    "ANTHROPIC_CLAUDE": "anthropic:claude-3-5-sonnet-20241022",
}