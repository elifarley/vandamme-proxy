"""Type coercion and validation utilities for configuration loading.

This module provides utilities for loading environment variables according
to the ConfigSchema, including automatic type coercion and validation.

Errors are raised with clear messages to help users fix configuration issues.
"""

import os
from typing import Any

from src.core.config.schema import ConfigSchema, EnvVarSpec


class ConfigError(Exception):
    """Configuration validation error.

    This exception is raised when an environment variable fails validation
    or cannot be converted to the expected type.

    Attributes:
        env_var: The environment variable name
        value: The raw value that failed validation
        message: Human-readable error message
    """

    def __init__(self, env_var: str, value: str, message: str) -> None:
        self.env_var = env_var
        self.value = value
        self.message = message
        super().__init__(f"{env_var}={value}: {message}")


def _parse_bool(value: str) -> bool:
    """Parse string to boolean.

    Args:
        value: String value to parse

    Returns:
        True if value is "true", "1", "yes", or "on" (case-insensitive)
        False otherwise
    """
    return value.lower() in ("true", "1", "yes", "on")


def _parse_tuple(value: str) -> tuple[str, ...]:
    """Parse comma-separated string to tuple.

    Args:
        value: Comma-separated string (e.g., "model1,model2,model3")

    Returns:
        Tuple of non-empty strings
    """
    if not value:
        return ()
    parts = [part.strip() for part in value.split(",")]
    return tuple(part for part in parts if part)


def load_env_var(spec: EnvVarSpec) -> Any:
    """Load and validate a single environment variable.

    This function:
    1. Reads the environment variable
    2. Uses the default if not set
    3. Coerces the string value to the target type
    4. Runs custom validation if provided
    5. Raises ConfigError with clear message if anything fails

    Args:
        spec: Environment variable specification from ConfigSchema

    Returns:
        Validated and coerced value

    Raises:
        ConfigError: If validation fails or type conversion is impossible
    """
    raw_value = os.environ.get(spec.name)

    # Use default if not set
    if raw_value is None:
        return spec.default

    # Type coercion
    try:
        if spec.coerce is not None:
            # Use custom coercion function if provided
            value = spec.coerce(raw_value)
        elif spec.type_hint is bool:
            value = _parse_bool(raw_value)
        elif spec.type_hint is int:
            value = int(raw_value)
        elif spec.type_hint is float:
            value = float(raw_value)
        elif spec.type_hint is tuple:
            value = _parse_tuple(raw_value)
        else:
            # For str and other types, use as-is
            value = raw_value
    except (ValueError, TypeError) as e:
        raise ConfigError(
            spec.name,
            raw_value,
            f"Cannot convert to {spec.type_hint.__name__}: {e}",
        ) from e

    # Custom validation
    if spec.validator is not None:
        try:
            if not spec.validator(value):
                raise ConfigError(
                    spec.name,
                    raw_value,
                    f"Validation failed for type {spec.type_hint.__name__}",
                )
        except TypeError as e:
            # Validator raised an error (e.g., trying to compare None with int)
            raise ConfigError(
                spec.name,
                raw_value,
                f"Validation error: {e}",
            ) from e

    return value


def load_all_specs() -> dict[str, Any]:
    """Load all environment variables according to schema.

    This loads all defined environment variables, collecting any errors
    that occur. This allows showing all configuration errors at once
    rather than failing on the first error.

    Returns:
        Dictionary mapping env var names to validated values.
        Values that failed validation will be ConfigError instances.

    Note:
        This function does not raise exceptions for individual failures.
        Callers should check for ConfigError instances in the result.
    """
    result: dict[str, Any] = {}
    specs = ConfigSchema.all_specs()

    for name, spec in specs.items():
        try:
            result[name] = load_env_var(spec)
        except ConfigError as e:
            # Collect errors for later reporting
            result[name] = e

    return result


def validate_all() -> list[ConfigError]:
    """Validate all environment variables and return any errors.

    This is useful for startup validation to show all configuration
    issues before the application starts.

    Returns:
        List of ConfigError instances (empty if all valid)

    Example:
        errors = validate_all()
        if errors:
            for error in errors:
                print(f"Configuration error: {error}")
            sys.exit(1)
    """
    errors: list[ConfigError] = []
    loaded = load_all_specs()

    for _name, value in loaded.items():
        if isinstance(value, ConfigError):
            errors.append(value)

    return errors
