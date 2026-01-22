"""
Growth Chat Super Graph.

A unified agent that routes between:
- knowledge_hub_agent: For intelligent RAG-based knowledge queries
- app_automation_agent: For team management actions

The router uses LLM classification to determine which agent should handle each request.
"""
from src.growth_chat.graph import create_growth_chat_graph
from src.growth_chat.router import router
from src.growth_chat.schemas import GrowthChatRequest, GrowthChatState
from src.growth_chat.stream import stream_processing

__all__ = [
    "create_growth_chat_graph",
    "stream_processing",
    "router",
    "GrowthChatState",
    "GrowthChatRequest",
]

