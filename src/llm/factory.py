from typing import Optional
import os

from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from src.utils.logger import logger

# Prefer the dedicated Google package
try:
    from langchain_google_vertexai import ChatVertexAI
    _HAS_VERTEX = True
except Exception:
    ChatVertexAI = None  # type: ignore
    _HAS_VERTEX = False

# Pull project/region/credentials from app config when available
try:
    from src.config.common_settings import PROJECT_ID as _PROJECT_ID, LOCATION as _LOCATION, credentials as _CREDENTIALS
except Exception:
    print("Could not import common_settings")
    _PROJECT_ID, _LOCATION, _CREDENTIALS = None, None, None

# Import requires_global_region for Gemini 3 models
try:
    from src.utils.model_factory import requires_global_region
except Exception:
    # Fallback implementation if import fails
    def requires_global_region(model_name: str) -> bool:
        """Check if the model requires the global region (Gemini 3 models)."""
        return model_name.lower().startswith('gemini-3')

DEFAULT_PROVIDER = os.environ.get("DEFAULT_LLM_PROVIDER", "vertex_ai").lower()


def create_chat_model(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    project: Optional[str] = None,
    location: Optional[str] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    reasoning_effort: Optional[str] = "medium",
    service_tier: Optional[str] = "default",
) -> BaseChatModel:
    provider_name = (provider or DEFAULT_PROVIDER).lower()

    if provider_name in ("gemini", "vertex_ai"):
        if not _HAS_VERTEX:
            raise RuntimeError("Vertex AI chat model not available. Install langchain-google-vertexai and configure GCP env.")
        model_id = model or os.environ.get("VERTEX_DEFAULT_MODEL", "gemini-3-flash-preview")
        
        # Use explicit credentials and project info from common_settings
        # Fall back to provided parameters or environment variables if common_settings not available
        vertex_project = project or _PROJECT_ID or os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
        
        # Gemini 3 preview models require 'global' region
        if requires_global_region(model_id):
            vertex_location = "global"
        else:
            vertex_location = location or _LOCATION or os.environ.get("VERTEX_LOCATION") or os.environ.get("GOOGLE_CLOUD_REGION")
        
        return ChatVertexAI(
            model_name=model_id,
            project=vertex_project,
            location=vertex_location,
            credentials=_CREDENTIALS
        )

    if provider_name == "openai":
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        model_id = model or os.environ.get("OPENAI_DEFAULT_MODEL", "gpt-5-mini")
        # Provide sane defaults for production
        temp = 1.0 if temperature is None else float(temperature)
        top_p = 1.0 if top_p is None else float(top_p)

        # Only include optional kwargs when the target model supports them.
        # - reasoning_effort: supported by OpenAI reasoning models (o4, o3, etc.)
        # - service_tier: supported by gpt-4o family
        model_lower = (model_id or "").lower()
        supports_reasoning_effort = (
            model_lower.startswith("o4")
            or model_lower.startswith("o3")
            or "-reason" in model_lower
        )
        supports_service_tier = ("gpt-4o" in model_lower)

        kwargs = dict(
            model=model_id,
            api_key=api_key,
            timeout=60,
            max_retries=3,
            temperature=temp,
            top_p=top_p,
        )
        if supports_reasoning_effort and reasoning_effort is not None:
            # langchain-openai forwards unknown fields as model_kwargs
            kwargs["reasoning_effort"] = reasoning_effort
        if supports_service_tier and service_tier is not None:
            kwargs["service_tier"] = service_tier

        return ChatOpenAI(**kwargs)

    # xAI (Grok) via OpenAI-compatible API
    if provider_name in ("xai", "x-ai", "x_ai", "x.ai", "grok"):
        api_key = api_key or os.environ.get("X_AI_API_KEY")
        if not api_key:
            raise RuntimeError("X_AI_API_KEY not set")
        model_id = model or os.environ.get("XAI_DEFAULT_MODEL", "grok-3-mini")
        base_url = os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1")
        temp = 1.0 if temperature is None else float(temperature)
        top_p = 1.0 if top_p is None else float(top_p)
        return ChatOpenAI(
            model=model_id,
            api_key=api_key,
            base_url=base_url,
            timeout=60,
            max_retries=3,
            temperature=temp,
            top_p=top_p,
        )

    raise ValueError(f"Unsupported provider: {provider_name}")


def identify_model_name(llm: BaseChatModel) -> str:
    """Return the model name from a LangChain chat model instance.

    Supports common providers by checking multiple attribute names.
    """
    # ChatOpenAI uses 'model'
    model_name = getattr(llm, "model", None)
    if model_name:
        return str(model_name)

    # ChatVertexAI uses 'model_name'
    model_name = getattr(llm, "model_name", None)
    if model_name:
        return str(model_name)

    # Fallbacks seen in some wrappers
    model_name = getattr(llm, "model_id", None) or getattr(llm, "name", None)
    return str(model_name) if model_name else "unknown"


def identify_provider(llm: BaseChatModel) -> str:
    """Best-effort provider identifier for a LangChain chat model instance."""
    try:
        if isinstance(llm, ChatOpenAI):
            # Distinguish xAI from OpenAI using the configured base URL
            base_url = getattr(llm, "base_url", None)
            if base_url is None:
                client = getattr(llm, "client", None)
                base_url = getattr(client, "base_url", None)
            base_url_str = str(base_url) if base_url is not None else ""
            if "api.x.ai" in base_url_str:
                return "xai"
            return "openai"
    except Exception:
        pass

    try:
        if _HAS_VERTEX and ChatVertexAI is not None and isinstance(llm, ChatVertexAI):
            return "vertex_ai"
    except Exception:
        pass

    # Fallback to class name
    try:
        return type(llm).__name__
    except Exception:
        return "unknown"


def create_tool_chat_model(tool_name: str, default_provider: Optional[str] = None, default_model: Optional[str] = None) -> BaseChatModel:
    """Create an LLM for a tool honoring per-tool overrides.

    - Reads `TOOL_MODEL_OVERRIDES` from `src.config.tool_models`
    - Falls back to provided defaults or environment defaults
    """
    try:
        from src.config.tool_models import TOOL_MODEL_OVERRIDES
    except Exception:
        TOOL_MODEL_OVERRIDES = {}  # type: ignore

    override = (TOOL_MODEL_OVERRIDES or {}).get(tool_name, {})
    provider = override.get("provider", default_provider)
    model = override.get("model", default_model)
    temperature = override.get("temperature")
    top_p = override.get("top_p") if override.get("top_p") else 1.0
    logger.info("LLMFactory: creating tool model for %s provider=%s model=%s temperature=%s", tool_name, provider, model, temperature)
    return create_chat_model(provider=provider, model=model, temperature=temperature, top_p=top_p)