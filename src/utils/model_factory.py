"""Model factory for creating OpenAI or Anthropic models based on model name.

This module provides a factory function for creating chat models from either
OpenAI or Anthropic providers based on the model name. It automatically detects
the appropriate provider and configures the model with the specified parameters.

Key Features:
- Automatic provider detection based on model name
- Support for OpenAI and Anthropic chat models
- Tool binding capabilities
- JSON mode support for OpenAI models
- Environment variable configuration
"""

import os
from typing import Any, Optional, List, Union, TYPE_CHECKING


def extract_text_content(content: Any) -> str:
    """
    Normalize LLM message content to a plain text string.
    
    Gemini 3 models return content as a list of blocks with type/text structure
    instead of a plain string. This function handles both formats.
    
    Args:
        content: Message content - can be a string, list of content blocks, or other
        
    Returns:
        Extracted text content as a string
        
    Examples:
        >>> extract_text_content("Hello world")
        'Hello world'
        >>> extract_text_content([{"type": "text", "text": "Hello"}])
        'Hello'
    """
    if isinstance(content, list):
        # Handle Gemini 3 style: [{"type": "text", "text": "..."}]
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_value = part.get("text", "")
                if text_value:
                    return text_value
        # Fallback: join all text values from the list
        return " ".join([
            p.get("text", "") for p in content 
            if isinstance(p, dict) and p.get("text")
        ])
    if isinstance(content, str):
        return content
    return str(content) if content is not None else ""
from langchain_core.language_models.chat_models import BaseChatModel

if TYPE_CHECKING:
    from langchain_google_vertexai import ChatVertexAI
    from langchain_anthropic import ChatAnthropic

from langchain_openai import ChatOpenAI

# Import Anthropic for Claude models (optional)
try:
    from langchain_anthropic import ChatAnthropic
    _HAS_ANTHROPIC = True
except ImportError:
    ChatAnthropic = None  # type: ignore
    _HAS_ANTHROPIC = False

# Import Vertex AI for Gemini models (optional)
try:
    from langchain_google_vertexai import ChatVertexAI
    _HAS_VERTEX = True
except ImportError:
    ChatVertexAI = None  # type: ignore
    _HAS_VERTEX = False

# Import project/region/credentials from app config when available
try:
    from src.config.common_settings import PROJECT_ID as _PROJECT_ID, LOCATION as _LOCATION, credentials as _CREDENTIALS
except ImportError:
    _PROJECT_ID, _LOCATION, _CREDENTIALS = None, None, None


def is_anthropic_model(model_name: str) -> bool:
    """Check if the model name corresponds to an Anthropic model.

    Args:
        model_name: The name of the model to check.

    Returns:
        True if the model is from Anthropic, False otherwise.

    Examples:
        >>> is_anthropic_model("claude-3-opus")
        True
        >>> is_anthropic_model("gpt-4")
        False
    """
    anthropic_prefixes = [
        'claude-3',
        'claude-2',
        'claude-1',
        'claude-instant',
        'claude'
    ]
    return any(model_name.lower().startswith(prefix) for prefix in anthropic_prefixes)


def is_gemini_model(model_name: str) -> bool:
    """Check if the model name corresponds to a Gemini model.

    Args:
        model_name: The name of the model to check.

    Returns:
        True if the model is from Google Gemini, False otherwise.

    Examples:
        >>> is_gemini_model("gemini-1.5-pro")
        True
        >>> is_gemini_model("gemini-3-flash-preview")
        True
        >>> is_gemini_model("gemini-3-flash-preview")
        True
        >>> is_gemini_model("gpt-4")
        False
    """
    gemini_prefixes = [
        'gemini-3',    # Gemini 3 (requires global region)
        'gemini-2.5',  # Latest generation first
        'gemini-2.0',
        'gemini-1.5',
        'gemini-1.0',
        'gemini-pro',
        'gemini-flash',
        'gemini'
    ]
    return any(model_name.lower().startswith(prefix) for prefix in gemini_prefixes)


def requires_global_region(model_name: str) -> bool:
    """Check if the model requires the global region.
    
    Gemini 3 preview models require the 'global' location instead of
    regional endpoints like 'us-central1'.

    Args:
        model_name: The name of the model to check.

    Returns:
        True if the model requires global region, False otherwise.

    Examples:
        >>> requires_global_region("gemini-3-flash-preview")
        True
        >>> requires_global_region("gemini-3-flash-preview")
        False
    """
    global_region_models = [
        'gemini-3',  # All Gemini 3 models require global region
    ]
    return any(model_name.lower().startswith(prefix) for prefix in global_region_models)


def is_xai_model(model_name: str) -> bool:
    """Check if the model name corresponds to an XAI (Grok) model.

    Args:
        model_name: The name of the model to check.

    Returns:
        True if the model is from XAI (Grok), False otherwise.

    Examples:
        >>> is_xai_model("grok-2")
        True
        >>> is_xai_model("grok-3-mini")
        True
        >>> is_xai_model("gpt-4")
        False
    """
    xai_prefixes = [
        'grok-4-fast-reasoning',     # Latest fast reasoning model
        'grok-4-fast-non-reasoning',  # Latest fast non-reasoning model
        'grok-code-fast-1',          # Latest code model
        'grok-4',                    # General grok-4 prefix
        'grok-3',
        'grok-2',
        'grok-1',
        'grok-beta',
        'grok'
    ]
    return any(model_name.lower().startswith(prefix) for prefix in xai_prefixes)


def create_chat_model(
    model_name: Optional[str] = None,
    temperature: float = 0.7,
    api_tools: Optional[List] = None,
    json_mode: bool = False,
    project: Optional[str] = None,
    location: Optional[str] = None
) -> BaseChatModel:
    """Create a chat model instance (OpenAI, Anthropic, Gemini, or XAI) based on model name.

    This function automatically detects the appropriate provider based on the model
    name and creates the corresponding chat model instance. It supports tool binding
    and JSON mode for compatible models.

    Args:
        model_name: Name of the model to create. If None, uses environment defaults.
                   Examples: "gpt-4", "claude-3-opus", "gemini-1.5-pro", "grok-2"
        temperature: Temperature setting for the model (0.0-2.0 for most models).
                    Controls randomness in responses.
        api_tools: Optional list of tools to bind to the model for function calling.
        json_mode: Sets JSON mode for OpenAI/XAI models. Note: Not supported for Anthropic/Gemini.
        project: Google Cloud project ID for Gemini models (optional).
        location: Google Cloud location for Gemini models (optional).

    Returns:
        Configured chat model instance (ChatOpenAI, ChatAnthropic, or ChatVertexAI) 
        with tools bound if provided.

    Raises:
        ValueError: If required API keys or configuration is not set.
        RuntimeError: If required dependencies are not installed.

    Environment Variables:
        DEFAULT_MODEL: Default model to use if model_name is None (default: "gpt-4")
        ANTHROPIC_API_KEY: Required for Anthropic models
        OPENAI_API_KEY: Required for OpenAI models
        X_AI_API_KEY: Required for XAI (Grok) models
        XAI_BASE_URL: Base URL for XAI API (default: "https://api.x.ai/v1")
        GOOGLE_CLOUD_PROJECT: Google Cloud project for Gemini models (uses .gcloud.json auth)
        VERTEX_LOCATION: Google Cloud location for Gemini models (optional)

    Google Cloud Authentication:
        Gemini models use Google Cloud JSON authentication via .gcloud.json file
        or default Google Cloud credentials. No API key required.

    Examples:
        >>> # Create OpenAI model
        >>> model = create_chat_model("gpt-4", temperature=0.5)

        >>> # Create Anthropic model with tools
        >>> tools = [some_tool_definition]
        >>> model = create_chat_model("claude-3-opus", api_tools=tools)

        >>> # Create Gemini model (Gemini 3 uses global region automatically)
        >>> model = create_chat_model("gemini-3-flash-preview", temperature=0.3)

        >>> # Create XAI model
        >>> model = create_chat_model("grok-2", temperature=0.7)

        >>> # Use environment default
        >>> model = create_chat_model()
    """
    if model_name is None:
        model_name = os.getenv("DEFAULT_MODEL", "gpt-4")

    # Determine provider and create appropriate model
    if is_anthropic_model(model_name):
        # Create Anthropic model
        if not _HAS_ANTHROPIC:
            raise RuntimeError(
                "Anthropic chat model not available. Install langchain-anthropic to use Claude models.")

        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is required for Anthropic models")

        model = ChatAnthropic(
            model=model_name,
            temperature=temperature,
            anthropic_api_key=anthropic_api_key
        )
        provider = "anthropic"

    elif is_gemini_model(model_name):
        # Create Gemini model via Vertex AI
        if not _HAS_VERTEX:
            raise RuntimeError(
                "Vertex AI chat model not available. Install langchain-google-vertexai and configure GCP env.")

        # Use explicit credentials and project info from common_settings
        # Fall back to provided parameters or environment variables
        vertex_project = project or _PROJECT_ID or os.getenv(
            "GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT")
        
        # Gemini 3 preview models require 'global' region
        if requires_global_region(model_name):
            vertex_location = "global"
        else:
            vertex_location = location or _LOCATION or os.getenv(
                "VERTEX_LOCATION") or os.getenv("GOOGLE_CLOUD_REGION")

        if not vertex_project:
            raise ValueError(
                "Google Cloud project ID is required for Gemini models. Set GOOGLE_CLOUD_PROJECT or provide project parameter.")

        # Use the same authentication pattern as the main factory
        # This will use .gcloud.json file or default Google Cloud credentials
        model = ChatVertexAI(
            model_name=model_name,
            project=vertex_project,
            location=vertex_location,
            credentials=_CREDENTIALS,
            temperature=temperature
        )
        provider = "gemini"

    elif is_xai_model(model_name):
        # Create XAI model (Grok) via OpenAI-compatible API
        xai_api_key = os.getenv("X_AI_API_KEY")
        if not xai_api_key:
            raise ValueError(
                "X_AI_API_KEY environment variable is required for XAI (Grok) models")

        base_url = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")

        model = ChatOpenAI(
            model=model_name,
            api_key=xai_api_key,
            base_url=base_url,
            temperature=temperature,
            timeout=60,
            max_retries=3
        )

        # Apply JSON mode if requested (XAI supports OpenAI-compatible features)
        if json_mode:
            model = model.with_structured_output(method="json_mode")
        provider = "xai"

    else:
        # Default to OpenAI model
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required for OpenAI models")

        model = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            openai_api_key=openai_api_key,
            timeout=60,
            max_retries=3
        )

        # Apply JSON mode if requested (OpenAI only)
        if json_mode:
            model = model.with_structured_output(method="json_mode")
        provider = "openai"

    # Bind API tools if available
    if api_tools:
        print(
            f"Binding API tools to {provider} model {model_name}: {[tool.name for tool in api_tools]}")
        model = model.bind_tools(api_tools)
    else:
        print(f"No API tools to bind to {provider} model {model_name}")

    return model


def is_anthropic_available() -> bool:
    """Check if the Anthropic package is available.

    Returns:
        True if langchain_anthropic is installed and available, False otherwise.

    Examples:
        >>> if is_anthropic_available():
        ...     model = create_chat_model("claude-3-opus")
        >>> else:
        ...     print("Anthropic package not available")
    """
    return _HAS_ANTHROPIC


def is_vertex_available() -> bool:
    """Check if the Vertex AI package is available.

    Returns:
        True if langchain_google_vertexai is installed and available, False otherwise.

    Examples:
        >>> if is_vertex_available():
        ...     model = create_chat_model("gemini-1.5-pro")
        >>> else:
        ...     print("Vertex AI package not available")
    """
    return _HAS_VERTEX


def get_model_provider(model_name: str) -> str:
    """Get the provider name for a given model.

    This is a utility function that determines which provider should be used
    for a given model name.

    Args:
        model_name: Name of the model to check.

    Returns:
        Provider name ('anthropic', 'gemini', 'xai', or 'openai').

    Examples:
        >>> get_model_provider("claude-3-opus")
        'anthropic'
        >>> get_model_provider("gemini-1.5-pro")
        'gemini'
        >>> get_model_provider("grok-2")
        'xai'
        >>> get_model_provider("gpt-4")
        'openai'
    """
    if is_anthropic_model(model_name):
        return "anthropic"
    elif is_gemini_model(model_name):
        return "gemini"
    elif is_xai_model(model_name):
        return "xai"
    else:
        return "openai"


