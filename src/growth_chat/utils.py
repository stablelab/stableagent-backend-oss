"""
Utility functions for Growth Chat graphs.
"""
from typing import Any, List

from langchain_core.messages import HumanMessage, RemoveMessage, ToolMessage

from src.utils.model_factory import extract_text_content

from .schemas import PlanStep


def format_plan_message(plan: List[PlanStep], step_idx: int) -> str:
    """
    Format a plan into a message string with task descriptions.
    
    Args:
        plan: List of plan steps with agent_type and task_description
        step_idx: Current step index in the plan
        
    Returns:
        Formatted string with [TASK_DESCRIPTION] and [NEXT_TASK_DESCRIPTION] tags
    """
    parts = []
    parts.append(f"[TASK_DESCRIPTION] for {plan[step_idx]['agent_type']}: {plan[step_idx]['task_description']} [END TASK_DESCRIPTION].")
    for step in plan[step_idx + 1:]:
        parts.append(f"[NEXT_TASK_DESCRIPTION] for {step['agent_type']}: {step['task_description']} [END NEXT_TASK_DESCRIPTION].")
    return "\n".join(parts)


def filter_empty_messages(messages: List[Any]) -> List[Any]:
    """
    Filter out messages with empty content to prevent Gemini API errors.
    
    Gemini requires all messages to have at least one 'parts' field with content.
    Messages with empty or None content cause: "must include at least one parts field"
    
    Args:
        messages: List of LangChain messages
        
    Returns:
        Filtered list with only non-empty messages
    """
    filtered = []
    for msg in messages:
        content = extract_text_content(msg.content) if hasattr(msg, "content") else ""
        if content and content.strip():
            filtered.append(msg)
    return filtered


def get_plan_message_removals(messages: List[Any]) -> List[RemoveMessage]:
    """
    Get RemoveMessage objects for all plan instruction messages.
    
    Plan messages are HumanMessages that start with "[TASK_DESCRIPTION]".
    When agents execute sequentially, old plan messages become stale.
    This function returns RemoveMessage objects for all plan messages,
    to be used with the add_messages reducer before adding a new plan message.
    
    Args:
        messages: List of LangChain messages
        
    Returns:
        List of RemoveMessage objects for all plan messages
    """
    removals = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            content = extract_text_content(msg.content) if hasattr(msg, "content") else ""
            if content and content.startswith("[TASK_DESCRIPTION]") and hasattr(msg, "id"):
                removals.append(RemoveMessage(id=msg.id))
    return removals


def get_tool_message_removals(messages: List[Any]) -> List[RemoveMessage]:
    """
    Get RemoveMessage objects for all tool messages.
    
    Tool messages are internal execution details that can clutter the
    conversation history for subsequent agents. This function returns
    RemoveMessage objects for all ToolMessage instances.
    
    Args:
        messages: List of LangChain messages
        
    Returns:
        List of RemoveMessage objects for all tool messages
    """
    removals = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and hasattr(msg, "id"):
            removals.append(RemoveMessage(id=msg.id))
    return removals


