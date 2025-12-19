import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.alias_manager import AliasManager
    from src.core.config import Config

from src.core.config import config

logger = logging.getLogger(__name__)


class ModelManager:
    def __init__(self, config: "Config") -> None:
        self.config = config
        self.provider_manager = config.provider_manager
        self.alias_manager: AliasManager | None = getattr(config, "alias_manager", None)

    def resolve_model(self, model: str) -> tuple[str, str]:
        """Resolve model name to (provider, actual_model)

        Resolution process:
        1. Determine provider context (from explicit prefix or default provider)
        2. Apply alias resolution scoped to that provider (if aliases are configured)
        3. Parse provider prefix from resolved value
        4. Return provider and actual model name

        Returns:
            Tuple[str, str]: (provider_name, actual_model_name)
        """
        logger.debug(f"Starting model resolution for: '{model}'")

        # Apply alias resolution if available
        resolved_model = model
        if self.alias_manager and self.alias_manager.has_aliases():
            logger.debug(
                f"Alias manager available with {self.alias_manager.get_alias_count()} aliases"
            )

            # Check if model already has provider prefix
            if ":" not in model:
                # No provider prefix - resolve using default provider only
                default_provider = self.provider_manager.default_provider
                logger.debug(f"Resolving alias '{model}' with provider scope '{default_provider}'")
                alias_target = self.alias_manager.resolve_alias(model, provider=default_provider)
            else:
                # Has provider prefix - allow cross-provider resolution for backward compatibility
                logger.debug(f"Resolving alias '{model}' across all providers")
                alias_target = self.alias_manager.resolve_alias(model)

            if alias_target:
                logger.info(f"[ModelManager] Alias resolved: '{model}' -> '{alias_target}'")
                resolved_model = alias_target
            else:
                logger.debug(f"No alias match found for '{model}', using original model name")
        else:
            logger.debug("No aliases configured or alias manager unavailable")

        # Parse provider prefix
        logger.debug(f"Parsing provider prefix from resolved model: '{resolved_model}'")
        provider_name, actual_model = self.provider_manager.parse_model_name(resolved_model)
        logger.debug(f"Parsed provider: '{provider_name}', actual model: '{actual_model}'")

        # Log the final resolution result
        if resolved_model != model:
            logger.info(
                f"[ModelManager] Resolved: '{model}' -> "
                f"'{provider_name}:{actual_model}' (via alias)"
            )
        else:
            logger.debug(
                f"Model resolution complete: '{model}' -> "
                f"'{provider_name}:{actual_model}' (no alias)"
            )

        return provider_name, actual_model


model_manager = ModelManager(config)
