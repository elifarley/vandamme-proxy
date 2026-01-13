"""Request pipeline factory.

Builds the default request conversion pipeline with all transformers.
"""

from src.conversion.pipeline.base import RequestPipeline, RequestTransformer
from src.conversion.pipeline.transformers.message_content import MessageContentTransformer
from src.conversion.pipeline.transformers.metadata import MetadataInjector
from src.conversion.pipeline.transformers.optional_fields import OptionalFieldsTransformer
from src.conversion.pipeline.transformers.system_message import SystemMessageTransformer
from src.conversion.pipeline.transformers.token_limit import TokenLimitTransformer
from src.conversion.pipeline.transformers.tool_choice import ToolChoiceTransformer
from src.conversion.pipeline.transformers.tool_schema import ToolSchemaTransformer


class RequestPipelineFactory:
    """Factory for creating request conversion pipelines.

    Provides a default pipeline configuration with all transformers in the
    correct order. Can be extended to create custom pipeline configurations.
    """

    @staticmethod
    def create_default() -> RequestPipeline:
        """Create the default request conversion pipeline.

        Transformers are executed in the following order:
        1. SystemMessageTransformer - Add system message
        2. MessageContentTransformer - Convert all messages
        3. TokenLimitTransformer - Validate max_tokens
        4. ToolSchemaTransformer - Convert tools
        5. ToolChoiceTransformer - Map tool_choice
        6. OptionalFieldsTransformer - Add optional fields
        7. MetadataInjector - Add provider metadata

        Returns:
            A configured RequestPipeline ready for execution.
        """
        transformers: list[RequestTransformer] = [
            SystemMessageTransformer(),
            MessageContentTransformer(),
            TokenLimitTransformer(),
            ToolSchemaTransformer(),
            ToolChoiceTransformer(),
            OptionalFieldsTransformer(),
            MetadataInjector(),
        ]
        return RequestPipeline(transformers)

    @staticmethod
    def create_custom(transformers: list[RequestTransformer]) -> RequestPipeline:
        """Create a custom pipeline with specified transformers.

        Args:
            transformers: Ordered list of transformers to execute.

        Returns:
            A configured RequestPipeline with custom transformers.
        """
        return RequestPipeline(transformers)
