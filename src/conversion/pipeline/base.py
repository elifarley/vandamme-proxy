"""Base infrastructure for request conversion pipeline.

This module defines the core components of the pipeline:
- ConversionContext: Immutable context passed through transformers
- RequestTransformer: Abstract base for all transformation steps
- RequestPipeline: Orchestrator that executes transformers in sequence
"""

import dataclasses
import logging
from abc import ABC, abstractmethod
from typing import Any

from src.models.claude import ClaudeMessagesRequest


@dataclasses.dataclass(frozen=True)
class ConversionContext:
    """Immutable context passed through the conversion pipeline.

    Contains all input data and intermediate state needed for transformation.
    The frozen=True ensures immutability - transformers must return new instances
    rather than mutating the context.

    Attributes:
        claude_request: The original Claude API request.
        provider_name: The resolved provider name (e.g., "openai", "anthropic").
        openai_model: The resolved OpenAI model name.
        tool_name_map: Mapping of sanitized tool names (if enabled).
        tool_name_map_inverse: Inverse mapping for response conversion.
        openai_request: The OpenAI request being built (modified by each transformer).
        metadata: Optional metadata for debugging and extensibility.
    """

    claude_request: ClaudeMessagesRequest
    provider_name: str
    openai_model: str
    tool_name_map: dict[str, str]
    tool_name_map_inverse: dict[str, str]
    openai_request: dict[str, Any]
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


class RequestTransformer(ABC):
    """Base class for all request transformation steps.

    Each transformer handles a single, focused transformation of the request.
    Transformers must be pure functions - they should not mutate the input
    context but rather return a new ConversionContext with changes applied.
    """

    @abstractmethod
    def transform(self, context: ConversionContext) -> ConversionContext:
        """Transform the context and return a new instance.

        This method must NOT mutate the input context. Instead, it should
        create a new ConversionContext with the changes applied using
        dataclasses.replace().

        Args:
            context: The input context.

        Returns:
            A new ConversionContext with transformations applied.
        """
        pass

    @property
    def name(self) -> str:
        """Human-readable name for logging and debugging.

        Defaults to the class name. Override for custom names.
        """
        return self.__class__.__name__


class RequestPipeline:
    """Orchestrates the execution of transformers in sequence.

    Executes transformers in order with comprehensive error handling
    and debug logging. Each transformer receives the output of the
    previous transformer as its input.
    """

    def __init__(self, transformers: list[RequestTransformer]) -> None:
        """Initialize the pipeline with a list of transformers.

        Args:
            transformers: Ordered list of transformers to execute.
        """
        self.transformers = transformers
        self.logger = logging.getLogger(f"{__name__}.RequestPipeline")

    def execute(self, initial_context: ConversionContext) -> dict[str, Any]:
        """Execute all transformers and return the final OpenAI request.

        Args:
            initial_context: The starting context with all input data.

        Returns:
            The final OpenAI request dict after all transformations.

        Raises:
            Exception: If any transformer fails. The exception propagates
                with context about which transformer failed.
        """
        context = initial_context

        for i, transformer in enumerate(self.transformers):
            self.logger.debug(
                f"Running transformer [{i + 1}/{len(self.transformers)}]: {transformer.name}"
            )
            try:
                context = transformer.transform(context)
            except Exception as e:
                self.logger.error(
                    f"Transformer {transformer.name} failed: {e}",
                    exc_info=True,
                )
                raise

        self.logger.debug(f"Pipeline completed: {len(self.transformers)} transformers executed")
        return context.openai_request
