"""Tally on-chain proposals search tool for Research Agent.

Searches on-chain governance proposals from Tally.
"""
from typing import Any, Type

from pydantic import BaseModel, Field

from .base import SemanticSearchTool
from .schemas.common_schemas import DATE_DESCRIPTION


class TallySearchInput(BaseModel):
    """Input for Tally proposal search."""
    query: str = Field("", description="Semantic search query for proposals (e.g., 'treasury', 'parameter change'). Leave empty to get latest proposals by date.")
    dao_id: str = Field("", description="Tally DAO identifier - can be the org_id (e.g., '2206072050458560434') or slug (e.g., 'uniswap'). Use dao_catalog to find the correct tally_id. Leave empty for all.")
    state: str = Field("", description="Filter by state: active, executed, defeated, queued. Leave empty for all states.")
    start_date: str = Field("", description=f"Filter proposals created after this date. {DATE_DESCRIPTION} Leave empty for no filter.")
    end_date: str = Field("", description=f"Filter proposals created before this date. {DATE_DESCRIPTION} Leave empty for no filter.")
    limit: int = Field(10, ge=1, le=50, description="Maximum results to return")


class TallyProposalsTool(SemanticSearchTool):
    """Search Tally on-chain governance proposals.
    
    Searches the unified_proposals table filtered by source='tally'.
    Returns proposal details with on-chain voting results and links.
    """
    
    name: str = "tally_proposals"
    description: str = """Search Tally on-chain governance proposals.

INPUT:
- query: Semantic search (e.g., 'treasury', 'parameter change'). Leave EMPTY to get latest proposals by date.
- dao_id: Tally DAO identifier - supports BOTH org_id (e.g., '2206072050458560434') and slug (e.g., 'uniswap'). Use dao_catalog first to get the ID.
- state: active/executed/defeated/queued
- start_date/end_date: Filter by date range (YYYY-MM-DD format)
- limit: Max results (default 10)

RETURNS: On-chain proposals with title, body, for/against votes, state, and Tally link.

USE FOR: On-chain governance, executable proposals, governor contracts, binding votes.

IMPORTANT:
- For "latest" or "recent" proposals: Leave query EMPTY - returns most recent by date
- For topic search: Provide query - returns most relevant by semantic match

TIPS:
- Use dao_catalog first to find the correct tally_id (org_id) for a DAO
- Combine with votes_lookup to analyze specific proposal voting patterns
- If no results, try snapshot_proposals for off-chain votes"""
    args_schema: Type[BaseModel] = TallySearchInput
    
    def _run_tool(
        self,
        query: str = "",
        dao_id: str = "",
        state: str = "",
        start_date: str = "",
        end_date: str = "",
        limit: int = 10,
        **kwargs: Any,
    ) -> str:
        """Execute tally proposals search."""
        client = self._get_db_client()
        
        # If no query provided, get latest proposals ordered by date
        # If query provided, use semantic search ordered by relevance
        results = client.search_proposals(
            query=query if query.strip() else None,  # None = order by date
            source="tally",
            dao_id=dao_id if dao_id else None,
            state=state if state else None,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None,
            limit=limit,
        )
        
        if not results:
            filter_msg = []
            if dao_id:
                filter_msg.append(f"DAO '{dao_id}'")
            if state:
                filter_msg.append(f"state '{state}'")
            if query:
                filter_msg.append(f"matching '{query}'")
            if start_date or end_date:
                filter_msg.append(f"date range {start_date or 'any'} to {end_date or 'now'}")
            msg = f"No Tally proposals found" + (" " + " and ".join(filter_msg) if filter_msg else "")
            msg += "\n\nTIP: Try using dao_catalog to verify the tally_id, or check snapshot_proposals for off-chain votes."
            return msg
        
        # Prepare preview data for frontend cards
        preview_data = []
        output_lines = [f"Found {len(results)} Tally on-chain proposals:\n"]
        
        for i, prop in enumerate(results, 1):
            title = prop.get("title", "Untitled")
            body = (prop.get("body") or "")[:200] # CHECK : we are only getting 500 from query and taking only 200
            state_val = prop.get("state", "Unknown")
            prop_id = prop.get("proposal_id", "")
            created_at = prop.get("created_at")
            ends_at = prop.get("ends_at")
            choices = prop.get("choices")
            scores = prop.get("scores")
            discourse_topic_id = prop.get("discourse_topic_id")
            dao = prop.get("dao_id")
            
            # Construct Tally link
            link = f"https://www.tally.xyz/gov/{dao}/proposal/{prop_id}" if dao and prop_id else ""
            
            # Add to preview data for frontend card
            preview_data.append({
                "id": prop_id,
                "title": title,
                "source": "tally",
                "dao_id": dao,
                "state": state_val,
                "choices": choices,
                "scores": scores,
                "discourse_topic_id": discourse_topic_id,
                "created_at": created_at,
                "ends_at": ends_at,
                "link": link,
                "body_preview": body[:150] if body else None,
            })
            
            # Text summary
            output_lines.append(f"**{i}. {title}**")
            output_lines.append(f"  - DAO: {dao} | State: {state_val}")
            if created_at:
                output_lines.append(f"  - Created: {str(created_at)[:10]}")
            
            if choices is not None and scores is not None:
                output_lines.append(f"  - {self._format_choices_scores(choices, scores)}")
                
            if discourse_topic_id:
                output_lines.append(f"  - Discourse Topic ID: {discourse_topic_id}")

            if link:
                output_lines.append(f"  - [View on Tally]({link})")
            output_lines.append("")
        
        # Combine preview block with text summary
        preview_block = self._format_preview_block("proposal", preview_data)
        # return preview_block + "\n\n" + "\n".join(output_lines)
        return output_lines, preview_block
    
    def _format_votes(self, votes: Any) -> str:
        """Format vote counts for readability (handle wei-denominated values)."""
        if votes is None:
            return "N/A"
        try:
            v = float(votes)
            # Check if value looks like wei (very large number)
            if v >= 1e18:
                v = v / 1e18
            
            if v >= 1_000_000:
                return f"{v/1_000_000:.2f}M"
            elif v >= 1_000:
                return f"{v/1_000:.1f}K"
            else:
                return f"{v:.0f}"
        except (ValueError, TypeError):
            return str(votes)
    
    def _format_choices_scores(self, choices: list, scores: list) -> str:
        """
        Formats votes in a single-line, LLM-friendly key=value style.
        Example:
        Votes: choice="[1] Future 1, Pair 0" score=2.97M | choice="[1] Future 1, Pair 1" score=1.30M
        """
        if not choices or not scores or len(choices) != len(scores):
            return "Votes: N/A"

        return "Votes: " + " | ".join(
            f'choice="{choice}" score={self._format_votes(score)}'
            for choice, score in zip(choices, scores)
        )
