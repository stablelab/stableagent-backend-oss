"""Define a custom Reasoning and Action agent for Forse Analytics.

Works with a chat model with tool calling support.
Supports three analysis modes:
- Dashboard Overview: Holistic analysis of entire dashboard
- Custom Analysis: User-specified analysis on graph data  
- Default: Sequential step-by-step chart exploration
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, cast

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from src.forse_analyze_agent.prompts import get_system_prompt
from src.forse_analyze_agent.state import InputState, State
from src.forse_analyze_agent.tools import AVAILABLE_TOOLS
from src.utils.model_factory import create_chat_model

# Model configuration - can be overridden via environment variables
DEFAULT_MODEL = os.getenv("FORSE_AGENT_MODEL", "gemini-3-flash-preview")
DEFAULT_TEMPERATURE = float(os.getenv("FORSE_AGENT_TEMPERATURE", "0.7"))


def _build_context_from_state(state: State) -> str:
    """Build additional context string from state for the model."""
    context_parts = []
    
    if state.dashboard_id:
        context_parts.append(f"Current dashboard_id: {state.dashboard_id}")
    
    if state.graph_id:
        context_parts.append(f"Current graph_id: {state.graph_id}")
    
    if state.category_ids:
        context_parts.append(f"Selected categories: {', '.join(state.category_ids)}")
    
    if state.analysis_mode:
        context_parts.append(f"Analysis mode: {state.analysis_mode}")
    
    if state.user_analysis_prompt:
        context_parts.append(f"User's analysis request: {state.user_analysis_prompt}")
    
    if state.dashboard_context:
        context_parts.append(f"Dashboard has {state.dashboard_context.get('total_graphs', 'unknown')} graphs")
    
    if context_parts:
        return "\n\n[Current Context]\n" + "\n".join(context_parts)
    return ""


async def call_model(
    state: State, 
    config: Optional[RunnableConfig] = None
) -> Dict[str, Any]:
    """Call the LLM powering the Forse agent.

    This function prepares the prompt, initializes the model, and processes the response.
    Supports dynamic context injection based on state.

    Args:
        state: The current state of the conversation.
        config: Optional runnable config for tracing/callbacks.

    Returns:
        dict: A dictionary containing the model's response message and any state updates.
    """
    # Initialize the model with tool binding
    model = create_chat_model(
        model_name=DEFAULT_MODEL,
        temperature=DEFAULT_TEMPERATURE,
    ).bind_tools(AVAILABLE_TOOLS)

    # Build system prompt with current timestamp
    system_message = get_system_prompt().format(
        system_time=datetime.now(tz=timezone.utc).isoformat()
    )
    
    # Add state context if available
    context = _build_context_from_state(state)
    if context:
        system_message += context

    # Prepare messages for the model
    messages = [{"role": "system", "content": system_message}, *state.messages]

    # Get the model's response
    response = cast(
        AIMessage,
        await model.ainvoke(messages, config=config),
    )

    # Handle the case when it's the last step and the model still wants to use a tool
    if state.is_last_step and response.tool_calls:
        return {
            "messages": [
                AIMessage(
                    id=response.id,
                    content="Sorry, I could not find an answer to your question in the specified number of steps.",
                )
            ]
        }

    # Return the model's response
    return {"messages": [response]}


def route_model_output(state: State) -> Literal["__end__", "tools"]:
    """Determine the next node based on the model's output.

    This function checks if the model's last message contains tool calls.

    Args:
        state: The current state of the conversation.

    Returns:
        str: The name of the next node to call ("__end__" or "tools").
    """
    last_message = state.messages[-1]
    if not isinstance(last_message, AIMessage):
        raise ValueError(
            f"Expected AIMessage in output edges, but got {type(last_message).__name__}"
        )
    # If there is no tool call, then we finish
    if not last_message.tool_calls:
        return "__end__"
    # Otherwise we execute the requested actions
    return "tools"


def create_forse_agent_graph(
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    recursion_limit: int = 25,
) -> StateGraph:
    """Factory function to create a Forse agent graph.
    
    Useful for creating customized instances when used as a sub-agent.
    
    Args:
        model_name: Override the default model name.
        temperature: Override the default temperature.
        recursion_limit: Maximum number of agent steps (default: 25).
        
    Returns:
        Compiled StateGraph ready for invocation.
    """
    # Build the graph
    builder = StateGraph(State, input_schema=InputState)

    # Create a custom call_model with overridden settings if provided
    async def custom_call_model(state: State, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
        effective_model = model_name or DEFAULT_MODEL
        effective_temp = temperature if temperature is not None else DEFAULT_TEMPERATURE
        
        model = create_chat_model(
            model_name=effective_model,
            temperature=effective_temp,
        ).bind_tools(AVAILABLE_TOOLS)

        system_message = get_system_prompt().format(
            system_time=datetime.now(tz=timezone.utc).isoformat()
        )
        
        context = _build_context_from_state(state)
        if context:
            system_message += context

        messages = [{"role": "system", "content": system_message}, *state.messages]

        response = cast(
            AIMessage,
            await model.ainvoke(messages, config=config),
        )

        if state.is_last_step and response.tool_calls:
            return {
                "messages": [
                    AIMessage(
                        id=response.id,
                        content="Sorry, I could not find an answer to your question in the specified number of steps.",
                    )
                ]
            }

        return {"messages": [response]}

    # Add nodes
    builder.add_node("call_model", custom_call_model)
    builder.add_node("tools", ToolNode(AVAILABLE_TOOLS))

    # Set entry point
    builder.add_edge("__start__", "call_model")

    # Add conditional routing
    builder.add_conditional_edges("call_model", route_model_output)

    # Tool results flow back to model
    builder.add_edge("tools", "call_model")

    return builder.compile(
        name="forse_agent_graph",
    )


# Default graph instance for direct usage and backward compatibility
_default_builder = StateGraph(State, input_schema=InputState)
_default_builder.add_node("call_model", call_model)
_default_builder.add_node("tools", ToolNode(AVAILABLE_TOOLS))
_default_builder.add_edge("__start__", "call_model")
_default_builder.add_conditional_edges("call_model", route_model_output)
_default_builder.add_edge("tools", "call_model")

forse_agent_graph = _default_builder.compile(name="forse_agent_graph")
