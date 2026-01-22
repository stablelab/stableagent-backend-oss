"""Discord message search tool for Research Agent.

Searches DAO Discord discussions using unified_discord table.
"""
from typing import Any, Type

from pydantic import BaseModel, Field

from .base import SemanticSearchTool
from .schemas.common_schemas import DATE_DESCRIPTION


class DiscordSearchInput(BaseModel):
    """Input for Discord search."""
    query: str = Field(..., description="Search query (e.g., 'governance', 'airdrop', 'community concerns')")
    dao_id: str = Field("", description="Filter by DAO identifier. Leave empty to search all.")
    start_date: str = Field("", description=f"Filter messages after this date. {DATE_DESCRIPTION} Leave empty for no filter.")
    end_date: str = Field("", description=f"Filter messages before this date. {DATE_DESCRIPTION} Leave empty for no filter.")
    limit: int = Field(10, ge=1, le=30, description="Maximum results to return")


class DiscordSearchTool(SemanticSearchTool):
    """Search Discord messages from DAO communities.
    
    Searches the unified_discord table which contains aggregated
    discord messages grouped by date.
    """
    
    name: str = "discord_search"
    description: str = """Search Discord messages from DAO communities.

INPUT:
- query: Semantic search (e.g., 'airdrop concerns', 'governance feedback', 'token price')
- dao_id: Filter by DAO identifier
- start_date/end_date: Filter by date range (YYYY-MM-DD format)
- limit: Max results (default 10)

RETURNS: Aggregated messages with date, content summary, and time range.

USE FOR: Community discussions, governance conversations, DAO announcements, sentiment analysis.

TIPS:
- Discord often has real-time community reactions
- Use with telegram_search for broader social sentiment
- For formal discussions, prefer discourse_search
- Good for understanding community mood and concerns
- If no results, the DAO may not have Discord data indexed"""
    args_schema: Type[BaseModel] = DiscordSearchInput
    
    def _run_tool(
        self,
        query: str,
        dao_id: str = "",
        start_date: str = "",
        end_date: str = "",
        limit: int = 10,
        **kwargs: Any,
    ) -> str:
        """Execute discord search.
        
        unified_discord columns: date, dao_id, start_unix, end_unix, 
        content (jsonb), content_summary (jsonb), embedding
        """
        client = self._get_db_client()
        
        # Convert empty strings to None
        results = client.search_discord(
            query=query,
            dao_id=dao_id if dao_id else None,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None,
            limit=limit,
        )
        
        if not results:
            msg = f"No Discord messages found matching '{query}'" + (f" for DAO '{dao_id}'" if dao_id else "")
            msg += "\n\nTIP: Try telegram_search or discourse_search for other community channels."
            return msg
        
        # Prepare preview data for frontend cards
        preview_data = []
        output_lines = [f"Found {len(results)} Discord discussion periods:\n"]
        
        for i, msg in enumerate(results, 1):
            date = msg.get("date", "Unknown date")
            # content_summary is JSONB - extract summary if dict
            content_raw = msg.get("content_summary", "")
            if isinstance(content_raw, dict):
                content = str(content_raw.get("summary", content_raw))[:300]
            else:
                content = str(content_raw)[:300] if content_raw else ""
            
            dao = msg.get("dao_id", "Unknown")
            start = msg.get("start_unix", 0)
            
            # Use dao + date + start_unix as unique identifier
            unique_id = f"{dao}-{date}-{start}"
            
            # Add to preview data for frontend card
            preview_data.append({
                "id": unique_id,
                "title": f"{dao} - {date}",
                "content": content[:200] if content else "",
                "source": "discord",
                "dao_id": dao,
                "channel": str(date),  # Using date as a pseudo-channel for display
                "timestamp": str(start) if start else None,
            })
            
            # Text summary
            output_lines.append(f"**{i}. {dao} - {date}**")
            output_lines.append(f"  - DAO: {dao}")
            if content:
                output_lines.append(f"  - Summary: {content[:150]}...")
            output_lines.append("")
        
        # Combine preview block with text summary
        preview_block = self._format_preview_block("discussion", preview_data)
        return preview_block + "\n\n" + "\n".join(output_lines)
