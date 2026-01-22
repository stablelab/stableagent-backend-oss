"""
Model factory for Criteria LLM Agent.

Re-exports the model factory from utils to maintain consistency
and avoid code duplication. Uses the same multi-provider LLM support.
"""

import sys
import os

# Import the shared model factory from utils
try:
    from src.utils.model_factory import (
        create_chat_model,
        is_anthropic_model,
        is_gemini_model,
        is_xai_model,
        get_model_provider,
        is_anthropic_available,
        is_vertex_available
    )
    
    __all__ = [
        "create_chat_model",
        "is_anthropic_model",
        "is_gemini_model",
        "is_xai_model",
        "get_model_provider",
        "is_anthropic_available",
        "is_vertex_available"
    ]
    
except ImportError as e:
    raise ImportError(
        f"Failed to import model factory from utils: {e}. "
        "Ensure utils.model_factory is properly accessible."
    )
