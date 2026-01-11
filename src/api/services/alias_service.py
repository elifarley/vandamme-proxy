"""Service layer for coordinating alias operations with provider filtering.

This service provides a clean separation between the domain layer (AliasManager)
and infrastructure layer (ProviderManager), eliminating circular dependencies
and improving testability.
"""

from dataclasses import dataclass
from logging import getLogger
from typing import TYPE_CHECKING

from src.core.constants import Constants

if TYPE_CHECKING:
    from src.core.alias_manager import AliasManager
    from src.core.provider_manager import ProviderManager

logger = getLogger(__name__)


@dataclass(frozen=True)
class ActiveAliasesResult:
    """Result of get_active_aliases with status information.

    Attributes:
        aliases: Nested tuple of (provider_name, ((alias, target), ...))
            for true immutability. The outer structure is ((provider, items), ...).
        is_success: True if the operation succeeded
        error_message: Optional error message if is_success is False
        provider_count: Number of active providers
        alias_count: Total number of aliases across all providers

    Note:
        This dataclass is frozen and uses tuples for all collections,
        ensuring true runtime immutability.
    """

    aliases: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    is_success: bool
    error_message: str | None = None
    provider_count: int = 0
    alias_count: int = 0


@dataclass(frozen=True)
class ProviderAliasInfo:
    """Information about a single provider's aliases.

    Attributes:
        provider: Provider name
        alias_count: Total number of aliases for this provider
        fallback_count: Number of aliases from fallback configuration
        aliases: Tuple of (alias_name, target_model, type) tuples.

    Note:
        This dataclass is frozen and uses a tuple for the aliases list,
        ensuring true runtime immutability.
    """

    provider: str
    alias_count: int
    fallback_count: int
    aliases: tuple[tuple[str, str, str], ...]  # (alias, target, type)


@dataclass(frozen=True)
class AliasSummary:
    """Complete alias summary for presentation.

    Attributes:
        total_aliases: Total number of aliases across all providers
        total_providers: Number of active providers
        total_fallbacks: Total number of fallback aliases
        providers: Tuple of provider-specific alias information.
        default_provider: Default provider name if set

    Note:
        This dataclass is frozen and uses a tuple for the providers list,
        ensuring true runtime immutability.
    """

    total_aliases: int
    total_providers: int
    total_fallbacks: int
    providers: tuple[ProviderAliasInfo, ...]
    default_provider: str | None


class AliasService:
    """Service for alias operations with active provider filtering.

    This service coordinates between AliasManager (domain) and ProviderManager
    (infrastructure) to provide aliases filtered to only active providers.

    The service layer pattern eliminates circular dependencies that would occur
    if AliasManager directly imported ProviderManager, and makes testing easier
    by allowing both dependencies to be mocked explicitly.

    Args:
        alias_manager: The alias manager instance containing all alias definitions
        provider_manager: The provider manager instance for determining active providers

    Attributes:
        alias_manager: Alias manager for accessing all configured aliases
        provider_manager: Provider manager for determining which providers are active
    """

    def __init__(
        self,
        alias_manager: "AliasManager",
        provider_manager: "ProviderManager",
    ):
        self.alias_manager = alias_manager
        self.provider_manager = provider_manager

    def _get_active_provider_names(self) -> set[str]:
        """Get set of active provider names (those with API keys configured).

        Returns:
            Set of provider names that have API keys configured.
            Returns empty set if ProviderManager is not available.

        Note:
            This method handles AttributeError gracefully (expected during early
            initialization). All other exceptions propagate.
        """
        try:
            providers = self.provider_manager.list_providers()
            # Filter out empty provider names
            return {name for name in providers if name}
        except AttributeError as e:
            # ProviderManager not initialized - expected during early init
            logger.debug("ProviderManager not initialized: %s", e)
            return set()

    def get_active_aliases(self) -> dict[str, dict[str, str]]:
        """Get aliases filtered to only active providers.

        Returns:
            Dict mapping provider name to their aliases, filtered to only
            providers that have API keys configured. Empty dict if no
            providers are active.

            Example:
                {
                    "openai": {"haiku": "gpt-4o-mini", "fast": "gpt-4o"},
                    "poe": {"sonnet": "glm-4.6"},
                }

        Note:
            This method returns an empty dict when provider filtering fails,
            ensuring the API only shows aliases that are actually usable.
        """
        active_providers = self._get_active_provider_names()

        if not active_providers:
            return {}

        all_aliases = self.alias_manager.get_all_aliases()

        return {
            provider: aliases.copy()
            for provider, aliases in all_aliases.items()
            if provider in active_providers
        }

    def get_active_aliases_result(self) -> ActiveAliasesResult:
        """Get aliases with unambiguous status information.

        .. deprecated::
            This method has no production callers. Use `get_active_aliases()`
            instead. Will be removed in a future version.

        Returns:
            ActiveAliasesResult containing aliases and status information.
            Unlike get_active_aliases(), this distinguishes between "no active
            providers" and "error occurred" scenarios.

        Note:
            Fail-fast behavior: unexpected exceptions (except AttributeError
            during early initialization) propagate to the caller. Only
            AttributeError from provider initialization is handled gracefully.
        """
        import warnings

        warnings.warn(
            "get_active_aliases_result() is deprecated and will be removed. "
            "Use get_active_aliases() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        active_providers = self._get_active_provider_names()

        if not active_providers:
            return ActiveAliasesResult(
                aliases=(),
                is_success=False,
                error_message="No active providers found",
                provider_count=0,
                alias_count=0,
            )

        all_aliases = self.alias_manager.get_all_aliases()

        filtered_aliases = {
            provider: aliases.copy()
            for provider, aliases in all_aliases.items()
            if provider in active_providers
        }

        provider_count = len(filtered_aliases)
        alias_count = sum(len(aliases) for aliases in filtered_aliases.values())

        return ActiveAliasesResult(
            aliases=tuple(
                (provider, tuple(sorted(aliases.items())))
                for provider, aliases in filtered_aliases.items()
            ),
            is_success=True,
            error_message=None,
            provider_count=provider_count,
            alias_count=alias_count,
        )

    def get_alias_summary(self, default_provider: str | None = None) -> AliasSummary:
        """Get structured alias summary for presentation.

        This method returns a data structure with all the information needed
        for display, without any formatting logic. The presenter layer is
        responsible for converting this to human-readable output.

        Args:
            default_provider: Optional default provider to highlight in output.

        Returns:
            AliasSummary with all display data (no formatting).
        """
        active_aliases = self.get_active_aliases()

        if not active_aliases:
            return AliasSummary(
                total_aliases=0,
                total_providers=0,
                total_fallbacks=0,
                providers=(),
                default_provider=default_provider,
            )

        # Get fallback aliases using public getter (no private attribute access)
        fallback_aliases = self.alias_manager.get_fallback_aliases()

        total_aliases = sum(len(aliases) for aliases in active_aliases.values())

        # Count fallback aliases and build provider info
        providers_info: list[ProviderAliasInfo] = []
        total_fallbacks = 0

        for provider in sorted(active_aliases.keys()):
            provider_aliases = active_aliases[provider]
            provider_fallbacks = fallback_aliases.get(provider, {})

            # Count and categorize aliases
            alias_list: list[tuple[str, str, str]] = []
            fallback_count = 0

            for alias, target in sorted(provider_aliases.items(), key=lambda x: x[0].lower()):
                is_fallback = alias in provider_fallbacks
                alias_type = (
                    Constants.ALIAS_TYPE_FALLBACK if is_fallback else Constants.ALIAS_TYPE_EXPLICIT
                )
                alias_list.append((alias, target, alias_type))
                if is_fallback:
                    fallback_count += 1

            total_fallbacks += fallback_count

            providers_info.append(
                ProviderAliasInfo(
                    provider=provider,
                    alias_count=len(provider_aliases),
                    fallback_count=fallback_count,
                    aliases=tuple(alias_list),
                )
            )

        return AliasSummary(
            total_aliases=total_aliases,
            total_providers=len(active_aliases),
            total_fallbacks=total_fallbacks,
            providers=tuple(providers_info),
            default_provider=default_provider,
        )
