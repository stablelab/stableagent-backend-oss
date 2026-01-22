"""
LangSmith tracking utilities with thread support.

Provides thread context management, decorators for tracking node/tool execution,
and session context management via contextvars.
"""

import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Callable
from functools import wraps
from contextvars import ContextVar

from .logger import logger

# Optional LangSmith imports
try:
    from langsmith import traceable, Client
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    traceable = lambda *args, **kwargs: lambda func: func  # No-op decorator

try:
    from langchain.callbacks.tracers import LangChainTracer
    from langchain_core.runnables import RunnableConfig
    LANGCHAIN_TRACER_AVAILABLE = True
except ImportError:
    LANGCHAIN_TRACER_AVAILABLE = False
    LangChainTracer = None
    RunnableConfig = dict


# Context variables for thread tracking
_current_session_id: ContextVar[Optional[str]] = ContextVar("current_session_id", default=None)
_current_user_id: ContextVar[Optional[str]] = ContextVar("current_user_id", default=None)
_current_thread_config: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "current_thread_config", default=None
)


def is_langsmith_enabled() -> bool:
    """
    Check if LangSmith tracking is enabled.
    
    Supports both new (LANGSMITH_TRACING) and legacy (LANGCHAIN_TRACING_V2) env vars.
    """
    if not LANGSMITH_AVAILABLE:
        return False
    
    # Check new env var first, then fall back to legacy
    tracing_enabled = os.getenv("LANGSMITH_TRACING", "").lower() == "true"
    if not tracing_enabled:
        tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true"
    
    return tracing_enabled


def generate_session_id() -> str:
    """Generate a new session ID for thread tracking."""
    return str(uuid.uuid4())


def set_session_context(session_id: str, user_id: Optional[str] = None) -> None:
    """Set the current session context for thread tracking."""
    _current_session_id.set(session_id)
    if user_id:
        _current_user_id.set(str(user_id))


def get_session_context() -> tuple:
    """Get the current session context (session_id, user_id)."""
    return _current_session_id.get(), _current_user_id.get()


def get_thread_metadata(
    session_id: Optional[str] = None, user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Get metadata for thread tracking."""
    current_session_id, current_user_id = get_session_context()
    
    metadata = {}
    
    if session_id or current_session_id:
        metadata["session_id"] = session_id or current_session_id
        metadata["thread_id"] = session_id or current_session_id
    
    if user_id or current_user_id:
        metadata["user_id"] = user_id or current_user_id
    
    return metadata


def create_thread_config(
    thread_id: Optional[str] = None, user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a LangChain config with thread tracking.
    
    Args:
        thread_id: Thread/session ID (generates new one if not provided)
        user_id: Optional user ID
        
    Returns:
        Config dict with callbacks for thread tracking
    """
    if not is_langsmith_enabled():
        return {}
    
    if not thread_id:
        thread_id = generate_session_id()
    
    # Convert user_id to string if provided
    user_id_str = str(user_id) if user_id is not None else None
    set_session_context(thread_id, user_id_str)
    
    project_name = os.getenv("LANGSMITH_PROJECT", "growth-chat")
    
    config: Dict[str, Any] = {
        "metadata": {
            "thread_id": thread_id,
            "session_id": thread_id,
        },
        "tags": [f"thread:{thread_id}"],
    }
    
    if user_id_str:
        config["metadata"]["user_id"] = user_id_str
        config["tags"].append(f"user:{user_id_str}")
    
    # Add LangChainTracer callback if available
    if LANGCHAIN_TRACER_AVAILABLE and LangChainTracer:
        try:
            # Build tracer kwargs - include workspace_id if provided (required for org-scoped API keys)
            tracer_kwargs: Dict[str, Any] = {
                "project_name": project_name,
            }
            
            # Add workspace_id if set (required for org-scoped API keys)
            workspace_id = os.getenv("LANGSMITH_WORKSPACE_ID")
            if workspace_id:
                # LangChainTracer doesn't directly accept workspace_id, but setting env var works
                # The Client uses LANGSMITH_WORKSPACE_ID automatically
                pass
            
            # Try with full parameters first
            try:
                tracer = LangChainTracer(
                    project_name=project_name,
                    tags=config["tags"],
                    metadata=config["metadata"],
                )
                config["callbacks"] = [tracer]
            except TypeError:
                # Fallback for older versions that don't accept tags/metadata
                tracer = LangChainTracer(project_name=project_name)
                config["callbacks"] = [tracer]
                
        except Exception as e:
            logger.warning(f"Failed to create LangChainTracer: {e}")
    
    _current_thread_config.set(config)
    
    return config


def get_current_thread_config() -> Optional[Dict[str, Any]]:
    """Get the current thread config from context."""
    return _current_thread_config.get()


def track_tool_execution(tool_name: str, metadata: Optional[Dict[str, Any]] = None):
    """
    Decorator for tracking tool executions using LangSmith @traceable.
    
    Args:
        tool_name: Name of the tool being tracked
        metadata: Optional additional metadata
    """
    def decorator(func: Callable) -> Callable:
        if not is_langsmith_enabled():
            return func
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            thread_metadata = get_thread_metadata()
            combined_metadata = {**(metadata or {}), **thread_metadata}
            
            @traceable(
                run_type="tool",
                name=f"tool_{tool_name}",
                metadata=combined_metadata,
            )
            def traced_execution():
                return func(*args, **kwargs)
            
            return traced_execution()
        
        return wrapper
    return decorator


def track_node_execution(node_name: str, metadata: Optional[Dict[str, Any]] = None):
    """
    Decorator for tracking node executions using LangSmith @traceable.
    
    Args:
        node_name: Name of the node being tracked
        metadata: Optional additional metadata
    """
    def decorator(func: Callable) -> Callable:
        if not is_langsmith_enabled():
            return func
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            thread_metadata = get_thread_metadata()
            combined_metadata = {**(metadata or {}), **thread_metadata}
            
            @traceable(
                run_type="chain",
                name=f"node_{node_name}",
                metadata=combined_metadata,
            )
            def traced_execution():
                return func(*args, **kwargs)
            
            return traced_execution()
        
        return wrapper
    return decorator


class ThreadContext:
    """
    Context manager for LangSmith thread tracking.
    
    Usage:
        with ThreadContext(thread_id="my-thread") as config:
            response = model.invoke(messages, config=config)
    """
    
    def __init__(self, thread_id: Optional[str] = None, user_id: Optional[str] = None):
        """
        Initialize thread context.
        
        Args:
            thread_id: Thread/session ID (generates new one if not provided)
            user_id: Optional user ID
        """
        self.thread_id = thread_id or generate_session_id()
        self.user_id = user_id
        self.config: Optional[Dict[str, Any]] = None
        self.previous_config: Optional[Dict[str, Any]] = None
    
    def __enter__(self) -> Dict[str, Any]:
        """Enter the thread context."""
        self.previous_config = _current_thread_config.get()
        self.config = create_thread_config(self.thread_id, self.user_id)
        return self.config
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the thread context."""
        _current_thread_config.set(self.previous_config)


def ensure_thread_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Ensure we have a thread config, using existing config if available.
    
    Args:
        config: Existing config to merge with
        
    Returns:
        Config with thread tracking
    """
    if config and ("callbacks" in config or "metadata" in config):
        return config
    
    thread_config = get_current_thread_config()
    if thread_config and thread_config.get("callbacks"):
        if config:
            merged = {**config}
            merged.setdefault("metadata", {}).update(thread_config.get("metadata", {}))
            merged.setdefault("tags", []).extend(thread_config.get("tags", []))
            merged.setdefault("callbacks", []).extend(thread_config.get("callbacks", []))
            return merged
        return thread_config
    
    thread_id = None
    user_id = None
    if config and "configurable" in config:
        thread_id = config["configurable"].get("thread_id")
        user_id = config["configurable"].get("user_id")
    
    new_config = create_thread_config(thread_id=thread_id, user_id=user_id)
    if config:
        merged = {**config}
        merged.setdefault("metadata", {}).update(new_config.get("metadata", {}))
        merged.setdefault("tags", []).extend(new_config.get("tags", []))
        if "callbacks" in new_config:
            merged.setdefault("callbacks", []).extend(new_config["callbacks"])
        return merged
    return new_config


def log_tracking_status() -> None:
    """Log the current LangSmith tracking status."""
    if is_langsmith_enabled():
        project = os.getenv("LANGSMITH_PROJECT", "growth-chat")
        workspace_id = os.getenv("LANGSMITH_WORKSPACE_ID")
        
        if workspace_id:
            logger.info(f"LangSmith tracking enabled - project: {project}, workspace: {workspace_id}")
        else:
            logger.info(f"LangSmith tracking enabled - project: {project}")
            logger.warning("LANGSMITH_WORKSPACE_ID not set - required for org-scoped API keys")
    else:
        logger.info("LangSmith tracking disabled")

