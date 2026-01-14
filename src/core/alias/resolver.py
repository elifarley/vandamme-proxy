"""Alias resolution strategy pattern implementation.

This module breaks down the monolithic resolve_alias() method into
focused, composable resolver classes following the Strategy Pattern.

Inspired by the middleware architecture in src/middleware/base.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from logging import getLogger
from typing import Any

logger = getLogger(__name__)


@dataclass(frozen=True)
class ResolutionContext:
    """Immutable context for alias resolution.

    Attributes:
        model: The original model name to resolve
        provider: Optional provider scope for resolution
        default_provider: Default provider from configuration
        aliases: All configured aliases {provider: {alias: target}}
        metadata: Additional context data for resolver communication
    """

    model: str
    provider: str | None
    default_provider: str
    aliases: dict[str, dict[str, str]]
    metadata: dict[str, Any] = field(default_factory=dict)

    def with_updates(self, **kwargs: Any) -> "ResolutionContext":
        """Create a new context with specified fields updated.

        Args:
            **kwargs: Fields to update in the new context

        Returns:
            A new ResolutionContext with updated values
        """
        return ResolutionContext(  # type: ignore[arg-type]
            model=kwargs.get("model", self.model),
            provider=kwargs.get("provider", self.provider),
            default_provider=kwargs.get("default_provider", self.default_provider),
            aliases=kwargs.get("aliases", self.aliases),
            metadata=kwargs.get("metadata", self.metadata.copy()),
        )


@dataclass(frozen=True)
class ResolutionResult:
    """Result of alias resolution.

    Attributes:
        resolved_model: The resolved model name (or original if no alias)
        provider: The provider to use
        was_resolved: True if an alias was found and resolved
        resolution_path: List of intermediate aliases for chained resolution
        matches: Optional list of matches for MatchRanker to process
    """

    resolved_model: str
    provider: str | None
    was_resolved: bool
    resolution_path: tuple[str, ...] = ()
    matches: tuple["Match", ...] = ()


@dataclass(frozen=True)
class Match:
    """A single alias match found by SubstringMatcher.

    Attributes:
        provider: Provider name where alias was found
        alias: The alias name that matched
        target: The target model the alias points to
        length: Length of the alias (for ranking)
        is_exact: True if exact match, False if substring
    """

    provider: str
    alias: str
    target: str
    length: int
    is_exact: bool


class AliasResolver(ABC):
    """Abstract base class for alias resolution strategies.

    Each resolver handles one specific aspect of alias resolution:
    - Literal prefix handling
    - Provider scope extraction
    - Substring matching
    - Cross-provider resolution
    - Chained alias resolution

    Resolvers are composed into a chain that processes resolution
    requests in priority order (lower priority values execute first).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for logging and debugging."""

    @property
    def priority(self) -> int:
        """Execution priority (lower values execute earlier).

        Default priority is 100. Subclasses should override to define
        their execution order in the resolution chain.
        """
        return 100

    @abstractmethod
    def can_resolve(self, context: ResolutionContext) -> bool:
        """Check if this resolver can handle the given context.

        Args:
            context: The resolution context

        Returns:
            True if this resolver should attempt resolution
        """
        pass

    @abstractmethod
    def resolve(self, context: ResolutionContext) -> ResolutionResult | None:
        """Resolve the alias, or None if cannot resolve.

        Args:
            context: The resolution context

        Returns:
            ResolutionResult if resolved, None to continue chain
        """
        pass


class LiteralPrefixResolver(AliasResolver):
    """Handles literal model names prefixed with '!' (bypass alias resolution).

    The '!' prefix allows users to bypass alias resolution and use
    the exact model name provided.

    Priority: 10 (highest - executes first to handle bypass requests).
    """

    @property
    def name(self) -> str:
        return "LiteralPrefixResolver"

    @property
    def priority(self) -> int:
        return 10

    def can_resolve(self, context: ResolutionContext) -> bool:
        return context.model.startswith("!")

    def resolve(self, context: ResolutionContext) -> ResolutionResult | None:
        logger.debug(f"[{self.name}] Processing literal model: '{context.model}'")

        literal_part = context.model[1:]  # Remove '!'
        if not literal_part:
            logger.debug(f"[{self.name}] Empty model after stripping '!'")
            return None

        # Parse provider from literal
        if ":" in literal_part:
            provider, model = literal_part.split(":", 1)
            resolved = f"{provider.lower()}:{model}"
        else:
            provider = context.provider or context.default_provider
            resolved = f"{provider}:{literal_part}" if provider else literal_part

        logger.debug(f"[{self.name}] Literal: '{context.model}' -> '{resolved}'")

        return ResolutionResult(
            resolved_model=resolved,
            provider=provider,
            was_resolved=False,  # Literal names are not alias resolution
            resolution_path=(),
        )


class ChainedAliasResolver(AliasResolver):
    """Resolves chained aliases (e.g., fast -> sonnet -> gpt-4o-mini).

    This resolver handles the case where an alias points to another alias,
    creating a chain that must be followed to reach the final model name.

    Cycle detection prevents infinite loops, and max_chain_length
    limits recursion depth.

    Priority: 20 (second - handles provider:model format).
    """

    DEFAULT_MAX_CHAIN_LENGTH: int = 10

    @property
    def priority(self) -> int:
        return 20

    def __init__(self, max_chain_length: int = DEFAULT_MAX_CHAIN_LENGTH) -> None:
        """Initialize chained alias resolver.

        Args:
            max_chain_length: Maximum number of alias chain steps to follow
        """
        self._max_chain_length = max_chain_length

    @property
    def name(self) -> str:
        return "ChainedAliasResolver"

    def can_resolve(self, context: ResolutionContext) -> bool:
        return ":" in context.model

    def resolve(self, context: ResolutionContext) -> ResolutionResult | None:
        resolved_model = context.model
        seen: set[str] = set()
        path: list[str] = []

        for iteration in range(self._max_chain_length):
            if ":" not in resolved_model:
                break

            potential_provider, model_part = resolved_model.split(":", 1)
            aliases_for_provider = context.aliases.get(potential_provider)
            if aliases_for_provider is None:
                break

            provider_scoped = f"{potential_provider}:{model_part.lower()}"
            if provider_scoped in seen:
                logger.warning(
                    f"[{self.name}] Cycle detected: "
                    f"{' -> '.join(sorted(seen))} -> {provider_scoped}"
                )
                # Return the last successfully resolved model (before cycle)
                # Don't increment path since we detected a cycle
                return ResolutionResult(
                    resolved_model=resolved_model,
                    provider=potential_provider,
                    was_resolved=True,
                    resolution_path=tuple(path),
                )

            if model_part.lower() not in aliases_for_provider:
                break

            seen.add(provider_scoped)
            target = aliases_for_provider[model_part.lower()]
            path.append(model_part)

            logger.debug(
                f"[{self.name}] Iteration {iteration + 1}: '{model_part}' is an alias -> '{target}'"
            )

            # Apply the same logic as the initial resolution
            if ":" in target:
                # Target has a provider prefix
                target_provider, _ = target.split(":", 1)
                resolved_model = target
            else:
                # Target is bare model name - add provider prefix
                resolved_model = f"{potential_provider}:{target}"

        if resolved_model == context.model:
            return None  # No resolution occurred

        provider = resolved_model.split(":", 1)[0] if ":" in resolved_model else context.provider

        # Check if we exhausted max iterations without full resolution
        # This happens when a chain is longer than _max_chain_length
        if iteration == self._max_chain_length - 1 and ":" in resolved_model:
            logger.warning(
                f"[{self.name}] Alias resolution exceeded max chain length "
                f"{self._max_chain_length}. Chain may be incomplete. "
                f"Stopped at: '{resolved_model}'"
            )

        return ResolutionResult(
            resolved_model=resolved_model,
            provider=provider,
            was_resolved=True,
            resolution_path=tuple(path),
        )


class SubstringMatcher(AliasResolver):
    """Performs case-insensitive substring matching against alias names.

    Creates variations (underscores/hyphens) and finds all matching aliases.
    Stores matches in context metadata for the MatchRanker to use.

    Priority: 30 (third - finds substring matches).
    """

    @property
    def name(self) -> str:
        return "SubstringMatcher"

    @property
    def priority(self) -> int:
        return 30

    def can_resolve(self, context: ResolutionContext) -> bool:
        return bool(context.aliases) and not context.model.startswith("!")

    def resolve(self, context: ResolutionContext) -> ResolutionResult | None:
        model_lower = context.model.lower()

        # Strip provider prefix for matching
        model_for_match = model_lower.split(":", 1)[1] if ":" in model_lower else model_lower

        # Create variations
        variations = {
            model_for_match,
            model_for_match.replace("_", "-"),
            model_for_match.replace("-", "_"),
        }

        # Determine search scope
        explicit_provider = model_lower.split(":", 1)[0] if ":" in model_lower else None
        search_provider = explicit_provider or (
            context.provider.lower() if context.provider else None
        )

        # Find matches
        matches: list[Match] = []
        for provider_name, provider_aliases in context.aliases.items():
            if search_provider and provider_name != search_provider:
                continue

            for alias, target in provider_aliases.items():
                alias_lower = alias.lower()
                for variation in variations:
                    if alias_lower in variation:
                        match_length = len(alias_lower)
                        is_exact = alias_lower == variation
                        matches.append(
                            Match(
                                provider=provider_name,
                                alias=alias,
                                target=target,
                                length=match_length,
                                is_exact=is_exact,
                            )
                        )
                        break

        if not matches:
            return None

        # Return matches in the result for the chain to pass to MatchRanker
        # This is the elegant way - the chain extracts matches and updates context
        return ResolutionResult(
            resolved_model=context.model,
            provider=context.provider,
            was_resolved=False,
            resolution_path=(),
            matches=tuple(matches),
        )


class MatchRanker(AliasResolver):
    """Ranks and selects the best match from candidate aliases.

    Sorts by:
    1. Exact match preference
    2. Longest match
    3. Default provider preference
    4. Alphabetical (provider, alias)

    Priority: 40 (fourth - ranks and selects best match from SubstringMatcher results).
    """

    @property
    def name(self) -> str:
        return "MatchRanker"

    @property
    def priority(self) -> int:
        return 40

    def can_resolve(self, context: ResolutionContext) -> bool:
        """MatchRanker processes matches found by SubstringMatcher."""
        return bool(context.metadata.get("substring_matches"))

    def resolve(
        self, context: ResolutionContext, matches: list[Match] | None = None
    ) -> ResolutionResult | None:
        """Rank and select the best match from context metadata.

        Args:
            context: The resolution context containing matches in metadata
            matches: Optional pre-fetched matches list (deprecated, use context.metadata)

        Returns:
            ResolutionResult with the best match
        """
        # Read matches from context metadata (new way) or parameter (legacy compat)
        if not matches:
            matches_from_context = context.metadata.get("substring_matches")
            if not matches_from_context:
                return None
            matches = list(matches_from_context)

        # Sort matches
        matches.sort(
            key=lambda m: (
                0 if m.is_exact else 1,  # Exact first
                -m.length,  # Longer first
                0 if m.provider == context.default_provider else 1,  # Default provider
                m.provider,  # Provider alphabetical
                m.alias,  # Alias alphabetical
            )
        )

        best = matches[0]
        target = best.target

        # Handle cross-provider aliases
        if ":" in target:
            potential_provider, _ = target.split(":", 1)
            if potential_provider in context.aliases:
                # Valid cross-provider alias
                resolved = target
            else:
                # Model name with ':', add provider prefix
                provider = best.provider
                resolved = f"{provider}:{target}"
        else:
            provider = best.provider
            resolved = f"{provider}:{target}"

        match_type = "exact" if best.is_exact else "substring"
        logger.info(
            f"[{self.name}] ({match_type} match for '{context.model}') "
            f"'{best.provider}:{best.alias}' -> '{resolved}'"
        )

        return ResolutionResult(
            resolved_model=resolved,
            provider=best.provider,
            was_resolved=True,
            resolution_path=(best.alias,),
        )


class AliasResolverChain:
    """Orchestrates alias resolution through a priority-based chain of resolvers.

    Inspired by MiddlewareChain in src/middleware/base.py.

    The chain processes resolution requests by passing the context
    through each resolver in priority order (lower priority values execute first).
    Context metadata allows resolvers to communicate between phases.

    The first resolver to return a non-None result wins.
    """

    def __init__(self, resolvers: list[AliasResolver]) -> None:
        """Initialize the resolver chain.

        Args:
            resolvers: List of resolvers to execute in priority order
        """
        self._resolvers = resolvers
        self._logger = getLogger(f"{__name__}.AliasResolverChain")

    def resolve(self, context: ResolutionContext) -> ResolutionResult:
        """Resolve alias through the priority-based chain of resolvers.

        Resolvers execute in priority order (lower values first).
        Context metadata allows SubstringMatcher to pass matches to MatchRanker.

        Args:
            context: The resolution context

        Returns:
            ResolutionResult from the first resolver that handles the request,
            or a default result if no resolver handles it
        """
        # Sort resolvers by priority (lower values execute first)
        sorted_resolvers = sorted(self._resolvers, key=lambda r: r.priority)

        # Track the current context (updated by resolvers that return new contexts)
        current_context = context

        for resolver in sorted_resolvers:
            if not resolver.can_resolve(current_context):
                continue

            self._logger.debug(
                f"[{resolver.name}] (priority={resolver.priority}) "
                f"Processing model='{current_context.model}' "
                f"provider={current_context.provider}"
            )

            result = resolver.resolve(current_context)

            # If resolver returned any result, handle it
            if result is not None:
                # If was_resolved=True (successful resolution), check for chains
                if result.was_resolved:
                    # After MatchRanker selects a match, check if it needs chain following
                    # Look for ChainedAliasResolver and re-run on the resolved model
                    for chain_resolver in sorted_resolvers:
                        if isinstance(chain_resolver, ChainedAliasResolver):
                            # Check if the resolved model might be an alias
                            resolved_model = result.resolved_model
                            provider = (
                                result.provider
                                or current_context.provider
                                or current_context.default_provider
                            )
                            if (
                                ":" in resolved_model
                                or resolved_model in current_context.aliases.get(provider, {})
                            ):
                                # Create a new context with the resolved model to follow chains
                                chain_context = ResolutionContext(
                                    model=resolved_model,
                                    provider=provider,
                                    default_provider=current_context.default_provider,
                                    aliases=current_context.aliases,
                                )
                                chain_result = chain_resolver.resolve(chain_context)
                                if chain_result and chain_result.was_resolved:
                                    # Merge the resolution paths
                                    merged_path = (
                                        result.resolution_path + chain_result.resolution_path
                                    )
                                    return ResolutionResult(
                                        resolved_model=chain_result.resolved_model,
                                        provider=chain_result.provider,
                                        was_resolved=True,
                                        resolution_path=merged_path,
                                    )
                    return result

                # If result has matches (from SubstringMatcher), store in context
                # and continue to MatchRanker
                if result.matches:
                    current_context = current_context.with_updates(
                        metadata={**current_context.metadata, "substring_matches": result.matches}
                    )
                    continue

                # Special case: LiteralPrefixResolver returns was_resolved=False
                # but with a modified resolved_model. This indicates "bypass" intent.
                # We check if the resolved_model differs from input.
                if result.resolved_model != current_context.model:
                    return result

        # No resolver handled it - return original
        self._logger.debug(f"No resolver matched, returning original: '{context.model}'")
        return ResolutionResult(
            resolved_model=context.model,
            provider=context.provider or context.default_provider,
            was_resolved=False,
            resolution_path=(),
        )
