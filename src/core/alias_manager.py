"""
Model alias management for VDM_ALIAS_* environment variables.

This module provides flexible model name resolution with case-insensitive
substring matching, supporting provider prefixes in alias values.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)


class AliasManager:
    """
    Manages model aliases with case-insensitive substring matching.

    Supports VDM_ALIAS_* environment variables where:
    - VDM_ALIAS_FAST=openai:gpt-4o-mini
    - VDM_ALIAS_HAIKU=poe:gpt-4o-mini
    - VDM_ALIAS_CHAT=anthropic:claude-3-5-sonnet-20241022
    """

    def __init__(self) -> None:
        """Initialize AliasManager and load aliases from environment."""
        self.aliases: dict[str, str] = {}
        self._load_aliases()

    def _load_aliases(self) -> None:
        """
        Load VDM_ALIAS_* environment variables.

        Expected format: VDM_ALIAS_<NAME>=<target_model>
        Example: VDM_ALIAS_FAST=openai:gpt-4o-mini
        """
        alias_pattern = re.compile(r"^VDM_ALIAS_(.+)$")
        loaded_count = 0
        skipped_count = 0

        for env_key, env_value in os.environ.items():
            match = alias_pattern.match(env_key)
            if match:
                alias_name = match.group(1).lower()  # Store aliases in lowercase

                if not env_value or not env_value.strip():
                    logger.warning(f"Empty alias value for {env_key}, skipping")
                    skipped_count += 1
                    continue

                if self._validate_alias(alias_name, env_value):
                    self.aliases[alias_name] = env_value.strip()
                    loaded_count += 1
                    logger.debug(f"Loaded model alias: {alias_name} -> {env_value}")
                else:
                    logger.warning(
                        f"Invalid alias configuration for {env_key}={env_value}, skipping"
                    )
                    skipped_count += 1

        if self.aliases:
            logger.info(f"Loaded {loaded_count} model aliases ({skipped_count} skipped)")
            self._print_alias_summary()

    def _validate_alias(self, alias: str, value: str) -> bool:
        """
        Validate alias configuration.

        Args:
            alias: The alias name (lowercase)
            value: The alias target value

        Returns:
            True if valid, False otherwise
        """
        # Check for circular reference
        if alias == value.lower():
            logger.error(f"Circular alias reference detected: {alias} -> {value}")
            return False

        # Basic format validation - allow most characters in model names
        # Allow provider:model format or plain model names
        # Be permissive since model names can have various formats
        if not value or not value.strip():
            return False

        # Disallow characters that are clearly invalid for model names
        # Allow letters, numbers, hyphens, underscores, dots, slashes, colons
        # @ is not allowed as it's typically used for usernames or emails
        if "@" in value:
            logger.warning(f"Invalid alias target format (contains @): {value}")
            return False

        return True

    def resolve_alias(self, model: str) -> str | None:
        """
        Resolve model name to alias value with case-insensitive substring matching.

        Resolution algorithm:
        1. Convert model name to lowercase
        2. Create variations of model name (with underscores and hyphens)
        3. Find all aliases where alias name matches any variation
        4. If exact match exists, return it immediately
        5. Otherwise, select longest matching substring
        6. If tie, select alphabetically first

        Args:
            model: The requested model name

        Returns:
            The resolved alias target or None if no match found
        """
        logger.debug(f"Attempting to resolve model alias for: '{model}'")

        if not model:
            logger.debug("No model name provided, cannot resolve alias")
            return None

        if not self.aliases:
            logger.debug("No aliases configured, returning None")
            return None

        model_lower = model.lower()
        logger.debug(f"Model name (lowercase): '{model_lower}'")

        # Create variations of the model name for matching
        # This allows "my_model" to match both "my-model" and "my_model" in the model name
        model_variations = {
            model_lower,  # Original
            model_lower.replace("_", "-"),  # Underscores to hyphens
            model_lower.replace("-", "_"),  # Hyphens to underscores
        }
        logger.debug(f"Model variations for matching: {model_variations}")

        # Find all matching aliases
        matches: list[tuple[str, str, int]] = []  # (alias, target, match_length)

        logger.debug(f"Checking {len(self.aliases)} configured aliases for matches")

        for alias, target in self.aliases.items():
            alias_lower = alias.lower()
            logger.debug(f"  Testing alias: '{alias}' -> '{target}'")

            # Check if alias matches any variation of the model name
            for variation in model_variations:
                if alias_lower in variation:
                    # Use the actual matched length from the variation
                    match_length = len(alias_lower)
                    matches.append((alias, target, match_length))
                    logger.debug(
                        f"    ✓ Match found! Alias '{alias}' found in variation "
                        f"'{variation}' (length: {match_length})"
                    )
                    break  # Found a match, no need to check other variations
            else:
                logger.debug(f"    ✗ No match found for alias '{alias}'")

        if not matches:
            logger.debug(f"No aliases matched model name '{model}'")
            return None

        logger.debug(
            f"Found {len(matches)} matching aliases: {[(m[0], m[1], m[2]) for m in matches]}"
        )

        # Sort matches: exact match first, then by length, then alphabetically
        # For exact match, check against all variations
        matches.sort(
            key=lambda x: (
                (
                    0 if any(x[0].lower() == variation for variation in model_variations) else 1
                ),  # Exact match first
                -x[2],  # Longer match first
                x[0],  # Alphabetical order
            )
        )

        best_match = matches[0]
        is_exact = any(best_match[0].lower() == variation for variation in model_variations)
        match_type = "exact" if is_exact else "substring"

        logger.info(
            f"Resolved model alias '{model}' -> '{best_match[1]}' "
            f"(matched alias '{best_match[0]}' via {match_type} match)"
        )
        match_details = [
            (
                m[0],
                m[2],
                "exact" if any(m[0].lower() == v for v in model_variations) else "substring",
            )
            for m in matches[:3]
        ]
        logger.debug(f"  All matches sorted by priority: {match_details}")

        return best_match[1]

    def get_all_aliases(self) -> dict[str, str]:
        """
        Get all configured aliases.

        Returns:
            Dictionary of alias_name -> target_model
        """
        return self.aliases.copy()

    def has_aliases(self) -> bool:
        """
        Check if any aliases are configured.

        Returns:
            True if aliases exist, False otherwise
        """
        return bool(self.aliases)

    def get_alias_count(self) -> int:
        """
        Get the number of configured aliases.

        Returns:
            Number of aliases
        """
        return len(self.aliases)

    def _print_alias_summary(self) -> None:
        """Print an elegant summary of loaded model aliases"""
        if not self.aliases:
            return

        # Sort aliases by name for consistent display
        sorted_aliases = sorted(self.aliases.items(), key=lambda x: x[0].lower())

        print(f"\n✨ Model Aliases ({len(self.aliases)} configured):")
        print(f"   {'Alias':<20} {'Target Model':<40} {'Provider'}")
        print(f"   {'-' * 20} {'-' * 40} {'-' * 15}")

        for alias, target in sorted_aliases:
            # Extract provider from target if present
            if ":" in target:
                provider, model = target.split(":", 1)
                # Color code providers
                provider_colors = {
                    "openai": "\033[94m",  # Blue
                    "anthropic": "\033[92m",  # Green
                    "azure": "\033[93m",  # Yellow
                    "poe": "\033[95m",  # Magenta
                    "bedrock": "\033[96m",  # Cyan
                    "vertex": "\033[97m",  # White
                    "gemini": "\033[91m",  # Red
                }
                color = provider_colors.get(provider.lower(), "")
                reset = "\033[0m" if color else ""
                provider_display = f"{color}{provider}{reset}"
                model_display = model
            else:
                provider_display = "\033[90mdefault\033[0m"  # Gray
                model_display = target

            # Truncate long model names
            if len(model_display) > 38:
                model_display = model_display[:35] + "..."

            print(f"   {alias:<20} {model_display:<40} {provider_display}")

        # Add usage examples
        print("\n   💡 Use aliases in your requests:")
        print(
            f"      Example: model='sonnet' → resolves to '{sorted_aliases[0][1]}'"
            if sorted_aliases
            else "      Configure VDM_ALIAS_* environment variables to create aliases"
        )
        print("      Substring matching: 'my-sonnet-model' matches alias 'sonnet'")
