"""Schemas for GitHub activity tool.

Defines input/output types for GitHub repository queries.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class GitHubSearchInput(BaseModel):
    """Input schema for GitHub search."""
    query: str = Field(..., description="Search query for GitHub repositories")
    dao_id: Optional[str] = Field(None, description="Internal DAO ID to filter")
    repo: Optional[str] = Field(None, description="Repository name to filter")
    limit: int = Field(10, ge=1, le=30, description="Maximum results to return")


class GitHubRepoOutput(BaseModel):
    """Output schema for a single GitHub repository."""
    dao_id: int = Field(..., description="Internal DAO ID")
    github_org: str = Field(..., description="GitHub organization name")
    repo_name: str = Field(..., description="Repository name")
    full_name: str = Field(..., description="Full repository name (org/repo)")
    description: Optional[str] = Field(None, description="Repository description")
    html_url: str = Field(..., description="GitHub repository URL")
    stargazers_count: Optional[int] = Field(None, description="Number of stars")
    forks_count: Optional[int] = Field(None, description="Number of forks")
    distance: Optional[float] = Field(None, description="Semantic similarity distance")


class GitHubSearchOutput(BaseModel):
    """Output schema for GitHub search results."""
    query: str = Field(..., description="Original search query")
    total_results: int = Field(..., description="Number of results found")
    repositories: List[GitHubRepoOutput] = Field(default_factory=list, description="Matching repositories")

