"""Declarative schema for environment variable configuration.

This module provides a single source of truth for all environment variables,
including automatic type coercion, validation, and documentation generation.

The schema-based approach provides:
- Single definition point for all config options
- Automatic type coercion (str -> int/float/bool)
- Validation with clear error messages
- Self-documenting configuration
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EnvVarSpec:
    """Specification for a single environment variable.

    Attributes:
        name: Environment variable name (e.g., "PORT", "LOG_LEVEL")
        default: Default value if env var not set
        type_hint: Type for validation (int, str, float, bool)
        description: Human-readable description for docs
        validator: Optional custom validation function
        coerce: Optional function to convert string to target type
    """

    name: str
    default: Any
    type_hint: type
    description: str
    validator: Callable[[Any], bool] | None = None
    coerce: Callable[[str], Any] | None = None


class ConfigSchema:
    """Registry of all configuration environment variables.

    Each attribute is an EnvVarSpec that defines:
    - The environment variable name
    - Default value
    - Type for validation
    - Human-readable description
    - Optional validation rules
    """

    # === Server Settings ===

    HOST = EnvVarSpec(
        name="HOST",
        default="0.0.0.0",
        type_hint=str,
        description="Server host address to bind to",
    )

    PORT = EnvVarSpec(
        name="PORT",
        default=8082,
        type_hint=int,
        description="Server port number",
        validator=lambda x: 1 <= x <= 65535,
    )

    LOG_LEVEL = EnvVarSpec(
        name="LOG_LEVEL",
        default="INFO",
        type_hint=str,
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        validator=lambda x: x.upper() in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    # === Provider Settings ===

    VDM_DEFAULT_PROVIDER = EnvVarSpec(
        name="VDM_DEFAULT_PROVIDER",
        default="openai",
        type_hint=str,
        description="Default LLM provider to use",
    )

    PROXY_API_KEY = EnvVarSpec(
        name="PROXY_API_KEY",
        default=None,
        type_hint=str,
        description="Optional API key for proxy authentication (controls access TO the proxy)",
    )

    # === Timeout Settings ===

    REQUEST_TIMEOUT = EnvVarSpec(
        name="REQUEST_TIMEOUT",
        default=90,
        type_hint=int,
        description="Request timeout in seconds for non-streaming requests",
        validator=lambda x: x > 0,
    )

    STREAMING_READ_TIMEOUT_SECONDS = EnvVarSpec(
        name="STREAMING_READ_TIMEOUT_SECONDS",
        default=None,
        type_hint=float,
        description="Read timeout for streaming SSE requests (None = unlimited)",
        validator=lambda x: x is None or x > 0,
    )

    STREAMING_CONNECT_TIMEOUT_SECONDS = EnvVarSpec(
        name="STREAMING_CONNECT_TIMEOUT_SECONDS",
        default=30,
        type_hint=float,
        description="Connect timeout for streaming requests",
        validator=lambda x: x > 0,
    )

    MAX_RETRIES = EnvVarSpec(
        name="MAX_RETRIES",
        default=2,
        type_hint=int,
        description="Maximum retry attempts for failed requests",
        validator=lambda x: x >= 0,
    )

    # === Metrics & Token Limits ===

    LOG_REQUEST_METRICS = EnvVarSpec(
        name="LOG_REQUEST_METRICS",
        default=False,
        type_hint=bool,
        description="Enable request metrics logging",
    )

    MAX_TOKENS_LIMIT = EnvVarSpec(
        name="MAX_TOKENS_LIMIT",
        default=4096,
        type_hint=int,
        description="Maximum tokens allowed in requests",
        validator=lambda x: x > 0,
    )

    MIN_TOKENS_LIMIT = EnvVarSpec(
        name="MIN_TOKENS_LIMIT",
        default=100,
        type_hint=int,
        description="Minimum tokens allowed in requests",
        validator=lambda x: x > 0,
    )

    # === SSE Metrics Settings ===

    VDM_ACTIVE_REQUESTS_SSE_ENABLED = EnvVarSpec(
        name="VDM_ACTIVE_REQUESTS_SSE_ENABLED",
        default=False,
        type_hint=bool,
        description="Enable active requests SSE endpoint",
    )

    VDM_ACTIVE_REQUESTS_SSE_INTERVAL = EnvVarSpec(
        name="VDM_ACTIVE_REQUESTS_SSE_INTERVAL",
        default=0.5,
        type_hint=float,
        description="SSE broadcast interval in seconds",
        validator=lambda x: x > 0,
    )

    VDM_ACTIVE_REQUESTS_SSE_HEARTBEAT = EnvVarSpec(
        name="VDM_ACTIVE_REQUESTS_SSE_HEARTBEAT",
        default=30.0,
        type_hint=float,
        description="SSE heartbeat interval in seconds",
        validator=lambda x: x > 0,
    )

    # === Cache Settings ===

    CACHE_DIR = EnvVarSpec(
        name="CACHE_DIR",
        default="~/.cache/vandamme-proxy",
        type_hint=str,
        description="Directory for cache storage",
    )

    MODELS_CACHE_ENABLED = EnvVarSpec(
        name="MODELS_CACHE_ENABLED",
        default=True,
        type_hint=bool,
        description="Enable models cache",
    )

    MODELS_CACHE_TTL_HOURS = EnvVarSpec(
        name="MODELS_CACHE_TTL_HOURS",
        default=24,
        type_hint=int,
        description="Models cache TTL in hours",
        validator=lambda x: x > 0,
    )

    # === Alias Cache Settings ===

    ALIAS_CACHE_TTL_SECONDS = EnvVarSpec(
        name="ALIAS_CACHE_TTL_SECONDS",
        default=300.0,
        type_hint=float,
        description="Alias cache TTL in seconds",
        validator=lambda x: x > 0,
    )

    ALIAS_CACHE_MAX_SIZE = EnvVarSpec(
        name="ALIAS_CACHE_MAX_SIZE",
        default=1000,
        type_hint=int,
        description="Maximum entries in alias cache",
        validator=lambda x: x > 0,
    )

    ALIAS_MAX_CHAIN_LENGTH = EnvVarSpec(
        name="ALIAS_MAX_CHAIN_LENGTH",
        default=10,
        type_hint=int,
        description="Maximum alias chain length to prevent infinite loops",
        validator=lambda x: x > 0,
    )

    # === Middleware Settings ===

    GEMINI_THOUGHT_SIGNATURES_ENABLED = EnvVarSpec(
        name="GEMINI_THOUGHT_SIGNATURES_ENABLED",
        default=True,
        type_hint=bool,
        description="Enable Gemini thought signature middleware",
    )

    THOUGHT_SIGNATURE_MAX_CACHE_SIZE = EnvVarSpec(
        name="THOUGHT_SIGNATURE_MAX_CACHE_SIZE",
        default=10000,
        type_hint=int,
        description="Maximum entries in thought signature cache",
        validator=lambda x: x > 0,
    )

    THOUGHT_SIGNATURE_CACHE_TTL = EnvVarSpec(
        name="THOUGHT_SIGNATURE_CACHE_TTL",
        default=3600.0,
        type_hint=float,
        description="TTL in seconds for thought signature cache entries",
        validator=lambda x: x > 0,
    )

    THOUGHT_SIGNATURE_CLEANUP_INTERVAL = EnvVarSpec(
        name="THOUGHT_SIGNATURE_CLEANUP_INTERVAL",
        default=300.0,
        type_hint=float,
        description="Cache cleanup interval in seconds",
        validator=lambda x: x > 0,
    )

    # === Top Models Settings ===

    TOP_MODELS_SOURCE = EnvVarSpec(
        name="TOP_MODELS_SOURCE",
        default="openrouter",
        type_hint=str,
        description="Source for top models: 'openrouter', 'manual_rankings', or 'disabled'",
        validator=lambda x: x in ["openrouter", "manual_rankings", "disabled"],
    )

    TOP_MODELS_RANKINGS_FILE = EnvVarSpec(
        name="TOP_MODELS_RANKINGS_FILE",
        default=None,
        type_hint=str,
        description="Path to manual rankings JSON file (when TOP_MODELS_SOURCE=manual_rankings)",
    )

    TOP_MODELS_TIMEOUT_SECONDS = EnvVarSpec(
        name="TOP_MODELS_TIMEOUT_SECONDS",
        default=5.0,
        type_hint=float,
        description="Timeout in seconds for fetching top models from OpenRouter",
        validator=lambda x: x > 0,
    )

    TOP_MODELS_EXCLUDE = EnvVarSpec(
        name="TOP_MODELS_EXCLUDE",
        default="",
        type_hint=str,
        description="Comma-separated list of models to exclude from top models",
    )

    @classmethod
    def all_specs(cls) -> dict[str, EnvVarSpec]:
        """Get all environment variable specifications.

        Returns:
            Dictionary mapping spec names to EnvVarSpec objects
        """
        return {
            name: getattr(cls, name)
            for name in dir(cls)
            if isinstance(getattr(cls, name), EnvVarSpec)
        }

    @classmethod
    def get_spec(cls, name: str) -> EnvVarSpec | None:
        """Get specification for a specific env var by name.

        Args:
            name: The environment variable name (e.g., "PORT")

        Returns:
            EnvVarSpec if found, None otherwise
        """
        for spec in cls.all_specs().values():
            if spec.name == name:
                return spec
        return None

    @classmethod
    def generate_markdown_docs(cls) -> str:
        """Generate Markdown documentation for all environment variables.

        Returns:
            Markdown documentation string
        """
        lines = ["# Configuration Options\n\n"]
        lines.extend(
            [
                "This document is auto-generated from `ConfigSchema`.\n\n",
                "## Environment Variables\n\n",
            ]
        )

        specs = cls.all_specs()
        for _name, spec in sorted(specs.items()):
            default_repr = f"`{spec.default}`" if spec.default is not None else "None"
            lines.extend(
                [
                    f"### `{spec.name}`\n\n",
                    f"- **Type**: `{spec.type_hint.__name__}`\n",
                    f"- **Default**: {default_repr}\n",
                    f"- **Description**: {spec.description}\n\n",
                ]
            )

        return "\n".join(lines)
