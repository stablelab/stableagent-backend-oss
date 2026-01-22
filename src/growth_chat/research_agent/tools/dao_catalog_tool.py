"""DAO catalog tool for Research Agent.

Lists and searches supported DAOs with their metadata using semantic matching.
"""
import json
import re
from typing import Any, List, Optional, Type

from pydantic import BaseModel, Field

from src.utils.logger import logger
from src.utils.model_factory import create_chat_model, extract_text_content

from .base import ResearchBaseTool
from .database_client import ResearchDatabaseClient


class DAOListInput(BaseModel):
    """Input for listing DAOs."""
    query: str = Field("", description="Search query for finding DAOs (semantic match). Leave empty to list all.")


class DAOCatalogTool(ResearchBaseTool):
    """List supported DAOs and get their metadata.
    
    Queries the internal.daos table to find DAOs and their
    identifiers for other tools (snapshot_id, tally_id, etc.)
    Uses LLM semantic matching to find relevant DAOs.
    """
    
    name: str = "dao_catalog"
    description: str = """List supported DAOs and get their identifiers.

INPUT:
- query: Semantic search for DAO (e.g., 'Aave', 'Uniswap', 'Gnosis')

RETURNS: DAOs with Snapshot ID, Tally ID, CoinGecko ID, and forum URL.
Shows "N/A" when an identifier is not available.

USE FOR: Finding correct identifiers BEFORE using other tools.

CRITICAL RULES:
- snapshot_id: Use with snapshot_proposals. If "N/A", do NOT call snapshot_proposals.
- tally_id: Use with tally_proposals. If "N/A", do NOT call tally_proposals.
- coingecko_token_id: Use with token_prices. If "N/A", do NOT call token_prices.

TIPS:
- Call this at the START of any DAO research to get correct identifiers
- Handles abbreviations and variations (e.g., 'ARB' matches 'Arbitrum')
- If a DAO is not listed, its data may not be indexed - try web_search instead"""
    args_schema: Type[BaseModel] = DAOListInput
    _db_client: Optional[ResearchDatabaseClient] = None
    
    def _get_db_client(self) -> ResearchDatabaseClient:
        """Get or create the database client."""
        if self._db_client is None:
            self._db_client = ResearchDatabaseClient()
        return self._db_client
    
    def _get_all_daos(self) -> List[dict]:
        """Fetch all DAOs from the database."""
        client = self._get_db_client()
        sql = """
        SELECT id, name, snapshot_id, tally_id, discourse_url, coingecko_token_id
        FROM internal.daos
        ORDER BY name
        """
        return client.execute_query(sql)
    
    def _string_match_daos(self, query: str, all_daos: List[dict]) -> List[dict]:
        """Fast string matching for DAOs."""
        query_lower = query.lower()
        return [
            dao for dao in all_daos 
            if query_lower in (dao.get("name") or "").lower()
            or query_lower in (dao.get("snapshot_id") or "").lower()
            or query_lower in (dao.get("tally_id") or "").lower()
        ]
    
    def _parse_json_array(self, text: str) -> List[int]:
        """Extract JSON array of integers from LLM response."""
        # Remove markdown code blocks if present
        text = text.strip()
        if "```" in text:
            # Extract content between code blocks
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if match:
                text = match.group(1).strip()
        
        # Find JSON array
        match = re.search(r"\[[\d,\s]*\]", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return []
    
    def _semantic_match_daos(self, query: str, all_daos: List[dict]) -> List[dict]:
        """Use Gemini Flash to semantically match DAOs to the query."""
        if not all_daos:
            return []
        
        # First try fast string matching
        string_matches = self._string_match_daos(query, all_daos)
        if string_matches:
            logger.info(f"[DAOCatalog] Found {len(string_matches)} matches via string matching")
            return string_matches
        
        # No string matches - try LLM semantic matching
        logger.info(f"[DAOCatalog] No string matches, trying LLM semantic matching...")
        
        # Build compact DAO list for the LLM (just id and name to reduce tokens)
        dao_list = [
            f"{dao.get('id')}: {dao.get('name', '')}" 
            for dao in all_daos
        ]
        
        try:
            # Use gemini-2.5-flash for this utility task
            # Gemini 3 has known async/blocking issues with LangChain when not using tools
            # See: https://github.com/langchain-ai/langchain-google/issues/1231
            model = create_chat_model(
                model_name="gemini-2.5-flash",
                temperature=0,
            )
            
            # Simple prompt asking for JSON array
            prompt = f"""Match the query to DAOs from this list. Return ONLY a JSON array of matching DAO IDs.

Query: "{query}"

DAOs (id: name):
{chr(10).join(dao_list)}

Return matching IDs as JSON array, e.g. [5, 12]. Empty array [] if no match."""

            logger.info(f"[DAOCatalog] Invoking gemini-2.5-flash...")
            response = model.invoke(prompt)
            content = extract_text_content(response.content)
            logger.info(f"[DAOCatalog] LLM returned: {content}")
            
            # Parse the JSON array from response
            matched_ids = self._parse_json_array(content)
            
            # Filter and preserve order from LLM response
            id_to_dao = {dao.get("id"): dao for dao in all_daos}
            matched_daos = []
            for dao_id in matched_ids:
                if dao_id in id_to_dao:
                    matched_daos.append(id_to_dao[dao_id])
            
            return matched_daos
            
        except Exception as e:
            logger.error(f"[DAOCatalog] Semantic matching failed: {e}")
            return []
    
    def _run_tool(
        self,
        query: str = "",
        **kwargs: Any,
    ) -> str:
        """Execute DAO catalog lookup with semantic matching."""
        # Always fetch all DAOs
        all_daos = self._get_all_daos()
        
        if not all_daos:
            return "No DAOs found in the database."
        
        # Apply semantic matching if query provided (empty string = no filter)
        if query and query.strip():
            results = self._semantic_match_daos(query, all_daos)
            if not results:
                return f"No DAOs found matching '{query}'"
        else:
            results = all_daos
        
        # Format results with clear availability indicators
        output = [f"Found {len(results)} DAOs" + (f" matching '{query}':" if query else ":") + "\n"]
        
        for i, dao in enumerate(results, 1):
            dao_name = dao.get("name", "Unknown")
            dao_id = dao.get("id", "")
            snapshot_id = dao.get("snapshot_id", "")
            tally_id = dao.get("tally_id", "")
            discourse = dao.get("discourse_url", "")
            coingecko = dao.get("coingecko_token_id", "")
            
            output.append(f"**{i}. {dao_name}** (ID: {dao_id})")
            
            # Always show Snapshot and Tally status so agent knows which tools to use
            snapshot_str = f"`{snapshot_id}`" if snapshot_id else "N/A"
            tally_str = f"`{tally_id}`" if tally_id else "N/A (no on-chain governance indexed)"
            coingecko_str = f"`{coingecko}`" if coingecko else "N/A"
            
            output.append(f"  - Snapshot: {snapshot_str}")
            output.append(f"  - Tally: {tally_str}")
            output.append(f"  - CoinGecko: {coingecko_str}")
            
            if discourse:
                output.append(f"  - Forum: {discourse}")
            output.append("")
        
        # Add usage hint at the end
        output.append("**Usage:** Use snapshot_proposals for Snapshot IDs, tally_proposals for Tally IDs. Do NOT call a tool if the ID is N/A.")
        
        return "\n".join(output)
