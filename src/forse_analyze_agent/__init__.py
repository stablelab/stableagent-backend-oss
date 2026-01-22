"""Forse Analyze Agent.

A ReAct-style agent for analyzing Forse.io dashboards and graphs.
Supports three analysis modes:
- Dashboard Overview: Holistic analysis of entire dashboard
- Custom Analysis: User-specified analysis on graph data  
- Default: Sequential step-by-step chart exploration

Can be used as:
- Standalone agent via HTTP endpoints (router)
- Sub-agent in multi-agent systems via direct API functions
"""

from src.forse_analyze_agent.graph import create_forse_agent_graph, forse_agent_graph

__all__ = [
    "forse_agent_graph",
    "create_forse_agent_graph",
]
