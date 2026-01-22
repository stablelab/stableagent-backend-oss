"""Telegram message search tool for Research Agent.

Searches DAO Telegram discussions using unified_telegram table.
"""
from typing import Any, Type

from pydantic import BaseModel, Field

from .base import SemanticSearchTool
from .schemas.common_schemas import DATE_DESCRIPTION


class TelegramSearchInput(BaseModel):
    """Input for Telegram search."""
    query: str = Field(..., description="Search query (e.g., 'governance', 'token launch', 'community concerns')")
    dao_id: str = Field("", description="Filter by DAO name or snapshot_id (e.g., 'gnosis.eth', 'Lido', 'arbitrum'). Use dao_catalog to find correct ID. Leave empty to search all.")
    start_date: str = Field("", description=f"Filter messages after this date. {DATE_DESCRIPTION} Leave empty for no filter.")
    end_date: str = Field("", description=f"Filter messages before this date. {DATE_DESCRIPTION} Leave empty for no filter.")
    limit: int = Field(10, ge=1, le=30, description="Maximum results to return")


class TelegramSearchTool(SemanticSearchTool):
    """Search Telegram messages from DAO communities.
    
    Searches the unified_telegram table which contains aggregated
    telegram messages grouped by topic and time window.
    """
    
    name: str = "telegram_search"
    description: str = """Search Telegram messages from DAO communities.

INPUT:
- query: Semantic search (e.g., 'governance concerns', 'token price', 'community feedback')
- dao_id: Filter by DAO identifier
- start_date/end_date: Filter by date range (YYYY-MM-DD format)
- limit: Max results (default 10)

RETURNS: Aggregated messages with topic, content summary, keywords, and time window.

USE FOR: Community sentiment, informal discussions, real-time reactions, grassroots feedback.

TIPS:
- Telegram often has more candid discussions than forums
- Use with discord_search for broader community sentiment picture
- For official discussions, prefer discourse_search
- Good for questions like "what is the community saying about X"
- If no results, the DAO may not have Telegram data indexed"""
    args_schema: Type[BaseModel] = TelegramSearchInput
    
    def _run_tool(
        self,
        query: str,
        dao_id: str = "",
        start_date: str = "",
        end_date: str = "",
        limit: int = 10,
        **kwargs: Any,
    ) -> str:
        """Execute telegram search.
        
        unified_telegram columns: dao_id, window_number, topic_id, topic_title, 
        content, topic_representation, embedding, start_unix, end_unix
        """
        client = self._get_db_client()
        
        # Pass dao_id as string - unified_telegram.dao_id is text (e.g., "gnosis.eth")
        results = client.search_telegram(
            query=query,
            dao_id=dao_id if dao_id else None,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None,
            limit=limit,
        )
        
        if not results:
            msg = f"No Telegram messages found matching '{query}'" + (f" for DAO '{dao_id}'" if dao_id else "")
            msg += "\n\nTIP: Try discord_search or discourse_search for other community channels."
            return msg
        
        # Prepare preview data for frontend cards
        preview_data = []
        output_lines = [f"Found {len(results)} Telegram discussion topics:\n"]
        
        for i, msg in enumerate(results, 1):
            topic_title = msg.get("topic_title", "General Discussion")
            content = (msg.get("content") or "")[:300]
            dao = msg.get("dao_id", "Unknown")
            window = msg.get("window_number", "")
            topic_id = msg.get("topic_id")
            topic_rep = msg.get("topic_representation", [])
            start_unix = msg.get("start_unix")
            end_unix = msg.get("end_unix")
            
            # Keywords for display
            keywords = ", ".join(topic_rep[:5]) if topic_rep and isinstance(topic_rep, list) else ""
            
            # Use dao_id + window + topic_id as unique identifier
            unique_id = f"{dao}-w{window}-t{topic_id}" if topic_id else f"{dao}-w{window}-{i}"
            
            # Add to preview data for frontend card
            preview_data.append({
                "id": unique_id,
                "title": topic_title,
                "content": content[:200] if content else keywords[:200],
                "source": "telegram",
                "dao_id": dao,
                "channel": f"Window {window}" if window else None,
                "start_unix": start_unix,
                "end_unix": end_unix,
            })
            
            # Text summary
            output_lines.append(f"**{i}. {topic_title}**")
            output_lines.append(f"  - DAO: {dao}" + (f" | Window: {window}" if window else ""))
            if keywords:
                output_lines.append(f"  - Keywords: {keywords}")
            if content:
                output_lines.append(f"  - {content[:150]}...")
            output_lines.append("")
        
        # Combine preview block with text summary
        preview_block = self._format_preview_block("discussion", preview_data)
        return preview_block + "\n\n" + "\n".join(output_lines)
