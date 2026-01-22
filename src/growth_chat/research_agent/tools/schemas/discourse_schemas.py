"""Schemas for Discourse search tool.

Defines input/output types for forum post queries.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class DiscourseSearchInput(BaseModel):
    """Input schema for discourse search."""
    query: str = Field(..., description="Search query for forum posts")
    dao_id: Optional[str] = Field(None, description="DAO identifier to filter results")
    topic_id: Optional[int] = Field(None, description="Specific topic ID to search within")
    limit: int = Field(10, ge=1, le=50, description="Maximum results to return")


class DiscoursePostOutput(BaseModel):
    """Output schema for a single discourse post."""
    topic_id: int = Field(..., description="Forum topic ID")
    index: int = Field(..., description="Post index within topic")
    topic_title: str = Field(..., description="Topic/thread title")
    dao_id: str = Field(..., description="DAO identifier")
    content_summary: Optional[str] = Field(None, description="Post content summary")
    post_link: Optional[str] = Field(None, description="Direct link to post")
    distance: Optional[float] = Field(None, description="Semantic similarity distance")


class DiscourseSearchOutput(BaseModel):
    """Output schema for discourse search results."""
    query: str = Field(..., description="Original search query")
    total_results: int = Field(..., description="Number of results found")
    posts: List[DiscoursePostOutput] = Field(default_factory=list, description="Matching posts")

