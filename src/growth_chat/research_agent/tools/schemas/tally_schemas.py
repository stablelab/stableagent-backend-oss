"""Schemas for Tally proposals tool.

Defines input/output types for on-chain proposal queries.
"""
from re import S
from typing import List, Optional

from pydantic import BaseModel, Field


class TallySearchInput(BaseModel):
    """Input schema for Tally proposal search."""
    query: Optional[str] = Field(None, description="Semantic search query for proposals")
    dao_id: Optional[str] = Field(None, description="Tally DAO identifier")
    state: Optional[str] = Field(None, description="Filter by state: active, executed, defeated, queued")
    limit: int = Field(10, ge=1, le=50, description="Maximum results to return")


class TallyProposalOutput(BaseModel):
    """Output schema for a single Tally proposal."""
    id: str = Field(..., description="Proposal ID")
    title: str = Field(..., description="Proposal title")
    body: Optional[str] = Field(None, description="Proposal body/description")
    dao_id: str = Field(..., description="Tally DAO identifier")
    state: Optional[str] = Field(None, description="Proposal state")
    choices: Optional[List[str]] = Field(None, description="Available voting choices")
    scores: Optional[List[float]] = Field(None, description="Scores for each choice")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    ends_at: Optional[str] = Field(None, description="Voting end timestamp")
    link: str = Field(..., description="Tally proposal URL")
    discourse_topic_id: Optional[int] = Field(None, description="Related discourse topic ID")
    distance: Optional[float] = Field(None, description="Semantic similarity distance")


class TallySearchOutput(BaseModel):
    """Output schema for Tally search results."""
    query: Optional[str] = Field(None, description="Original search query")
    dao_filter: Optional[str] = Field(None, description="DAO filter applied")
    total_results: int = Field(..., description="Number of results found")
    proposals: List[TallyProposalOutput] = Field(default_factory=list, description="Matching proposals")

