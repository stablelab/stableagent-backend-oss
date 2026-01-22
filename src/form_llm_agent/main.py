"""
Main module for Form LLM Agent.

Provides easy integration with the existing FastAPI application.
Includes multi-provider LLM support via the integrated model factory.
"""
from .router import router
from .types import LangGraphResult
from .graph import stream_field_processing, create_simple_graph
from .model_factory import (
    create_chat_model,
    get_model_provider,
    is_anthropic_model,
    is_gemini_model,
    is_xai_model,
    is_anthropic_available,
    is_vertex_available
)

__all__ = [
    # Core functionality
    "router",
    "LangGraphResult",
    "stream_field_processing",
    "create_simple_graph",

    # Model factory functions
    "create_chat_model",
    "get_model_provider",
    "is_anthropic_model",
    "is_gemini_model",
    "is_xai_model",
    "is_anthropic_available",
    "is_vertex_available"
]
