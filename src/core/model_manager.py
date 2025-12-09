from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from src.core.config import Config

from src.core.config import config


class ModelManager:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.provider_manager = config.provider_manager

    def resolve_model(self, model: str) -> Tuple[str, str]:
        """Resolve model name to (provider, actual_model)

        Parses provider prefixes and applies model mappings for Claude models
        when no provider is specified.

        Returns:
            Tuple[str, str]: (provider_name, actual_model_name)
        """
        # Parse provider prefix
        provider_name, actual_model = self.provider_manager.parse_model_name(model)

        # If no provider prefix, check if we need to map Claude models
        if provider_name == self.provider_manager.default_provider:
            # Check if this is a Claude model that needs mapping
            model_lower = actual_model.lower()
            if "haiku" in model_lower:
                actual_model = self.config.small_model
            elif "sonnet" in model_lower:
                actual_model = self.config.middle_model
            elif "opus" in model_lower:
                actual_model = self.config.big_model

        return provider_name, actual_model


model_manager = ModelManager(config)
