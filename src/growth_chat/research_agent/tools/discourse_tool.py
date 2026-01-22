"""Discourse forum search tool for Research Agent.

Searches DAO forum discussions using semantic search on discourse.discourse_embeddings_3072
(3072-dim vectors). Falls back to keyword search if no semantic results found.
"""
from typing import Any, Type

from pydantic import BaseModel, Field

from .base import SemanticSearchTool
from .schemas.common_schemas import DATE_DESCRIPTION


class DiscourseSearchInput(BaseModel):
    """Input for Discourse search."""
    query: str = Field("", description="Semantic search query (e.g., 'treasury management', 'delegate compensation'). Leave empty to get latest posts by date.")
    dao_id: str = Field("", description="Filter by DAO identifier. Leave empty to search all.")
    topic_id: int = Field(0, description="Filter by specific topic ID. Use 0 to search all topics.")
    start_date: str = Field("", description=f"Filter posts created after this date. {DATE_DESCRIPTION} Leave empty for no filter.")
    end_date: str = Field("", description=f"Filter posts created before this date. {DATE_DESCRIPTION} Leave empty for no filter.")
    limit: int = Field(10, ge=1, le=50, description="Maximum results to return")


class DiscourseSearchTool(SemanticSearchTool):
    """Search Discourse forum posts about DAO governance.
    
    Uses semantic search on discourse.discourse_embeddings_3072 (3072-dim vectors)
    to find forum discussions, proposal debates, and community conversations.
    Falls back to keyword search on discourse.posts if no semantic results.
    """
    
    name: str = "discourse_search"
    description: str = """Search Discourse forum posts about DAO governance.

INPUT:
- query: Semantic search (e.g., 'delegate rewards', 'treasury diversification'). Leave EMPTY to get latest posts by date.
- dao_id: Filter by DAO identifier
- topic_id: Filter by specific forum topic
- start_date/end_date: Filter by date range (YYYY-MM-DD format)
- limit: Max results (default 10)

RETURNS: Forum posts with topic title, content summary, DAO, and timestamps.

USE FOR: Governance discussions, proposal feedback, community debates, sentiment analysis.

IMPORTANT:
- For "latest" or "recent" posts: Leave query EMPTY - returns most recent by date
- For topic search: Provide query - returns most relevant by semantic match

TIPS:
- Use this alongside proposal tools to find discussions about specific proposals
- For recent activity, use start_date (e.g., "past 3 months" = start_date 3 months ago)
- Combine with telegram_search/discord_search for broader community sentiment
- If no results, try broader query terms or remove dao_id filter"""
    args_schema: Type[BaseModel] = DiscourseSearchInput
    
    def _run_tool(
        self,
        query: str = "",
        dao_id: str = "",
        topic_id: int = 0,
        start_date: str = "",
        end_date: str = "",
        limit: int = 10,
        **kwargs: Any,
    ) -> str:
        """Execute discourse search.
        
        Uses semantic search on discourse.discourse_embeddings_3072 (3072-dim).
        Falls back to keyword search if no semantic results.
        If query is empty, returns latest posts by date.
        """
        client = self._get_db_client()
        
        # Convert empty strings/0 to None
        results = client.search_discourse(
            query=query if query.strip() else None,
            dao_id=dao_id if dao_id else None,
            topic_id=str(topic_id) if topic_id else None,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None,
            limit=limit,
        )
        
        if not results:
            filter_msg = []
            if dao_id:
                filter_msg.append(f"DAO '{dao_id}'")
            if query:
                filter_msg.append(f"matching '{query}'")
            if start_date or end_date:
                filter_msg.append(f"date range {start_date or 'any'} to {end_date or 'now'}")
            msg = "No forum posts found" + (" " + " and ".join(filter_msg) if filter_msg else "")
            msg += "\n\nTIP: Try broader search terms, or use telegram_search/discord_search for community discussions."
            return msg
        
        # Prepare preview data for frontend cards
        preview_data = []
        output_lines = [f"Found {len(results)} forum posts:\n"]
        
        for i, post in enumerate(results, 1):
            title = post.get("topic_title", "Untitled")
            # content_summary may be JSONB - extract summary text if dict
            content_raw = post.get("content_summary", "")
            if isinstance(content_raw, dict):
                content = str(content_raw.get("summary", content_raw))[:300]
            else:
                content = str(content_raw)[:300] if content_raw else ""
            
            dao = post.get("dao_id", "Unknown")
            topic_id_val = post.get("topic_id")
            created_at = post.get("created_at")
            
            # Add to preview data for frontend card
            preview_data.append({
                "id": str(topic_id_val) if topic_id_val else str(i),
                "title": title,
                "content": content[:200] if content else "",
                "source": "discourse",
                "dao_id": dao,
                "topic_id": topic_id_val,
                "created_at": created_at,
            })
            
            # Text summary
            output_lines.append(f"**{i}. {title}**")
            output_lines.append(f"  - DAO: {dao}")
            if created_at:
                output_lines.append(f"  - Date: {str(created_at)[:10]}")
            if content:
                output_lines.append(f"  - {content[:150]}...")
            output_lines.append("")
        
        # Combine preview block with text summary
        preview_block = self._format_preview_block("discussion", preview_data)
        return preview_block + "\n\n" + "\n".join(output_lines)
