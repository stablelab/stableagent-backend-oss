"""Schemas for Telegram search tool.

Defines input/output types for Telegram message queries.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class TelegramSearchInput(BaseModel):
    """Input schema for Telegram search."""
    query: str = Field(..., description="Search query for Telegram messages")
    dao_id: Optional[str] = Field(None, description="DAO identifier to filter")
    limit: int = Field(10, ge=1, le=30, description="Maximum results to return")


class TelegramMessageOutput(BaseModel):
    """Output schema for a single Telegram topic/message cluster."""
    dao_id: str = Field(..., description="DAO identifier")
    window_number: int = Field(..., description="Analysis window number")
    topic_id: int = Field(..., description="Topic cluster ID")
    topic_title: str = Field(..., description="Topic title/label")
    content: str = Field(..., description="Aggregated message content")
    topic_representation: Optional[List[str]] = Field(None, description="Topic keywords")
    distance: Optional[float] = Field(None, description="Semantic similarity distance")


class TelegramSearchOutput(BaseModel):
    """Output schema for Telegram search results."""
    query: str = Field(..., description="Original search query")
    total_results: int = Field(..., description="Number of results found")
    messages: List[TelegramMessageOutput] = Field(default_factory=list, description="Matching message clusters")

