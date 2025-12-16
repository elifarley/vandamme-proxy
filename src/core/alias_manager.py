"""
Model alias management for provider-specific <PROVIDER>_ALIAS_* environment variables.

This module provides flexible model name resolution with case-insensitive
substring matching, where aliases are scoped to specific providers.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)


class AliasManager:
    """
    Manages model aliases with case-insensitive substring matching.

    Supports provider-specific <PROVIDER>_ALIAS_* environment variables where:
    - POE_ALIAS_HAIKU=grok-4.1-fast-non-reasoning
    - OPENAI_ALIAS_FAST=gpt-4o-mini
    - ANTHROPIC_ALIAS_CHAT=claude-3-5-sonnet-20241022
    """

    def __init__(self) -> None:
        """Initialize AliasManager and load aliases from environment and fallback config."""
        self.aliases: dict[str, dict[str, str]] = {}  # {provider: {alias_name: target_model}}
        self._fallback_aliases: dict[str, dict[str, str]] = {}  # Cached fallback config

        # Load fallback aliases first
        self._load_fallback_aliases()

        # Then load environment variable aliases (these take precedence)
        self._load_aliases()

        # Merge fallback aliases for any missing configurations
        self._merge_fallback_aliases()

    def _load_aliases(self) -> None:
        """
        Load provider-specific <PROVIDER>_ALIAS_* environment variables.

        Expected format: <PROVIDER>_ALIAS_<NAME>=<target_model>
        Example: POE_ALIAS_HAIKU=grok-4.1-fast-non-reasoning
        """
        alias_pattern = re.compile(r"^(.+)_ALIAS_(.+)$")
        loaded_count = 0
        skipped_count = 0

        # Get available providers from ProviderManager for validation
        from src.core.provider_manager import ProviderManager

        provider_manager = ProviderManager()
        provider_manager.load_provider_configs()
        available_providers = set(provider_manager._configs.keys())

        for env_key, env_value in os.environ.items():
            match = alias_pattern.match(env_key)
            if match:
                provider, alias_name = match.groups()
                provider = provider.lower()
                alias_name = alias_name.lower()  # Store aliases in lowercase

                # Validate provider exists
                if provider not in available_providers:
                    logger.warning(f"Provider '{provider}' not found for alias {env_key}, skipping")
                    skipped_count += 1
                    continue

                if not env_value or not env_value.strip():
                    logger.warning(f"Empty alias value for {env_key}, skipping")
                    skipped_count += 1
                    continue

                if self._validate_alias(alias_name, env_value):
                    # Initialize provider dict if needed
                    if provider not in self.aliases:
                        self.aliases[provider] = {}

                    self.aliases[provider][alias_name] = env_value.strip()
                    loaded_count += 1
                    logger.debug(f"Loaded model alias: {provider}:{alias_name} -> {env_value}")
                else:
                    logger.warning(
                        f"Invalid alias configuration for {env_key}={env_value}, skipping"
                    )
                    skipped_count += 1

        if self.aliases:
            total_aliases = sum(len(aliases) for aliases in self.aliases.values())
            logger.info(
                f"Loaded {total_aliases} model aliases from {len(self.aliases)} providers "
                f"({skipped_count} skipped)"
            )
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

    def _load_fallback_aliases(self) -> None:
        """Load fallback aliases from TOML configuration files."""
        try:
            from src.core.alias_config import AliasConfigLoader

            loader = AliasConfigLoader()
            config = loader.load_config()
            providers_config = config.get("providers", {})

            # Extract aliases from provider configurations
            fallback_aliases = {}
            for provider_name, provider_config in providers_config.items():
                if isinstance(provider_config, dict) and "aliases" in provider_config:
                    aliases = provider_config["aliases"]
                    if isinstance(aliases, dict):
                        fallback_aliases[provider_name] = aliases

            self._fallback_aliases = fallback_aliases
            if self._fallback_aliases:
                total_fallback = sum(len(aliases) for aliases in self._fallback_aliases.values())
                logger.debug(f"Loaded {total_fallback} fallback aliases from configuration")
        except ImportError as e:
            logger.debug(f"Could not import AliasConfigLoader: {e}")
            self._fallback_aliases = {}
        except Exception as e:
            logger.warning(f"Failed to load fallback aliases: {e}")
            self._fallback_aliases = {}

    def _merge_fallback_aliases(self) -> None:
        """Merge fallback aliases for any missing configurations."""
        # Get available providers for validation
        from src.core.provider_manager import ProviderManager

        provider_manager = ProviderManager()
        provider_manager.load_provider_configs()
        available_providers = set(provider_manager._configs.keys())

        for provider, fallback_aliases in self._fallback_aliases.items():
            # Only apply fallbacks for configured providers
            if provider not in available_providers:
                logger.debug(f"Skipping fallback aliases for unconfigured provider '{provider}'")
                continue

            # Initialize provider dict if needed
            if provider not in self.aliases:
                self.aliases[provider] = {}

            # Add fallback aliases that weren't explicitly configured
            for alias, target in fallback_aliases.items():
                if alias not in self.aliases[provider]:
                    self.aliases[provider][alias] = target
                    logger.debug(f"Applied fallback alias: {provider}:{alias} -> {target}")

    def resolve_alias(self, model: str) -> str | None:
        """
        Resolve model name to alias value with case-insensitive substring matching.

        Resolution algorithm:
        1. Convert model name to lowercase
        2. Create variations of model name (with underscores and hyphens)
        3. Find all aliases across all providers where alias name matches any variation
        4. If exact match exists, return it immediately
        5. Otherwise, select longest matching substring
        6. If tie, select alphabetically first

        Args:
            model: The requested model name

        Returns:
            The resolved alias target with provider prefix (e.g., "poe:grok-4.1-fast")
            or None if no match found
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

        # Find all matching aliases across all providers
        matches: list[tuple[str, str, str, int]] = []  # (provider, alias, target, match_length)

        total_aliases = sum(len(aliases) for aliases in self.aliases.values())
        logger.debug(
            f"Checking {total_aliases} configured aliases across {len(self.aliases)} providers "
            f"for matches"
        )

        for provider, provider_aliases in self.aliases.items():
            logger.debug(f"  Checking provider '{provider}' with {len(provider_aliases)} aliases")

            for alias, target in provider_aliases.items():
                alias_lower = alias.lower()
                logger.debug(f"    Testing alias: '{alias}' -> '{target}'")

                # Check if alias matches any variation of the model name
                for variation in model_variations:
                    if alias_lower in variation:
                        # Use the actual matched length from the variation
                        match_length = len(alias_lower)
                        matches.append((provider, alias, target, match_length))
                        logger.debug(
                            f"      ✓ Match found! Alias '{alias}' found in variation "
                            f"'{variation}' (length: {match_length})"
                        )
                        break  # Found a match, no need to check other variations
                else:
                    logger.debug(f"      ✗ No match found for alias '{alias}'")

        if not matches:
            logger.debug(f"No aliases matched model name '{model}'")
            return None

        logger.debug(
            f"Found {len(matches)} matching aliases: {[(m[0], m[1], m[2], m[3]) for m in matches]}"
        )

        # Sort matches: exact match first, then by length, then alphabetically
        # For exact match, check against all variations
        matches.sort(
            key=lambda x: (
                (
                    0 if any(x[1].lower() == variation for variation in model_variations) else 1
                ),  # Exact match first
                -x[3],  # Longer match first
                x[0],  # Provider name alphabetically
                x[1],  # Alias name alphabetically
            )
        )

        best_match = matches[0]
        best_provider, best_alias, best_target, _ = best_match
        is_exact = any(best_alias.lower() == variation for variation in model_variations)
        match_type = "exact" if is_exact else "substring"

        # Return with provider prefix
        resolved_model = f"{best_provider}:{best_target}"

        logger.info(
            f"Resolved model alias '{model}' -> '{resolved_model}' "
            f"(matched alias '{best_alias}' from provider '{best_provider}' via {match_type} match)"
        )
        match_details = [
            (
                m[0],
                m[1],
                m[3],
                "exact" if any(m[1].lower() == v for v in model_variations) else "substring",
            )
            for m in matches[:3]
        ]
        logger.debug(f"  All matches sorted by priority: {match_details}")

        return resolved_model

    def get_all_aliases(self) -> dict[str, dict[str, str]]:
        """
        Get all configured aliases grouped by provider.

        Returns:
            Dictionary of {provider: {alias_name: target_model}}
        """
        return {provider: aliases.copy() for provider, aliases in self.aliases.items()}

    def get_explicit_aliases(self) -> dict[str, dict[str, str]]:
        """
        Get only explicitly configured aliases (excluding fallbacks).

        Returns:
            Dictionary of {provider: {alias_name: target_model}}
        """
        explicit_aliases = {}

        for provider, aliases in self.aliases.items():
            provider_explicit = {}
            fallback_aliases = self._fallback_aliases.get(provider, {})

            for alias, target in aliases.items():
                # Include only if not from fallback or explicitly overridden
                if alias not in fallback_aliases or target != fallback_aliases[alias]:
                    provider_explicit[alias] = target

            if provider_explicit:
                explicit_aliases[provider] = provider_explicit

        return explicit_aliases

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
            Number of aliases across all providers
        """
        return sum(len(aliases) for aliases in self.aliases.values())

    def _print_alias_summary(self) -> None:
        """Print an elegant summary of loaded model aliases grouped by provider"""
        if not self.aliases:
            return

        total_aliases = sum(len(aliases) for aliases in self.aliases.values())

        # Count fallback aliases
        total_fallbacks = sum(
            sum(1 for alias in aliases if alias in self._fallback_aliases.get(provider, {}))
            for provider, aliases in self.aliases.items()
        )

        print(
            f"\n✨ Model Aliases ({total_aliases} configured across {len(self.aliases)} providers):"
        )

        if total_fallbacks > 0:
            print(f"   📦 Includes {total_fallbacks} fallback defaults from configuration")

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

        # Sort providers by name for consistent display
        for provider in sorted(self.aliases.keys()):
            provider_aliases = self.aliases[provider]
            color = provider_colors.get(provider.lower(), "")
            reset = "\033[0m" if color else ""
            provider_display = f"{color}{provider}{reset}"

            fallback_aliases = self._fallback_aliases.get(provider, {})
            num_fallback = sum(1 for alias in provider_aliases if alias in fallback_aliases)
            len(provider_aliases) - num_fallback

            provider_info = f"{provider_display} ({len(provider_aliases)} aliases"
            if num_fallback > 0:
                provider_info += f", {num_fallback} fallbacks"
            provider_info += "):"

            print(f"\n   {provider_info}")
            print(f"   {'Alias':<20} {'Target Model':<40} {'Type'}")
            print(f"   {'-' * 20} {'-' * 40} {'-' * 10}")

            # Sort aliases within each provider
            for alias, target in sorted(provider_aliases.items(), key=lambda x: x[0].lower()):
                # Determine if this is a fallback alias
                alias_type = "fallback" if alias in fallback_aliases else "explicit"
                type_display = (
                    f"\033[90m{alias_type}\033[0m" if alias_type == "fallback" else alias_type
                )

                # Truncate long model names
                model_display = target
                if len(model_display) > 38:
                    model_display = model_display[:35] + "..."
                print(f"   {alias:<20} {model_display:<40} {type_display}")

        # Add usage examples
        print("\n   💡 Use aliases in your requests:")
        if self.aliases:
            # Find the first provider with aliases
            first_provider = sorted(self.aliases.keys())[0]
            first_alias = sorted(self.aliases[first_provider].keys())[0]
            first_target = self.aliases[first_provider][first_alias]
            is_fallback = first_alias in self._fallback_aliases.get(first_provider, {})

            print(
                f"      Example: model='{first_alias}' → resolves to "
                f"'{first_provider}:{first_target}'"
            )
            if is_fallback:
                print("                (from configuration defaults)")
        print("      Substring matching: 'my-{alias}-model' matches alias '{alias}'")
        print("      Configure <PROVIDER>_ALIAS_<NAME> environment variables to create aliases")
        print("      Or override defaults in vandamme-config.toml")
