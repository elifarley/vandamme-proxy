"""Request conversion pipeline.

This package provides a composable pipeline for converting Claude API requests
to OpenAI format. Each transformer in the pipeline handles a single responsibility,
making the conversion process more maintainable and testable.
"""

from src.conversion.pipeline.base import ConversionContext, RequestPipeline, RequestTransformer
from src.conversion.pipeline.factory import RequestPipelineFactory

__all__ = ["ConversionContext", "RequestPipeline", "RequestTransformer", "RequestPipelineFactory"]
