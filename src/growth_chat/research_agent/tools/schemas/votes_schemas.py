"""Schemas for Votes lookup tool.

Defines input/output types for vote record queries.
"""
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class VotesSearchInput(BaseModel):
    """Input schema for votes lookup."""
    proposal_id: Optional[str] = Field(None, description="Filter by proposal ID")
    voter: Optional[str] = Field(None, description="Filter by voter address")
    dao_id: Optional[str] = Field(None, description="Filter by DAO identifier")
    limit: int = Field(50, ge=1, le=200, description="Maximum results to return")


class VoteRecordOutput(BaseModel):
    """Output schema for a single vote record."""
    voter: str = Field(..., description="Voter address")
    proposal: str = Field(..., description="Proposal ID")
    choice: Any = Field(..., description="Vote choice")
    vp: float = Field(..., description="Voting power used")
    source: str = Field(..., description="Source platform")
    dao_id: Optional[str] = Field(None, description="DAO identifier")
    reason: Optional[str] = Field(None, description="Voter's reason")
    created: Optional[int] = Field(None, description="Vote timestamp")


class VoteAggregation(BaseModel):
    """Aggregated vote statistics."""
    total_votes: int = Field(..., description="Total number of votes")
    total_vp: float = Field(..., description="Total voting power")
    choice_breakdown: dict = Field(default_factory=dict, description="Voting power per choice")


class VotesSearchOutput(BaseModel):
    """Output schema for votes search results."""
    proposal_id: Optional[str] = Field(None, description="Proposal filter")
    voter: Optional[str] = Field(None, description="Voter filter")
    dao_id: Optional[str] = Field(None, description="DAO filter")
    total_results: int = Field(..., description="Number of results found")
    aggregation: Optional[VoteAggregation] = Field(None, description="Vote aggregations if by proposal")
    votes: List[VoteRecordOutput] = Field(default_factory=list, description="Individual vote records")

