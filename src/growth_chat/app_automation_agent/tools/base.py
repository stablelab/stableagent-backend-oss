"""
Base classes for App Automation Agent tools.

Contains shared base classes that other tool modules can import without circular dependencies.
"""
from typing import Any, Optional

from langchain_core.tools import BaseTool
from langgraph.types import interrupt
from pydantic import BaseModel

from src.utils.logger import logger

from .api_client import APIError


def _serialize_for_interrupt(value: Any) -> Any:
    """Recursively serialize Pydantic models and other non-JSON-serializable objects."""
    if isinstance(value, BaseModel):
        return value.model_dump()
    elif isinstance(value, list):
        return [_serialize_for_interrupt(item) for item in value]
    elif isinstance(value, dict):
        return {k: _serialize_for_interrupt(v) for k, v in value.items()}
    return value


class APIBaseTool(BaseTool):
    """Base class for API tools with user approval.
    Handles user approval, API error handling, and resource cleanup."""
    
    auth_token: str = ""  # will be set by the tool instance
    requires_approval: bool = False
    _client: Optional[Any] = None  # Subclasses should override with specific client type

    def _get_client(self) -> Any:
        """Get API client instance. Override in subclass to return the appropriate client."""
        raise NotImplementedError("Subclasses must implement _get_client method")
    
    def close(self) -> None:
        """Close the API client if initialized. Call this for explicit cleanup."""
        if self._client is not None:
            if hasattr(self._client, 'close'):
                self._client.close()
            self._client = None

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        """Run the tool with or without user approval."""
        logger.info(f"[TOOL] Running {self.name} tool with parameters: {kwargs}")
        if self.requires_approval:
            # Serialize Pydantic models for JSON compatibility in interrupt
            serializable_kwargs = _serialize_for_interrupt(kwargs)
            # interrupts Langgraph execution until approval is received
            approval = interrupt(
                {
                    "action": self.name,
                    "parameters": serializable_kwargs,
                    "message": f"Do you approve this action?"
                }
            )
            if approval.get("action") == "approve":
                # if approved, update the kwargs with the approved parameters
                kwargs = approval.get("parameters", kwargs)
                logger.info(f"[APPROVAL] User approved action: {self.name} with parameters: {kwargs}")
            else:
                logger.info(f"[APPROVAL] User did not approve action: {self.name}")
                return f"{self.name} action not approved by user"
        try:
            result = self._run_tool(*args, **kwargs)
            logger.info(f"[TOOL] {self.name} result: {result}")
            return result
        except APIError as e:
            logger.error(f"[TOOL] {self.name} API Error: {e.message}")
            return f"Error running {self.name} tool: {e.message}"
        except Exception as e:
            logger.error(f"[TOOL] {self.name} Error: {str(e)}")
            return f"Error running {self.name} tool: {str(e)}"
    
    def _run_tool(self, *args: Any, **kwargs: Any) -> Any:
        """Run the tool."""
        raise NotImplementedError("Subclasses must implement this method")

