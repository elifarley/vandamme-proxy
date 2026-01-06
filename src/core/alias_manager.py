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
        self._default_provider: str | None = None  # Lazily loaded
        self._loaded: bool = False  # Track whether loading has occurred

        # Load fallback aliases first
        self._load_fallback_aliases()

        # Then load environment variable aliases (these take precedence)
        self._load_aliases()

        # Merge fallback aliases for any missing configurations
        self._merge_fallback_aliases()

        # Print summary of all loaded aliases (ENV + TOML)
        # Uses default_provider from _load_aliases() since this is called during init
        self._print_alias_summary(self._default_provider)

    def _load_aliases(self) -> None:
        """
        Load provider-specific <PROVIDER>_ALIAS_* environment variables.

        Expected format: <PROVIDER>_ALIAS_<NAME>=<target_model>
        Example: POE_ALIAS_HAIKU=grok-4.1-fast-non-reasoning
        """
        alias_pattern = re.compile(r"^(.+)_ALIAS_(.+)$")
        loaded_count = 0
        skipped_count = 0

        # Get default provider (lazily, without triggering ProviderManager init)
        from src.core.alias_config import AliasConfigLoader

        loader = AliasConfigLoader()
        defaults = loader.get_defaults()
        self._default_provider = defaults.get("default-provider", "openai")

        # NOTE: Intentionally do NOT call ProviderManager.load_provider_configs() here.
        # This allows AliasManager to be instantiated without requiring provider API keys.
        # Provider validation is done lazily when aliases are actually resolved.
        # In unit tests, ProviderManager is patched to provide mock _configs.

        for env_key, env_value in os.environ.items():
            match = alias_pattern.match(env_key)
            if match:
                provider, alias_name = match.groups()
                provider = provider.lower()
                alias_name = alias_name.lower()  # Store aliases in lowercase

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
                f"Loaded {total_aliases} explicit model aliases from {len(self.aliases)} providers "
                f"({skipped_count} skipped)"
            )

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
        # Get available providers for validation.
        #
        # IMPORTANT: Alias management must not require provider API keys.
        # Unit tests (and many offline workflows) intentionally run without any
        # *_API_KEY env vars. We therefore consider a provider "known" if it is
        # present in configuration defaults, config files, or env var *names*.
        from src.core.alias_config import AliasConfigLoader

        loader = AliasConfigLoader()
        config = loader.load_config()

        configured_providers = set((config.get("providers") or {}).keys())
        env_providers = {
            env_key[:-8].lower()
            for env_key in os.environ
            if env_key.endswith("_API_KEY") and not env_key.startswith("CUSTOM_")
        }
        available_providers = configured_providers | env_providers

        # Note: "default-provider" is a preference, not proof that a provider is enabled.
        # We intentionally do not treat it as "configured" for alias scoping.

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

    def _recursively_resolve(self, initial_model: str) -> tuple[str, int]:
        """
        Recursively resolve an alias through any chained references.

        This method handles chained aliases like: fast -> sonnet -> gpt-4o-mini
        It also detects and prevents cycles in the alias chain.

        Args:
            initial_model: The model to resolve (should have provider prefix)

        Returns:
            Tuple of (fully_resolved_model, step_count)
            step_count represents the number of alias resolutions performed
        """
        resolved_model = initial_model
        max_iterations = 10
        seen: set[str] = set()  # Track visited aliases for cycle detection

        for iteration in range(max_iterations):
            if ":" not in resolved_model:
                # No provider prefix - must be a concrete model
                break

            potential_provider, model_part = resolved_model.split(":", 1)

            # Check if this provider has any aliases configured
            maybe_aliases = self.aliases.get(potential_provider)
            if maybe_aliases is None:
                # Unknown provider - must be a concrete model
                break

            # Type narrowing: aliases_for_provider is now known to be dict[str, str]
            aliases_for_provider: dict[str, str] = maybe_aliases

            # Normalize for lookup (aliases are stored lowercase)
            model_part_lower = model_part.lower()

            # Check for cycle
            if model_part_lower in seen:
                logger.warning(
                    "[AliasManager] Cycle detected in alias resolution: "
                    f"{' -> '.join(seen)} -> {model_part}. "
                    f"Stopping at current resolved model: '{resolved_model}'"
                )
                break

            # Check if model_part is an alias key in this provider's aliases
            if model_part_lower not in aliases_for_provider:
                # Not an alias key - must be a concrete model name
                break

            # It's an alias! Resolve it and continue
            seen.add(model_part_lower)
            target = aliases_for_provider[model_part_lower]

            logger.debug(
                f"[AliasManager] Iteration {iteration + 1}: "
                f"'{model_part}' is an alias -> '{target}'"
            )

            # Apply the same logic as the initial resolution
            if ":" in target:
                # Target has a provider prefix
                target_provider, _ = target.split(":", 1)
                if target_provider in self.aliases:
                    # Valid cross-provider alias - use as-is
                    resolved_model = target
                else:
                    # Model name with ':' but not a provider prefix
                    resolved_model = f"{potential_provider}:{target}"
            else:
                # Bare model name - add provider prefix
                resolved_model = f"{potential_provider}:{target}"

        return resolved_model, len(seen)

    def resolve_alias(self, model: str, provider: str | None = None) -> str | None:
        """
        Resolve model name to alias value with case-insensitive substring matching.

        Resolution algorithm:
        1. Convert model name to lowercase
        2. Create variations of model name (with underscores and hyphens)
        3. Find aliases within provider scope where alias name matches any variation
        4. If exact match exists, return it immediately
        5. Otherwise, select longest matching substring
        6. If tie, select alphabetically first

        Args:
            model: The requested model name
            provider: Optional provider name to scope the search. If None, searches
                     across all providers (backward compatible behavior).

        Returns:
            The resolved alias target with provider prefix (e.g., "poe:grok-4.1-fast")
            or None if no match found
        """
        logger.debug(f"Attempting to resolve model alias for: '{model}'")

        if not model:
            logger.debug("No model name provided, cannot resolve alias")
            return None

        # Check for literal name prefix (!) - handle at the very beginning
        if model.startswith("!"):
            logger.debug(f"Literal model name detected, stripping '!' prefix: '{model}'")
            literal_part = model[1:]  # Remove the first character '!' (preserve original case)

            # Edge case: empty after stripping '!'
            if not literal_part:
                logger.debug("Empty model name after stripping '!', returning None")
                return None

            # Check if the literal part contains a provider prefix
            if ":" in literal_part:
                # Format: !provider:model
                literal_provider, literal_model = literal_part.split(":", 1)
                # Normalize provider to lowercase but preserve model case
                result = f"{literal_provider.lower()}:{literal_model}"
            else:
                # Format: !model (no provider specified)
                # If provider parameter is given, include it so downstream
                # parsing resolves consistently.
                result = f"{provider}:{literal_part}" if provider else literal_part

            logger.info(f"[AliasManager] literal: '{model}' -> '{result}'")
            return result

        if not self.aliases:
            logger.debug("No aliases configured, returning None")
            return None

        model_lower = model.lower()
        logger.debug(f"Model name (lowercase): '{model_lower}'")

        # If the caller already provided an explicit provider prefix (e.g. "kimi:sonnet"),
        # treat the portion after ":" as the alias search space. This prevents cross-provider
        # alias matches from hijacking an explicitly prefixed request.
        model_for_alias_match = model_lower.split(":", 1)[1] if ":" in model_lower else model_lower

        logger.debug(f"Model name for alias matching: '{model_for_alias_match}'")
        if provider:
            logger.debug(f"Provider scope: '{provider}'")

        # Create variations of the model name for matching
        # This allows "my_model" to match both "my-model" and "my_model" in the model name
        model_variations = {
            model_for_alias_match,  # Original (provider prefix stripped)
            model_for_alias_match.replace("_", "-"),  # Underscores to hyphens
            model_for_alias_match.replace("-", "_"),  # Hyphens to underscores
        }
        logger.debug(f"Model variations for matching: {model_variations}")

        # Determine if model has explicit provider prefix that overrides the provider parameter
        explicit_provider: str | None = model_lower.split(":", 1)[0] if ":" in model_lower else None

        # Normalize provider parameter to lowercase for consistent comparison
        normalized_provider = provider.lower() if provider else None

        # Use explicit provider if present, otherwise use the provider parameter
        search_provider = explicit_provider or normalized_provider

        # Find all matching aliases within the specified provider scope
        matches: list[tuple[str, str, str, int]] = []  # (provider, alias, target, match_length)

        # Log search scope for debugging
        if search_provider:
            provider_aliases = self.aliases.get(search_provider, {})
            total_aliases = len(provider_aliases)
            logger.debug(
                f"Checking {total_aliases} aliases for provider '{search_provider}' for matches"
            )
        else:
            total_aliases = sum(len(aliases) for aliases in self.aliases.values())
            logger.debug(
                f"Checking {total_aliases} configured aliases across {len(self.aliases)} providers "
                f"for matches"
            )

        for provider_name, provider_aliases in self.aliases.items():
            # Skip if we're scoping to a specific provider
            if search_provider and provider_name != search_provider:
                logger.debug(f"  Skipping provider '{provider_name}' (not in search scope)")
                continue
            logger.debug(
                f"  Checking provider '{provider_name}' with {len(provider_aliases)} aliases"
            )

            for alias, target in provider_aliases.items():
                alias_lower = alias.lower()
                logger.debug(f"    Testing alias: '{alias}' -> '{target}'")

                # Check if alias matches any variation of the model name
                for variation in model_variations:
                    if alias_lower in variation:
                        # Use the actual matched length from the variation
                        match_length = len(alias_lower)
                        matches.append((provider_name, alias, target, match_length))
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
                0 if x[0] == self._default_provider else 1,  # Prefer default provider
                x[0],  # Provider name alphabetically
                x[1],  # Alias name alphabetically
            )
        )

        best_match = matches[0]
        best_provider, best_alias, best_target, _ = best_match
        is_exact = any(best_alias.lower() == variation for variation in model_variations)
        match_type = "exact" if is_exact else "substring"

        # Return with provider prefix, but only if target doesn't already have one
        # Cross-provider aliases have targets like "zai:haiku" which should be returned as-is
        if ":" in best_target:
            # Check if this is a cross-provider alias (provider:model) or just a model name with ':'
            potential_provider, _ = best_target.split(":", 1)
            # Only treat as cross-provider if the potential provider is actually known
            if potential_provider in self.aliases:
                # Valid cross-provider alias - return as-is
                resolved_model = best_target
                logger.info(
                    "[AliasManager] (cross-provider %s match for '%s') '%s:%s' -> '%s'",
                    match_type,
                    model,
                    best_provider,
                    best_alias,
                    resolved_model,
                )
            else:
                # Model name contains ':' but it's not a provider prefix
                # (e.g., "openrouter/model:free")
                # Add source provider prefix
                result_provider = explicit_provider if explicit_provider else best_provider.lower()
                resolved_model = f"{result_provider}:{best_target}"
                logger.info(
                    "[AliasManager] (%s match for '%s') '%s:%s' -> '%s'",
                    match_type,
                    model,
                    best_provider,
                    best_alias,
                    resolved_model,
                )
        else:
            # Target is bare model name, add provider prefix
            result_provider = explicit_provider if explicit_provider else best_provider.lower()
            resolved_model = f"{result_provider}:{best_target}"
            logger.info(
                "[AliasManager] (%s match for '%s') '%s:%s' -> '%s'",
                match_type,
                model,
                best_provider,
                best_alias,
                resolved_model,
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

        # Recursive alias resolution: check if resolved_model is itself an alias
        # This handles chained aliases like: fast -> sonnet -> gpt-4o-mini
        resolved_model, steps = self._recursively_resolve(resolved_model)

        if steps:
            logger.info(
                f"[AliasManager] Fully resolved '{model}' through "
                f"{steps} step(s) -> '{resolved_model}'"
            )

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

    def print_common_model_mappings(self, default_provider: str) -> None:
        """Print resolved mappings for common Claude model names.

        Args:
            default_provider: The default provider name to use for resolution
        """
        common_models = ["haiku", "sonnet", "opus"]

        # Store all mappings first to prevent log lines from appearing between header and rows
        mappings: list[str] = []

        for model in common_models:
            # Do initial resolution (handles alias matching)
            resolved = self.resolve_alias(model, provider=default_provider)
            if resolved and ":" in resolved:
                # Count total resolution steps by resolving from the input model
                # We construct what the first alias match would look like (provider:model)
                # and then let _recursively_resolve count all steps from there
                first_alias = f"{default_provider}:{model}"
                _, steps = self._recursively_resolve(first_alias)

                provider, actual_model = resolved.split(":", 1)
                # For cross-provider resolution, show: "poe:haiku → zai:GLM-4.5-Air"
                # For same-provider, show: "poe:opus → gpt-5.1-codex-max"
                if provider != default_provider:
                    base_display = f"{default_provider}:{model} → {provider}:{actual_model}"
                else:
                    base_display = f"{default_provider}:{model} → {actual_model}"

                # Add step count indicator if non-shallow (more than 1 step)
                display_alias = f"{base_display} [{steps} steps]" if steps > 1 else base_display

                mappings.append(display_alias)
            else:
                # No alias found
                mappings.append(f"{default_provider}:{model} → Not configured")

        # Now print everything at once
        print("\n📝 Common Model Mappings (using default provider):")
        print(f"   {'Mapping':<65}")
        print(f"   {'-' * 65}")

        for mapping in mappings:
            print(f"   {mapping:<65}")

    def _print_alias_summary(self, default_provider: str | None = None) -> None:
        """Print an elegant summary of loaded model aliases grouped by provider.

        Args:
            default_provider: The default provider name to use for usage examples.
        """
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
            # Try to use the default provider for the example
            example_provider = default_provider if default_provider in self.aliases else None
            if not example_provider:
                # Fall back to the first provider with aliases (alphabetically)
                example_provider = sorted(self.aliases.keys())[0]

            first_alias = sorted(self.aliases[example_provider].keys())[0]
            first_target = self.aliases[example_provider][first_alias]
            is_fallback = first_alias in self._fallback_aliases.get(example_provider, {})

            print(
                f"      Example: model='{first_alias}' → resolves to "
                f"'{example_provider}:{first_target}'"
            )
            if is_fallback:
                print("                (from configuration defaults)")
        print("      Substring matching: 'my-{alias}-model' matches alias '{alias}'")
        print("      Configure <PROVIDER>_ALIAS_<NAME> environment variables to create aliases")
        print("      Or override defaults in vandamme-config.toml")
