"""Schemas for Discord search tool.

Defines input/output types for Discord message queries.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class DiscordSearchInput(BaseModel):
    """Input schema for Discord search."""
    query: str = Field(..., description="Search query for Discord messages")
    dao_id: Optional[str] = Field(None, description="DAO identifier to filter")
    limit: int = Field(10, ge=1, le=30, description="Maximum results to return")


class DiscordMessageOutput(BaseModel):
    """Output schema for a single Discord message period."""
    date: str = Field(..., description="Message date")
    dao_id: str = Field(..., description="DAO identifier")
    content_summary: Optional[str] = Field(None, description="Summarized content")
    start_unix: int = Field(..., description="Earliest message timestamp")
    end_unix: int = Field(..., description="Latest message timestamp")
    distance: Optional[float] = Field(None, description="Semantic similarity distance")


class DiscordSearchOutput(BaseModel):
    """Output schema for Discord search results."""
    query: str = Field(..., description="Original search query")
    total_results: int = Field(..., description="Number of results found")
    messages: List[DiscordMessageOutput] = Field(default_factory=list, description="Matching message periods")

