"""
Knowledge Hub Agent - Intelligent RAG-based knowledge retrieval for general chat.

This module provides an intelligent agent that can perform multiple strategic
searches over an organization's Knowledge Hub, enabling comprehensive
RAG (Retrieval-Augmented Generation) for context-aware responses.

The agent can:
- Break down complex questions into focused keyword searches
- Search the Knowledge Hub multiple times with different queries
- Synthesize answers from retrieved documents with proper citations
- Guide users on adding content when information is not found
"""

from .database import KnowledgeDatabase
from .graph import create_knowledge_hub_graph
from .tools import SearchKnowledgeHubTool, create_knowledge_hub_tools
from .types import KnowledgeItem, KnowledgeQueryRequest, KnowledgeQueryResponse

__all__ = [
    # Types
    "KnowledgeItem",
    "KnowledgeQueryRequest",
    "KnowledgeQueryResponse",
    # Database
    "KnowledgeDatabase",
    # Graph
    "create_knowledge_hub_graph",
    # Tools
    "SearchKnowledgeHubTool",
    "create_knowledge_hub_tools",
]
