"""
Main module for Forse Analyze LLM Agent.

Provides:
- forse_agent_graph: Default compiled graph for direct usage
- create_forse_agent_graph: Factory for customized graph instances
- analyze_dashboard: Direct API for dashboard analysis (sub-agent usage)
- analyze_graph: Direct API for graph analysis (sub-agent usage)
- router: FastAPI router for HTTP endpoints
"""

from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage

from src.forse_analyze_agent.graph import create_forse_agent_graph, forse_agent_graph
from src.forse_analyze_agent.router.main import router


async def analyze_dashboard(
    dashboard_id: str,
    analysis_prompt: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Direct API for dashboard analysis - use as sub-agent.
    
    Fetches all graphs in a dashboard and provides holistic analysis.
    
    Args:
        dashboard_id: The dashboard to analyze
        analysis_prompt: Optional custom analysis instructions
        model_name: Optional model override
        
    Returns:
        Analysis result with dashboard overview and insights
        
    Example:
        result = await analyze_dashboard(
            dashboard_id="abc123",
            analysis_prompt="Compare growth trends across all metrics"
        )
    """
    # Build the user message
    user_message = f"Analyze the entire dashboard with ID: {dashboard_id}"
    if analysis_prompt:
        user_message += f"\n\nSpecific analysis request: {analysis_prompt}"
    
    # Use custom graph if model override provided, else default
    graph = create_forse_agent_graph(model_name=model_name) if model_name else forse_agent_graph
    
    result = await graph.ainvoke({
        "messages": [HumanMessage(content=user_message)],
        "dashboard_id": dashboard_id,
        "analysis_mode": "dashboard",
        "user_analysis_prompt": analysis_prompt,
    })
    
    return {
        "analysis": result["messages"][-1].content,
        "dashboard_id": dashboard_id,
        "mode": "dashboard_overview",
    }


async def analyze_graph(
    dashboard_id: str,
    graph_id: str,
    category_id: Optional[str] = None,
    analysis_prompt: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Direct API for single graph analysis - use as sub-agent.
    
    Fetches data for a specific graph and performs analysis.
    
    Args:
        dashboard_id: The parent dashboard ID
        graph_id: The specific graph to analyze
        category_id: Optional category (uses first available if not provided)
        analysis_prompt: Optional custom analysis instructions
        model_name: Optional model override
        
    Returns:
        Analysis result with graph data and insights
        
    Example:
        result = await analyze_graph(
            dashboard_id="abc123",
            graph_id="graph456",
            analysis_prompt="Find the top 3 growth periods"
        )
    """
    # Build the user message
    user_message = f"Analyze graph {graph_id} from dashboard {dashboard_id}"
    if category_id:
        user_message += f" for category {category_id}"
    if analysis_prompt:
        user_message += f"\n\nSpecific analysis request: {analysis_prompt}"
    
    # Use custom graph if model override provided, else default
    graph = create_forse_agent_graph(model_name=model_name) if model_name else forse_agent_graph
    
    result = await graph.ainvoke({
        "messages": [HumanMessage(content=user_message)],
        "dashboard_id": dashboard_id,
        "graph_id": graph_id,
        "category_ids": [category_id] if category_id else [],
        "analysis_mode": "graph",
        "user_analysis_prompt": analysis_prompt,
    })
    
    return {
        "analysis": result["messages"][-1].content,
        "dashboard_id": dashboard_id,
        "graph_id": graph_id,
        "category_id": category_id,
        "mode": "graph_analysis",
    }


__all__ = [
    "router",
    "forse_agent_graph",
    "create_forse_agent_graph",
    "analyze_dashboard",
    "analyze_graph",
]