"""GitHub tools for Research Agent.

Searches DAO GitHub repositories, commits, stats, and project boards.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from .base import ResearchBaseTool, SemanticSearchTool
from .schemas.common_schemas import (
    GitHubBoardInput,
    GitHubCommitsInput,
    GitHubSearchInput,
    GitHubStatsInput,
)


class GitHubReposTool(SemanticSearchTool):
    """Search GitHub repositories for DAOs.
    
    Searches the github.github_metadata table for repository information
    including stars, forks, and descriptions.
    """
    
    name: str = "github_repos"
    description: str = """Search GitHub repositories for DAOs.
Input: query (required), dao_id (optional), repo (optional), limit (optional)
Returns: Repositories with org, name, description, stars, forks, and GitHub URL.
Use for: Finding DAO codebases, documentation, most popular repos."""
    args_schema: Type[BaseModel] = GitHubSearchInput
    
    def _run_tool(
        self,
        query: str,
        dao_id: str = "",
        repo: str = "",
        limit: int = 10,
        **kwargs: Any,
    ) -> str:
        """Execute GitHub search."""
        client = self._get_db_client()
        
        # Convert dao_id to int if provided (empty string = None)
        dao_id_int = None
        if dao_id:
            try:
                dao_id_int = int(dao_id)
            except ValueError:
                pass
        
        results = client.search_github(
            query=query,
            dao_id=dao_id_int,
            repo=repo,
            limit=limit,
        )
        
        if not results:
            filter_msg = []
            if dao_id:
                filter_msg.append(f"DAO ID {dao_id}")
            if repo:
                filter_msg.append(f"repo '{repo}'")
            return f"No GitHub repositories found matching '{query}'" + (" for " + " and ".join(filter_msg) if filter_msg else "")
        
        # Prepare preview data for frontend cards
        preview_data = []
        output = [f"Found {len(results)} GitHub repositories:\n"]
        
        for i, gh in enumerate(results, 1):
            full_name = gh.get("full_name", "Unknown")
            org = gh.get("github_org", "")
            repo_name = gh.get("repo_name", "")
            description = (gh.get("description") or "")[:200]
            url = gh.get("html_url", "")
            stars = gh.get("stargazers_count", 0)
            forks = gh.get("forks_count", 0)
            
            # Add to preview data for frontend card
            preview_data.append({
                "full_name": full_name,
                "org": org,
                "repo": repo_name,
                "description": description[:120] if description else "",
                "stars": stars,
                "forks": forks,
                "url": url,
            })
            
            output.append(f"**{i}. {full_name}**")
            if description:
                output.append(f"  - Description: {description}")
            output.append(f"  - Stars: {stars:,} | Forks: {forks:,}")
            if url:
                output.append(f"  - URL: {url}")
            output.append("")
        
        # Combine preview block with text summary
        preview_block = self._format_preview_block("github", preview_data)
        return preview_block + "\n\n" + "\n".join(output)


class GitHubCommitsTool(SemanticSearchTool):
    """Search GitHub commit history for DAOs.
    
    Searches the github.github_commits_daos table for commit messages,
    authors, and dates.
    """
    
    name: str = "github_commits"
    description: str = """Search GitHub commit history for DAOs.
Input: query (optional), dao_id (optional), author (optional), repo (optional), start_date, end_date, limit
Returns: Commits with message, author, date, repo, and commit URL.
Use for: Finding what DAOs have been working on, tracking development activity, finding commits by author or topic."""
    args_schema: Type[BaseModel] = GitHubCommitsInput
    
    def _run_tool(
        self,
        query: str = "",
        dao_id: str = "",
        author: str = "",
        repo: str = "",
        start_date: str = "",
        end_date: str = "",
        limit: int = 20,
        **kwargs: Any,
    ) -> str:
        """Execute GitHub commits search."""
        client = self._get_db_client()
        
        # Convert dao_id to int if provided
        dao_id_int = None
        if dao_id:
            try:
                dao_id_int = int(dao_id)
            except ValueError:
                pass
        
        results = client.search_github_commits_daos(
            query=query if query else None,
            dao_id=dao_id_int,
            author=author if author else None,
            repo=repo if repo else None,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None,
            limit=limit,
        )
        
        if not results:
            filter_parts = []
            if dao_id:
                filter_parts.append(f"DAO ID {dao_id}")
            if author:
                filter_parts.append(f"author '{author}'")
            if repo:
                filter_parts.append(f"repo '{repo}'")
            if query:
                filter_parts.append(f"query '{query}'")
            filter_msg = " for " + " and ".join(filter_parts) if filter_parts else ""
            return f"No GitHub commits found{filter_msg}."
        
        # Prepare preview data for frontend cards
        preview_data = []
        output = [f"Found {len(results)} commits:\n"]
        
        for i, commit in enumerate(results, 1):
            sha = commit.get("sha", "")[:7]
            message = (commit.get("message") or "")[:100]
            # Clean up multi-line messages
            message = message.split("\n")[0]
            author_name = commit.get("author_name", "")
            username = commit.get("github_username", "")
            date_val = commit.get("date", "")
            repo_name = commit.get("repo_name", "")
            org = commit.get("github_org", "")
            url = commit.get("html_url", "")
            
            # Format date
            date_str = ""
            if date_val:
                if isinstance(date_val, datetime):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)[:10]
            
            # Add to preview data
            preview_data.append({
                "sha": sha,
                "message": message[:80] if message else "",
                "author": username or author_name,
                "date": date_str,
                "repo": f"{org}/{repo_name}" if org else repo_name,
                "url": url,
            })
            
            output.append(f"**{i}. [{sha}] {message}**")
            output.append(f"  - Author: {username or author_name}")
            output.append(f"  - Repo: {org}/{repo_name}")
            output.append(f"  - Date: {date_str}")
            if url:
                output.append(f"  - URL: {url}")
            output.append("")
        
        preview_block = self._format_preview_block("github-commits", preview_data)
        return preview_block + "\n\n" + "\n".join(output)


class GitHubStatsTool(SemanticSearchTool):
    """Get GitHub development statistics for DAOs.
    
    Aggregates commit data to show activity metrics, top contributors,
    and most active repositories.
    """
    
    name: str = "github_stats"
    description: str = """Get GitHub development statistics for DAOs.
Input: dao_id (recommended), start_date (optional, default: 30 days), end_date (optional)
Returns: Total commits, unique contributors, top contributors, most active repos, weekly trends.
Use for: Measuring development activity, identifying key contributors, tracking project velocity."""
    args_schema: Type[BaseModel] = GitHubStatsInput
    
    def _run_tool(
        self,
        dao_id: str = "",
        start_date: str = "",
        end_date: str = "",
        **kwargs: Any,
    ) -> str:
        """Execute GitHub stats query."""
        client = self._get_db_client()
        
        # Convert dao_id to int if provided
        dao_id_int = None
        if dao_id:
            try:
                dao_id_int = int(dao_id)
            except ValueError:
                pass
        
        # Default to last 30 days if no date specified
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        stats = client.get_github_stats(
            dao_id=dao_id_int,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None,
        )
        
        total_commits = stats.get("total_commits", 0)
        unique_contributors = stats.get("unique_contributors", 0)
        top_contributors = stats.get("top_contributors", [])
        active_repos = stats.get("active_repos", [])
        weekly_commits = stats.get("weekly_commits", [])
        
        if total_commits == 0:
            filter_msg = f" for DAO ID {dao_id}" if dao_id else ""
            return f"No GitHub activity found{filter_msg} since {start_date}."
        
        output = [f"## GitHub Development Statistics\n"]
        output.append(f"**Period**: {start_date} to {end_date or 'now'}")
        if dao_id:
            output.append(f"**DAO ID**: {dao_id}")
        output.append("")
        
        output.append(f"### Summary")
        output.append(f"- **Total Commits**: {total_commits:,}")
        output.append(f"- **Unique Contributors**: {unique_contributors}")
        output.append("")
        
        if top_contributors:
            output.append("### Top Contributors")
            for i, contrib in enumerate(top_contributors[:5], 1):
                name = contrib.get("contributor", "Unknown")
                count = contrib.get("commit_count", 0)
                output.append(f"{i}. **{name}** - {count:,} commits")
            output.append("")
        
        if active_repos:
            output.append("### Most Active Repositories")
            for i, repo in enumerate(active_repos[:5], 1):
                repo_name = repo.get("repo_name", "Unknown")
                org = repo.get("github_org", "")
                count = repo.get("commit_count", 0)
                full_name = f"{org}/{repo_name}" if org else repo_name
                output.append(f"{i}. **{full_name}** - {count:,} commits")
            output.append("")
        
        if weekly_commits:
            output.append("### Weekly Commit Trend (Recent)")
            for week_data in weekly_commits[:8]:
                week = week_data.get("week", "")
                commits = week_data.get("commits", 0)
                if week:
                    week_str = week.strftime("%Y-%m-%d") if isinstance(week, datetime) else str(week)[:10]
                    output.append(f"- Week of {week_str}: {commits} commits")
        
        return "\n".join(output)


class GitHubBoardTool(ResearchBaseTool):
    """Search GitHub project board items.
    
    Searches the github.github_board table for roadmap items,
    priorities, and project status.
    """
    
    name: str = "github_board"
    description: str = """Search GitHub project board for roadmap and priorities.
Input: query (optional), status (optional: Backlog, In Progress, This Sprint, Done), priority (optional: P0, P1), limit
Returns: Board items with title, status, priority, and URL.
Use for: Finding project roadmap, current priorities, backlog items, what's being worked on."""
    args_schema: Type[BaseModel] = GitHubBoardInput
    
    def _run_tool(
        self,
        query: str = "",
        status: str = "",
        priority: str = "",
        limit: int = 20,
        **kwargs: Any,
    ) -> str:
        """Execute GitHub board search."""
        client = self._get_db_client()
        
        results = client.search_github_board(
            query=query if query else None,
            status=status if status else None,
            priority=priority if priority else None,
            limit=limit,
        )
        
        if not results:
            filter_parts = []
            if query:
                filter_parts.append(f"query '{query}'")
            if status:
                filter_parts.append(f"status '{status}'")
            if priority:
                filter_parts.append(f"priority '{priority}'")
            filter_msg = " with " + " and ".join(filter_parts) if filter_parts else ""
            return f"No GitHub board items found{filter_msg}."
        
        # Group by status for better readability
        by_status: Dict[str, List[Dict]] = {}
        for item in results:
            item_status = item.get("status", "Unknown")
            if item_status not in by_status:
                by_status[item_status] = []
            by_status[item_status].append(item)
        
        output = [f"Found {len(results)} board items:\n"]
        
        # Display order
        status_order = ["In Progress", "This Sprint", "Backlog", "Done"]
        displayed = set()
        
        for s in status_order:
            if s in by_status:
                output.append(f"### {s}")
                for item in by_status[s]:
                    title = item.get("title", "Untitled")
                    priority_val = item.get("priority", "")
                    url = item.get("url", "")
                    priority_badge = f" [{priority_val}]" if priority_val else ""
                    output.append(f"- **{title}**{priority_badge}")
                    if url:
                        output.append(f"  {url}")
                output.append("")
                displayed.add(s)
        
        # Any remaining statuses
        for s, items in by_status.items():
            if s not in displayed:
                output.append(f"### {s}")
                for item in items:
                    title = item.get("title", "Untitled")
                    priority_val = item.get("priority", "")
                    url = item.get("url", "")
                    priority_badge = f" [{priority_val}]" if priority_val else ""
                    output.append(f"- **{title}**{priority_badge}")
                    if url:
                        output.append(f"  {url}")
                output.append("")
        
        return "\n".join(output)

