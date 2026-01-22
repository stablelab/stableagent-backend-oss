"""Schemas for Snapshot proposals tool.

Defines input/output types for off-chain proposal queries.
"""
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class SnapshotSearchInput(BaseModel):
    """Input schema for Snapshot proposal search."""
    query: Optional[str] = Field(None, description="Semantic search query for proposals")
    space_id: Optional[str] = Field(None, description="Snapshot space ID (e.g., 'aave.eth', 'uniswap')")
    state: Optional[str] = Field(None, description="Filter by state: active, closed, pending")
    limit: int = Field(10, ge=1, le=50, description="Maximum results to return")


class SnapshotProposalOutput(BaseModel):
    """Output schema for a single Snapshot proposal."""
    id: str = Field(..., description="Proposal ID")
    title: str = Field(..., description="Proposal title")
    body: Optional[str] = Field(None, description="Proposal body/description")
    dao_id: str = Field(..., description="Snapshot space identifier")
    author: Optional[str] = Field(None, description="Proposal author address")
    state: Optional[str] = Field(None, description="Proposal state")
    choices: Optional[List[str]] = Field(None, description="Available voting choices")
    scores: Optional[List[float]] = Field(None, description="Scores for each choice")
    votes_count: Optional[int] = Field(None, description="Total number of votes")
    created_at: Optional[str] = Field(None, description="Voting start timestamp")
    ends_at: Optional[str] = Field(None, description="Voting end timestamp")
    discourse_topic_id : Optional[int] = Field(None, description="Related discourse topic ID")
    link: str = Field(..., description="Snapshot proposal URL")
    distance: Optional[float] = Field(None, description="Semantic similarity distance")


class SnapshotSearchOutput(BaseModel):
    """Output schema for Snapshot search results."""
    query: Optional[str] = Field(None, description="Original search query")
    space_filter: Optional[str] = Field(None, description="Space filter applied")
    total_results: int = Field(..., description="Number of results found")
    proposals: List[SnapshotProposalOutput] = Field(default_factory=list, description="Matching proposals")

