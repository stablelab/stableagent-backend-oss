"""Active proposals search tool for Research Agent.

Searches currently running/active governance proposals from Snapshot and on-chain sources.
Uses internal.socket_snapshot_proposals and internal.socket_onchain_proposals tables.
"""
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from src.services.connection_pool import get_connection_pool
from src.utils.logger import logger

from .base import ResearchBaseTool


class ActiveProposalsInput(BaseModel):
    """Input for active proposals search."""
    query: str = Field(
        "",
        description="Search query for proposal title/body (e.g., 'treasury', 'grants'). Leave empty to list all active proposals."
    )
    dao_id: str = Field(
        "",
        description="Filter by DAO identifier - Snapshot space (e.g., 'aave.eth') or on-chain name. Use dao_catalog to find the correct ID. Leave empty for all."
    )
    source: str = Field(
        "",
        description="Filter by source: 'snapshot' or 'onchain'. Leave empty for both."
    )
    limit: int = Field(
        10,
        ge=1,
        le=30,
        description="Maximum results to return"
    )


class ActiveProposalsTool(ResearchBaseTool):
    """Search currently active/running governance proposals.
    
    Searches real-time active proposals from both Snapshot (off-chain) and
    on-chain governance systems. Returns proposals that are currently open
    for voting with live vote tallies.
    """
    
    name: str = "active_proposals"
    description: str = """Search currently active/running governance proposals.

INPUT:
- query: Search text for title/body (optional - leave empty to list all active)
- dao_id: DAO identifier (Snapshot space like 'aave.eth' or on-chain name)
- source: 'snapshot' or 'onchain' (optional - leave empty for both)
- limit: Max results (default 10)

RETURNS: Active proposals with title, voting progress, time remaining, and links.

USE FOR:
- Finding proposals currently open for voting
- Checking active governance decisions across DAOs
- Monitoring real-time voting progress
- Answering "what's being voted on right now?"

TIPS:
- Use dao_catalog first to find the correct DAO identifier
- Results include live vote tallies (scores) and time remaining
- Combines both Snapshot and on-chain proposals
- For historical/closed proposals, use snapshot_proposals or tally_proposals instead"""
    
    args_schema: Type[BaseModel] = ActiveProposalsInput
    
    def _run_tool(
        self,
        query: str = "",
        dao_id: str = "",
        source: str = "",
        limit: int = 10,
        **kwargs: Any,
    ) -> str:
        """Execute active proposals search."""
        limit = max(1, min(30, limit))
        
        try:
            results = self._search_active_proposals(
                query=query if query else None,
                dao_id=dao_id if dao_id else None,
                source=source if source else None,
                limit=limit,
            )
            
            if not results:
                filter_msg = []
                if dao_id:
                    filter_msg.append(f"DAO '{dao_id}'")
                if source:
                    filter_msg.append(f"source '{source}'")
                if query:
                    filter_msg.append(f"matching '{query}'")
                msg = "No active proposals found" + (" for " + " and ".join(filter_msg) if filter_msg else "")
                msg += "\n\nTIP: Use dao_catalog to verify the DAO identifier, or try snapshot_proposals/tally_proposals for historical proposals."
                return msg
            
            return self._format_results(results, query)
            
        except Exception as e:
            logger.error(f"[ActiveProposalsTool] Error: {e}", exc_info=True)
            return f"Error searching active proposals: {str(e)}"
    
    def _search_active_proposals(
        self,
        query: Optional[str],
        dao_id: Optional[str],
        source: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Search for active proposals from both Snapshot and on-chain sources."""
        pool = get_connection_pool()
        conn = pool.get_connection()
        
        try:
            cursor = conn.cursor()
            results = []
            
            # Query Snapshot active proposals if source allows
            if not source or source.lower() == "snapshot":
                snapshot_results = self._query_snapshot_active(cursor, query, dao_id, limit)
                results.extend(snapshot_results)
            
            # Query on-chain active proposals if source allows
            if not source or source.lower() == "onchain":
                onchain_results = self._query_onchain_active(cursor, query, dao_id, limit)
                results.extend(onchain_results)
            
            # Sort by end time (soonest ending first)
            results.sort(key=lambda x: x.get("end", 0) or float("inf"))
            
            return results[:limit]
            
        finally:
            pool.return_connection(conn)
    
    def _query_snapshot_active(
        self,
        cursor,
        query: Optional[str],
        dao_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Query active Snapshot proposals."""
        conditions = ["active = true"]
        params: List[Any] = []
        
        if dao_id:
            # Match on snapshot_id or snapshot_name
            conditions.append("(snapshot_id ILIKE %s OR snapshot_name ILIKE %s)")
            params.extend([f"%{dao_id}%", f"%{dao_id}%"])
        
        if query:
            conditions.append("(title ILIKE %s OR body ILIKE %s)")
            params.extend([f"%{query}%", f"%{query}%"])
        
        sql = f"""
            SELECT 
                id,
                title,
                body,
                snapshot_id,
                snapshot_name,
                state,
                "start" as start_ts,
                "end" as end_ts,
                author,
                choices,
                scores,
                last_updated,
                'snapshot' as source
            FROM internal.socket_snapshot_proposals
            WHERE {' AND '.join(conditions)}
            ORDER BY "end" ASC
            LIMIT %s
        """
        params.append(limit)
        
        try:
            cursor.execute(sql, params)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[ActiveProposalsTool] Snapshot query error: {e}")
            return []
    
    def _query_onchain_active(
        self,
        cursor,
        query: Optional[str],
        dao_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Query active on-chain proposals."""
        conditions = ["active = true"]
        params: List[Any] = []
        
        if dao_id:
            # Match on name or address
            conditions.append("(name ILIKE %s OR address ILIKE %s)")
            params.extend([f"%{dao_id}%", f"%{dao_id}%"])
        
        if query:
            conditions.append("(title ILIKE %s OR body ILIKE %s)")
            params.extend([f"%{query}%", f"%{query}%"])
        
        sql = f"""
            SELECT 
                id,
                title,
                body,
                address,
                name as dao_name,
                state,
                "start" as start_ts,
                "end" as end_ts,
                author,
                choices,
                scores,
                last_updated,
                last_vote_change,
                'onchain' as source
            FROM internal.socket_onchain_proposals
            WHERE {' AND '.join(conditions)}
            ORDER BY "end" ASC
            LIMIT %s
        """
        params.append(limit)
        
        try:
            cursor.execute(sql, params)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[ActiveProposalsTool] On-chain query error: {e}")
            return []
    
    def _format_results(self, results: List[Dict[str, Any]], query: Optional[str]) -> str:
        """Format active proposals into readable output."""
        import json
        
        preview_data = []
        output_lines = [f"Found {len(results)} active proposals" + (f" matching '{query}':" if query else ":") + "\n"]
        
        current_time = int(time.time())
        
        for i, prop in enumerate(results, 1):
            title = prop.get("title", "Untitled")
            source = prop.get("source", "unknown")
            state = prop.get("state", "active")
            end_ts = prop.get("end_ts")
            start_ts = prop.get("start_ts")
            choices = prop.get("choices") or []
            scores = prop.get("scores") or []
            body = (prop.get("body") or "")[:200]
            
            # Get DAO identifier based on source
            if source == "snapshot":
                dao_id = prop.get("snapshot_id") or prop.get("snapshot_name") or "Unknown"
                prop_id = prop.get("id", "")
                link = f"https://snapshot.org/#/{dao_id}/proposal/{prop_id}" if dao_id and prop_id else ""
            else:
                dao_id = prop.get("dao_name") or prop.get("address") or "Unknown"
                link = ""  # On-chain links vary by protocol
            
            # Calculate time remaining
            time_remaining = ""
            if end_ts:
                try:
                    remaining_seconds = int(end_ts) - current_time
                    if remaining_seconds > 0:
                        days = remaining_seconds // 86400
                        hours = (remaining_seconds % 86400) // 3600
                        if days > 0:
                            time_remaining = f"{days}d {hours}h remaining"
                        else:
                            time_remaining = f"{hours}h remaining"
                    else:
                        time_remaining = "Ending soon"
                except (ValueError, TypeError):
                    pass
            
            # Format voting progress
            vote_summary = self._format_vote_summary(choices, scores)
            
            # Add to preview data
            preview_data.append({
                "id": prop.get("id"),
                "title": title,
                "source": source,
                "dao_id": dao_id,
                "state": state,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "time_remaining": time_remaining,
                "choices": choices,
                "scores": scores,
                "link": link,
                "body_preview": body[:150] if body else None,
            })
            
            # Text summary
            output_lines.append(f"**{i}. {title}**")
            output_lines.append(f"  - DAO: {dao_id} | Source: {source.capitalize()}")
            
            if time_remaining:
                output_lines.append(f"  - ⏱️ {time_remaining}")
            
            if vote_summary:
                output_lines.append(f"  - Votes: {vote_summary}")
            
            if link:
                output_lines.append(f"  - [View Proposal]({link})")
            
            output_lines.append("")
        
        # Combine preview block with text summary
        preview_block = self._format_preview_block("active-proposal", preview_data)
        return preview_block + "\n\n" + "\n".join(output_lines)
    
    def _format_vote_summary(self, choices: List[str], scores: List[float]) -> str:
        """Format voting choices and scores into a summary string."""
        if not choices or not scores:
            return ""
        
        try:
            # Pair choices with scores
            vote_pairs = []
            for choice, score in zip(choices, scores):
                formatted_score = self._format_number(score)
                vote_pairs.append(f"{choice}: {formatted_score}")
            
            return " | ".join(vote_pairs[:4])  # Limit to 4 choices for readability
        except Exception:
            return ""
    
    def _format_number(self, value: Any) -> str:
        """Format large numbers for readability."""
        if value is None:
            return "0"
        try:
            v = float(value)
            if v >= 1_000_000:
                return f"{v/1_000_000:.2f}M"
            elif v >= 1_000:
                return f"{v/1_000:.1f}K"
            else:
                return f"{v:.0f}"
        except (ValueError, TypeError):
            return str(value)
    
    def _format_preview_block(
        self,
        preview_type: str,
        data: List[Dict[str, Any]],
    ) -> str:
        """Format data as a preview block for the frontend."""
        import json
        
        # Clean data for preview
        cleaned_data = []
        for item in data[:5]:  # Limit to 5 previews
            cleaned = {k: v for k, v in item.items() if k not in ("embedding", "distance", "body")}
            cleaned_data.append(cleaned)
        
        json_str = json.dumps(cleaned_data, indent=2, default=str)
        return f"```{preview_type}-preview\n{json_str}\n```"

