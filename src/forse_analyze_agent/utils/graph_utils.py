"""Utility & helper functions."""

from typing import Any, Callable, Optional, TypeVar

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from src.utils.logger import logger


def get_message_text(msg: BaseMessage) -> str:
    """Get the text content of a message."""
    content = msg.content
    if isinstance(content, str):
        return content
    elif isinstance(content, dict):
        return content.get("text", "")
    else:
        txts = [c if isinstance(c, str) else (c.get("text") or "") for c in content]
        return "".join(txts).strip()


def load_chat_model(fully_specified_name: str) -> BaseChatModel:
    """Load a chat model from a fully specified name.

    Args:
        fully_specified_name (str): String in the format 'provider/model'.
    """
    provider, model = fully_specified_name.split("/", maxsplit=1)
    return init_chat_model(model, model_provider=provider)


# Type variable for generic caching
T = TypeVar('T')


async def cached_tool_call(
    cache_getter: Callable[[], Optional[T]],
    cache_setter: Callable[[T], None],
    tool_func: Callable[..., T],
    tool_name: str,
    **tool_kwargs
) -> T:
    """
    Execute a tool call with caching.
    
    This helper checks the cache first, and only calls the tool if data
    is not cached or stale. Results are automatically cached.
    
    Usage in graph nodes:
    ```python
    dao_spaces = await cached_tool_call(
        cache_getter=lambda: state.cache.get_dao_spaces(),
        cache_setter=lambda data: state.cache.set_dao_spaces(data),
        tool_func=step_1_fetch_dao_spaces.ainvoke,
        tool_name="step_1_fetch_dao_spaces",
    )
    ```
    
    Args:
        cache_getter: Function that returns cached data or None
        cache_setter: Function to store data in cache
        tool_func: The tool function to call (usually tool.ainvoke)
        tool_name: Name for logging purposes
        **tool_kwargs: Arguments to pass to the tool
        
    Returns:
        The cached or freshly-fetched data
    """
    # Try cache first
    cached_data = cache_getter()
    if cached_data is not None:
        logger.debug(f"Cache hit for {tool_name}")
        return cached_data
    
    # Cache miss - call the tool
    logger.debug(f"Cache miss for {tool_name}, fetching fresh data")
    try:
        result = await tool_func(tool_kwargs) if tool_kwargs else await tool_func({})
        
        # Cache the result if valid
        if result:
            cache_setter(result)
            logger.debug(f"Cached result for {tool_name}")
        
        return result
    except Exception as e:
        logger.error(f"Error in cached_tool_call for {tool_name}: {e}")
        raise

