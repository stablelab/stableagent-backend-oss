"""Common schemas shared across Research Agent tools.

Defines base types for proposals, votes, search results, and DAO info.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ==================
# Date Range Mixin
# ==================

DATE_DESCRIPTION = "Date in YYYY-MM-DD format (e.g., '2024-01-15')"


# ==================
# Proposal Schemas
# ==================

class ProposalResult(BaseModel):
    """Unified proposal result from any source."""
    proposal_id: str = Field(..., description="Unique proposal identifier")
    dao_id: str = Field(..., description="DAO identifier")
    title: str = Field(..., description="Proposal title")
    body: Optional[str] = Field(None, description="Proposal body/description")
    source: str = Field(..., description="Source platform: snapshot, tally, aragon, onchain_daos")
    state: Optional[str] = Field(None, description="Proposal state: active, closed, executed, etc.")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    ends_at: Optional[str] = Field(None, description="Ends at timestamp")
    choices: Optional[List[str]] = Field(None, description="Available voting choices")
    scores: Optional[List[float]] = Field(None, description="Scores for each choice in same order as choices")
    link: Optional[str] = Field(None, description="URL to view the proposal/forum post")
    discourse_topic_id: Optional[int] = Field(None, description="Related discourse topic ID")
    distance: Optional[float] = Field(None, description="Semantic similarity distance")


class ProposalSearchInput(BaseModel):
    """Base input for proposal search tools."""
    query: Optional[str] = Field(None, description="Semantic search query")
    dao_id: Optional[str] = Field(None, description="Filter by DAO identifier")
    state: Optional[str] = Field(None, description="Filter by state: active, closed, executed")
    start_date: Optional[str] = Field(None, description=f"Filter proposals created after this date. {DATE_DESCRIPTION}")
    end_date: Optional[str] = Field(None, description=f"Filter proposals created before this date. {DATE_DESCRIPTION}")
    limit: int = Field(10, ge=1, le=50, description="Maximum results to return")


# ==================
# Vote Schemas
# ==================

class VoteResult(BaseModel):
    """Individual vote record."""
    vote_id: str = Field(..., description="Unique vote identifier")
    voter: str = Field(..., description="Voter address")
    proposal_id: str = Field(..., description="Proposal voted on")
    choice: Any = Field(..., description="Vote choice (format varies by source)")
    voting_power: float = Field(..., description="Voting power used")
    source: str = Field(..., description="Source platform")
    dao_id: Optional[str] = Field(None, description="DAO identifier")
    reason: Optional[str] = Field(None, description="Voter's reason for their choice")
    created: Optional[int] = Field(None, description="Vote timestamp (unix)")


class VotesSearchInput(BaseModel):
    """Input for votes lookup."""
    proposal_id: Optional[str] = Field(None, description="Filter by proposal ID")
    voter: Optional[str] = Field(None, description="Filter by voter address")
    dao_id: Optional[str] = Field(None, description="Filter by DAO identifier")
    start_date: Optional[str] = Field(None, description=f"Filter votes cast after this date. {DATE_DESCRIPTION}")
    end_date: Optional[str] = Field(None, description=f"Filter votes cast before this date. {DATE_DESCRIPTION}")
    limit: int = Field(50, ge=1, le=200, description="Maximum results to return")


class VoterStatsInput(BaseModel):
    """Input for voter/delegate statistics."""
    voter: str = Field(..., description="Voter address (required). Use ens_resolver to convert ENS names.")
    dao_id: str = Field("", description="Filter to specific DAO (Snapshot space). Leave empty for all DAOs.")
    start_date: str = Field("", description=f"Filter votes after this date. {DATE_DESCRIPTION}")
    end_date: str = Field("", description=f"Filter votes before this date. {DATE_DESCRIPTION}")


class ProposalVoteStatsInput(BaseModel):
    """Input for proposal voting statistics."""
    proposal_id: str = Field(..., description="Proposal ID (required). Get from snapshot_proposals or tally_proposals.")
    dao_id: str = Field("", description="DAO identifier (helps narrow search)")


class VotingPowerTrendsInput(BaseModel):
    """Input for voting power trend analysis."""
    voters: str = Field(..., description="Voter address(es) - single address or comma-separated list (e.g., '0x123...,0x456...'). Use ens_resolver to convert ENS names.")
    dao_id: str = Field("", description="Filter to specific DAO (Snapshot space). Leave empty for all DAOs.")
    start_date: str = Field("", description=f"Start of period. {DATE_DESCRIPTION} Default: 6 months ago.")
    end_date: str = Field("", description=f"End of period. {DATE_DESCRIPTION}")


class TopVotersInput(BaseModel):
    """Input for top voters/delegates leaderboard."""
    dao_id: str = Field(..., description="DAO identifier (required). Use dao_catalog to find the snapshot_id.")
    metric: str = Field("votes", description="Ranking metric: 'votes' (count), 'voting_power' (current VP), 'avg_vp' (avg VP per vote), or 'tenure' (longest active)")
    start_date: str = Field("", description=f"Filter votes after this date. {DATE_DESCRIPTION}")
    end_date: str = Field("", description=f"Filter votes before this date. {DATE_DESCRIPTION}")
    limit: int = Field(20, ge=1, le=50, description="Number of top voters to return")


# ==================
# Forum/Discussion Schemas
# ==================

class DiscoursePostResult(BaseModel):
    """Discourse forum post."""
    id: int = Field(..., description="Post ID")
    topic_id: int = Field(..., description="Topic ID")
    topic_title: str = Field(..., description="Topic title")
    username: str = Field(..., description="Author username")
    content: str = Field(..., description="Post content")
    created_at: str = Field(..., description="Creation timestamp")
    dao_id: str = Field(..., description="DAO identifier")
    reply_count: Optional[int] = Field(None, description="Number of replies")
    url: Optional[str] = Field(None, description="URL to the post")


class DiscourseSearchInput(BaseModel):
    """Input for discourse search."""
    query: str = Field(..., description="Search query")
    dao_id: Optional[str] = Field(None, description="Filter by DAO identifier")
    topic_id: Optional[int] = Field(None, description="Filter by specific topic")
    start_date: Optional[str] = Field(None, description=f"Filter posts created after this date. {DATE_DESCRIPTION}")
    end_date: Optional[str] = Field(None, description=f"Filter posts created before this date. {DATE_DESCRIPTION}")
    limit: int = Field(10, ge=1, le=50, description="Maximum results to return")


# ==================
# Social/Messaging Schemas
# ==================

class TelegramMessageResult(BaseModel):
    """Telegram message from DAO discussions."""
    dao_id: str = Field(..., description="DAO identifier")
    topic_id: int = Field(..., description="Topic cluster ID")
    topic_title: str = Field(..., description="Topic title")
    content: str = Field(..., description="Aggregated message content or summary")
    window_start: str = Field(..., description="Analysis window start")
    window_end: str = Field(..., description="Analysis window end")
    topic_representation: Optional[List[str]] = Field(None, description="Topic keywords")


class TelegramSearchInput(BaseModel):
    """Input for telegram search."""
    query: str = Field(..., description="Search query")
    dao_id: Optional[str] = Field(None, description="Filter by DAO identifier")
    start_date: Optional[str] = Field(None, description=f"Filter messages after this date. {DATE_DESCRIPTION}")
    end_date: Optional[str] = Field(None, description=f"Filter messages before this date. {DATE_DESCRIPTION}")
    limit: int = Field(10, ge=1, le=30, description="Maximum results to return")


class DiscordMessageResult(BaseModel):
    """Discord message from DAO channels."""
    date: str = Field(..., description="Message date")
    dao_id: str = Field(..., description="DAO identifier")
    content_summary: Optional[str] = Field(None, description="Summarized content")
    start_unix: int = Field(..., description="Earliest message timestamp")
    end_unix: int = Field(..., description="Latest message timestamp")


class DiscordSearchInput(BaseModel):
    """Input for discord search."""
    query: str = Field(..., description="Search query")
    dao_id: Optional[str] = Field(None, description="Filter by DAO identifier")
    start_date: Optional[str] = Field(None, description=f"Filter messages after this date. {DATE_DESCRIPTION}")
    end_date: Optional[str] = Field(None, description=f"Filter messages before this date. {DATE_DESCRIPTION}")
    limit: int = Field(10, ge=1, le=30, description="Maximum results to return")


# ==================
# GitHub Schemas
# ==================

class GitHubRepoResult(BaseModel):
    """GitHub repository metadata."""
    dao_id: int = Field(..., description="Internal DAO ID")
    github_org: str = Field(..., description="GitHub organization")
    repo_name: str = Field(..., description="Repository name")
    full_name: str = Field(..., description="Full repo name (org/repo)")
    description: Optional[str] = Field(None, description="Repository description")
    html_url: str = Field(..., description="GitHub URL")
    stargazers_count: Optional[int] = Field(None, description="Star count")
    forks_count: Optional[int] = Field(None, description="Fork count")


class GitHubCommitResult(BaseModel):
    """GitHub commit record."""
    sha: str = Field(..., description="Commit SHA")
    message: str = Field(..., description="Commit message")
    author_name: str = Field(..., description="Author name")
    date: str = Field(..., description="Commit date")
    repo_name: str = Field(..., description="Repository name")
    html_url: str = Field(..., description="Commit URL")


class GitHubSearchInput(BaseModel):
    """Input for GitHub repository search."""
    query: str = Field(..., description="Search query for repository descriptions and READMEs")
    dao_id: str = Field("", description="Filter by DAO identifier (integer ID). Leave empty to search all.")
    repo: str = Field("", description="Filter by repository name. Leave empty to search all.")
    limit: int = Field(10, ge=1, le=30, description="Maximum results to return")


class GitHubCommitsInput(BaseModel):
    """Input for GitHub commits search."""
    query: str = Field("", description="Search commit messages for keywords. Leave empty to get latest commits.")
    dao_id: str = Field("", description="Filter by DAO identifier (integer ID). Use dao_catalog to find.")
    author: str = Field("", description="Filter by author name or GitHub username.")
    repo: str = Field("", description="Filter by repository name (partial match).")
    start_date: str = Field("", description=f"Filter commits after this date. {DATE_DESCRIPTION}")
    end_date: str = Field("", description=f"Filter commits before this date. {DATE_DESCRIPTION}")
    limit: int = Field(20, ge=1, le=50, description="Maximum results to return")


class GitHubStatsInput(BaseModel):
    """Input for GitHub development statistics."""
    dao_id: str = Field("", description="Filter by DAO identifier (integer ID). Recommended for meaningful stats.")
    start_date: str = Field("", description=f"Filter commits after this date. {DATE_DESCRIPTION} Default: last 30 days.")
    end_date: str = Field("", description=f"Filter commits before this date. {DATE_DESCRIPTION}")


class GitHubBoardInput(BaseModel):
    """Input for GitHub project board search."""
    query: str = Field("", description="Search item titles for keywords. Leave empty to get all items.")
    status: str = Field("", description="Filter by status: Backlog, In Progress, This Sprint, Done")
    priority: str = Field("", description="Filter by priority: P0, P1, etc.")
    limit: int = Field(20, ge=1, le=50, description="Maximum results to return")


# ==================
# DAO Metadata Schemas
# ==================

class DAOInfo(BaseModel):
    """DAO metadata from internal.daos."""
    id: int = Field(..., description="Internal DAO ID")
    name: str = Field(..., description="DAO name")
    snapshot_id: Optional[str] = Field(None, description="Snapshot space ID")
    tally_id: Optional[str] = Field(None, description="Tally identifier")
    discourse_url: Optional[str] = Field(None, description="Forum URL")
    coingecko_token_id: Optional[str] = Field(None, description="CoinGecko token ID")


class DAOListInput(BaseModel):
    """Input for listing DAOs."""
    name: Optional[str] = Field(None, description="Filter by name (partial match)")
    limit: int = Field(20, ge=1, le=100, description="Maximum results to return")


# ==================
# Date Utility Functions
# ==================

def parse_date_to_timestamp(date_str: Optional[str]) -> Optional[int]:
    """Parse a date string (YYYY-MM-DD) to Unix timestamp."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return int(dt.timestamp())
    except ValueError:
        return None


def parse_date_to_iso(date_str: Optional[str]) -> Optional[str]:
    """Parse a date string (YYYY-MM-DD) to ISO format for SQL."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.isoformat()
    except ValueError:
        return None
