"""Chain resolver tool for Research Agent.

Resolves blockchain/chain details from chain ID, slug, or name.
Queries the internal.chain_ids table for chain metadata.
"""
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from src.utils.logger import logger

from .base import ResearchBaseTool
from .database_client import ResearchDatabaseClient


def _sql_escape_literal(text: str) -> str:
    """Escape single quotes for SQL literals."""
    return text.replace("'", "''")


class ChainResolveInput(BaseModel):
    """Input for chain resolution."""
    query: str = Field(
        "",
        description="Chain ID (1), slug (ethereum), or human name (Ethereum Mainnet). Leave empty to list popular chains."
    )
    chain_type: str = Field(
        "",
        description="Filter by chain type: L1, L2, rollup. Leave empty for all types."
    )
    limit: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum results to return (1-50)"
    )


class ChainResolverTool(ResearchBaseTool):
    """Resolve blockchain/chain details from ID, slug, or name.
    
    Queries the internal.chain_ids table for comprehensive chain metadata
    including chain type, rollup information, native tokens, and explorer links.
    """
    
    name: str = "chain_resolver"
    description: str = """Resolve blockchain/chain details from ID, slug, or name.

INPUT:
- query: Chain ID (1), slug (ethereum), or human name (Ethereum Mainnet). Leave EMPTY to list popular chains.
- chain_type: Filter by type (L1, L2, rollup). Leave empty for all.
- limit: Max results (1-50, default 10)

RETURNS: chain_id, blockchain (slug), name, chain_type, rollup_type, 
         settlement, native_token_symbol, explorer_link, wrapped_native_token_address

USE FOR: 
- Looking up chain metadata before cross-chain queries
- Finding chain IDs for other tools
- Resolving chain names to IDs
- Getting explorer links and native token info

IMPORTANT:
- Accepts fuzzy matching (e.g., 'arb' finds 'Arbitrum')
- Returns multiple chains if query is ambiguous
- Chain ID 1 = Ethereum Mainnet, 137 = Polygon, 42161 = Arbitrum One

TIPS:
- Use before any chain-specific analysis
- Chain slugs (blockchain field) are often used as identifiers in other tools
- For L2/rollup info, check rollup_type and settlement fields"""
    
    args_schema: Type[BaseModel] = ChainResolveInput
    _db_client: Optional[ResearchDatabaseClient] = None
    
    def _get_db_client(self) -> ResearchDatabaseClient:
        """Get or create the database client."""
        if self._db_client is None:
            self._db_client = ResearchDatabaseClient()
        return self._db_client
    
    def _build_select_columns(self) -> str:
        """Build the SELECT columns for chain queries."""
        return (
            "c.chain_id, c.blockchain, c.name, c.chain_type, c.rollup_type, "
            "c.settlement, c.native_token_symbol, c.explorer_link, c.wrapped_native_token_address"
        )
    
    def _query_popular_chains(self, chain_type: str, limit: int) -> List[Dict[str, Any]]:
        """Get popular/common chains when no query provided."""
        client = self._get_db_client()
        
        where_parts = []
        if chain_type:
            safe_type = _sql_escape_literal(chain_type.strip())
            where_parts.append(f"LOWER(c.chain_type) = LOWER('{safe_type}')")
        
        where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""
        
        # Order by chain_id to get major chains first (Ethereum=1, etc.)
        sql = f"""
        SELECT {self._build_select_columns()}
        FROM internal.chain_ids c
        {where_clause}
        ORDER BY c.chain_id ASC
        LIMIT {limit}
        """
        
        try:
            return client.execute_query(sql)
        except Exception as e:
            logger.error("ChainResolverTool: DB error (popular): %s", e, exc_info=True)
            return []
    
    def _query_exact(self, query: str, chain_type: str, limit: int) -> List[Dict[str, Any]]:
        """Try exact match on chain_id, blockchain slug, or name."""
        client = self._get_db_client()
        
        where_parts = []
        
        # Check if query is numeric (chain ID)
        try:
            chain_id = int(query.strip())
            where_parts.append(f"c.chain_id = {chain_id}")
        except ValueError:
            # Text query - exact match on blockchain or name
            esc = _sql_escape_literal(query.strip())
            where_parts.append(
                f"(LOWER(c.blockchain) = LOWER('{esc}') OR LOWER(c.name) = LOWER('{esc}'))"
            )
        
        if chain_type:
            safe_type = _sql_escape_literal(chain_type.strip())
            where_parts.append(f"LOWER(c.chain_type) = LOWER('{safe_type}')")
        
        where_clause = " AND ".join(where_parts)
        
        sql = f"""
        SELECT {self._build_select_columns()}
        FROM internal.chain_ids c
        WHERE {where_clause}
        ORDER BY c.chain_id ASC
        LIMIT {limit}
        """
        
        try:
            return client.execute_query(sql)
        except Exception as e:
            logger.error("ChainResolverTool: DB error (exact): %s", e, exc_info=True)
            return []
    
    def _query_fuzzy(self, query: str, chain_type: str, limit: int) -> List[Dict[str, Any]]:
        """Fuzzy match using ILIKE pattern matching."""
        client = self._get_db_client()
        
        esc = _sql_escape_literal(query.strip())
        
        where_parts = [
            f"(LOWER(c.blockchain) LIKE LOWER('%{esc}%') OR LOWER(c.name) LIKE LOWER('%{esc}%'))"
        ]
        
        if chain_type:
            safe_type = _sql_escape_literal(chain_type.strip())
            where_parts.append(f"LOWER(c.chain_type) = LOWER('{safe_type}')")
        
        where_clause = " AND ".join(where_parts)
        
        sql = f"""
        SELECT {self._build_select_columns()}
        FROM internal.chain_ids c
        WHERE {where_clause}
        ORDER BY c.chain_id ASC
        LIMIT {limit}
        """
        
        try:
            return client.execute_query(sql)
        except Exception as e:
            logger.error("ChainResolverTool: DB error (fuzzy): %s", e, exc_info=True)
            return []
    
    def _get_similar_chains(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get suggestions for similar chains when no match found."""
        client = self._get_db_client()
        
        # Extract first few characters for broader matching
        esc = _sql_escape_literal(query.strip()[:3] if len(query) > 3 else query.strip())
        
        sql = f"""
        SELECT {self._build_select_columns()}
        FROM internal.chain_ids c
        WHERE LOWER(c.blockchain) LIKE LOWER('%{esc}%') 
           OR LOWER(c.name) LIKE LOWER('%{esc}%')
        ORDER BY c.chain_id ASC
        LIMIT {limit}
        """
        
        try:
            results = client.execute_query(sql)
            if results:
                return results
            
            # If still no results, return some popular chains as suggestions
            return self._query_popular_chains("", limit)
        except Exception as e:
            logger.error("ChainResolverTool: DB error (similar): %s", e, exc_info=True)
            return []
    
    def _format_chain_type(self, chain: Dict[str, Any]) -> str:
        """Format chain type information into readable string."""
        chain_type = chain.get("chain_type", "")
        rollup_type = chain.get("rollup_type", "")
        settlement = chain.get("settlement", "")
        
        parts = []
        if chain_type:
            parts.append(chain_type)
        if rollup_type:
            parts.append(f"Rollup ({rollup_type})")
        if settlement:
            parts.append(f"on {settlement}")
        
        return " ".join(parts) if parts else "Unknown"
    
    def _format_chain_result(self, chains: List[Dict[str, Any]], query: str) -> str:
        """Format chain results into readable output."""
        if not chains:
            return "No chains found."
        
        query_desc = f" matching '{query}'" if query else ""
        output_lines = [f"Found {len(chains)} chain(s){query_desc}:\n"]
        
        for i, chain in enumerate(chains, 1):
            name = chain.get("name", "Unknown")
            chain_id = chain.get("chain_id", "N/A")
            blockchain = chain.get("blockchain", "")
            native_token = chain.get("native_token_symbol", "")
            explorer = chain.get("explorer_link", "")
            wrapped = chain.get("wrapped_native_token_address", "")
            
            output_lines.append(f"**{i}. {name}** (Chain ID: {chain_id})")
            output_lines.append(f"  - Slug: `{blockchain}`")
            output_lines.append(f"  - Type: {self._format_chain_type(chain)}")
            
            if native_token:
                output_lines.append(f"  - Native Token: {native_token}")
            
            if explorer:
                output_lines.append(f"  - Explorer: {explorer}")
            
            if wrapped:
                output_lines.append(f"  - Wrapped Native: `{wrapped}`")
            
            output_lines.append("")
        
        return "\n".join(output_lines)
    
    def _run_tool(
        self,
        query: str = "",
        chain_type: str = "",
        limit: int = 10,
        **kwargs: Any,
    ) -> str:
        """Execute chain resolution."""
        # Validate and clamp limit
        limit = max(1, min(int(limit), 50))
        
        # Determine query mode
        query = query.strip() if query else ""
        chain_type = chain_type.strip() if chain_type else ""
        
        logger.info(
            f"[ChainResolverTool] Resolving query='{query}', chain_type='{chain_type}', limit={limit}"
        )
        
        # Mode 1: No query - list popular chains
        if not query:
            results = self._query_popular_chains(chain_type, limit)
            if results:
                preview_block = self._format_preview_block("chain", results)
                text_output = self._format_chain_result(results, "")
                
                if not chain_type:
                    text_output += "\n**TIP:** Provide a query to search for specific chains, or use chain_type to filter."
                
                return preview_block + "\n\n" + text_output
            
            return "No chains found in the database."
        
        # Mode 2: Try exact match first
        results = self._query_exact(query, chain_type, limit)
        if results:
            preview_block = self._format_preview_block("chain", results)
            return preview_block + "\n\n" + self._format_chain_result(results, query)
        
        # Mode 3: Try fuzzy match
        results = self._query_fuzzy(query, chain_type, limit)
        if results:
            preview_block = self._format_preview_block("chain", results)
            return preview_block + "\n\n" + self._format_chain_result(results, query)
        
        # Mode 4: No results - provide suggestions
        suggestions = self._get_similar_chains(query)
        if suggestions:
            suggestion_lines = [
                f"  - {s.get('name', 'Unknown')} (ID: {s.get('chain_id', 'N/A')}, slug: `{s.get('blockchain', '')}`)"
                for s in suggestions[:5]
            ]
            return (
                f"No chain found matching '{query}'.\n\n"
                "**Did you mean:**\n" + "\n".join(suggestion_lines) + "\n\n"
                "**TIP:** Try using the chain ID (e.g., 1 for Ethereum) or the blockchain slug."
            )
        
        return f"No chain found matching '{query}'. Try a different query or check the chain ID."

