"""
LangGraph workflow for Knowledge Hub Agent.

Implements an intelligent agent that can perform multiple strategic searches
on the Knowledge Hub to find comprehensive information for user queries.

The agent uses the create_agent pattern with a search tool that can be called
multiple times with different keyword queries.
"""
import os
from typing import List, Optional

from langchain.agents import create_agent
from langchain_core.tools import BaseTool
from langgraph.graph import MessagesState, StateGraph

from src.utils.checkpointer import get_checkpointer
from src.utils.logger import logger
from src.utils.model_factory import create_chat_model

from .prompts import KNOWLEDGE_HUB_AGENT_SYSTEM_PROMPT
from .tools import create_knowledge_hub_tools
from ..shared_tools import create_blockchain_tools
from ..prompts import MULTI_STEP_PLANS_PROMPT

# ==================
# Configuration
# ==================

DEFAULT_MODEL = os.environ.get("KNOWLEDGE_AGENT_MODEL", "gemini-3-flash-preview")
DEFAULT_TEMPERATURE = float(os.environ.get("KNOWLEDGE_AGENT_TEMPERATURE", "0.7"))

# Create shared checkpointer at module level (persists across requests)
_SHARED_CHECKPOINTER = get_checkpointer()


# ==================
# Agent Creation
# ==================

def create_knowledge_hub_agent_node(tools: List[BaseTool]):
    """
    Create the Knowledge Hub agent node.
    
    Uses LangChain's create_agent to build an agent that can:
    - Decompose complex queries into focused keyword searches
    - Call the search_knowledge_hub tool multiple times
    - Synthesize answers from retrieved documents
    - Guide users on adding content when information is not found
    
    Args:
        tools: List of tools for the agent (search_knowledge_hub)
        
    Returns:
        Agent node for the graph
    """
    system_prompt = KNOWLEDGE_HUB_AGENT_SYSTEM_PROMPT.format(
        multi_step_plans=MULTI_STEP_PLANS_PROMPT,
    )
    
    agent = create_agent(
        model=create_chat_model(model_name=DEFAULT_MODEL, temperature=DEFAULT_TEMPERATURE),
        system_prompt=system_prompt,
        tools=tools,
    )
    return agent


def create_knowledge_hub_graph(
    org_schema: str,
    org_id: int,
    visibility: Optional[str] = None,
    auth_token: str = "",
    org_slug: str = "",
):
    """
    Create and compile the LangGraph workflow for the Knowledge Hub Agent.
    
    Uses an intelligent agent with tool-calling capability that can:
    - Break down questions into multiple focused searches
    - Search the Knowledge Hub multiple times with different queries
    - Search on-chain blockchain proposals (if configured)
    - Provide well-cited answers from the retrieved documents
    - Guide users to add content when information is not found
    
    Args:
        org_schema: Organization database schema name
        org_id: Organization ID
        visibility: Visibility filter for knowledge items ("public" or None for all)
        auth_token: Privy authentication token for blockchain tools
        org_slug: Organization slug for blockchain tools
        
    Returns:
        Compiled graph with shared checkpointer
    """
    # Create tools with organization context and visibility filter
    tools = create_knowledge_hub_tools(
        org_schema=org_schema,
        org_id=org_id,
        visibility=visibility,
    )
    
    # Add blockchain tools if auth context is available
    if auth_token and org_slug:
        blockchain_tools = create_blockchain_tools(auth_token=auth_token, org_slug=org_slug)
        tools.extend(blockchain_tools)
        logger.info(f"Added {len(blockchain_tools)} blockchain tools to Knowledge Hub agent")
    
    logger.info(f"Creating Knowledge Hub agent with {len(tools)} tools for org_schema={org_schema}")
    
    # Create agent node
    knowledge_hub_agent = create_knowledge_hub_agent_node(tools=tools)
    
    # Create graph
    graph = StateGraph(MessagesState)
    graph.add_node("agent", knowledge_hub_agent)
    graph.set_entry_point("agent")
    graph.set_finish_point("agent")
    
    # Compile with shared checkpointer
    return graph.compile(checkpointer=_SHARED_CHECKPOINTER)