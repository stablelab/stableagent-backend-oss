"""Research Agent for DAO/governance data queries.

This agent provides specialized tools for querying various DAO data sources:
- Discourse forum posts
- Snapshot proposals (off-chain)
- Tally proposals (on-chain)
- GitHub activity
- Telegram messages
- Discord messages
- Vote records
- Token prices
"""
from .graph import create_research_agent_graph

__all__ = ["create_research_agent_graph"]

