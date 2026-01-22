from typing import Type, List, Dict, Any, Optional
from pydantic import BaseModel, Field

from langchain_core.tools import BaseTool

from src.services.database import DatabaseService
from src.utils.logger import logger
from src.utils.tool_events import emit_tool_event
import time
from src.knowledge.ens_knowledge import (
    ENS_KNOWLEDGE_GUIDE,
    normalize_ens_name,
    normalize_evm_address,
)


class ENSResolveInput(BaseModel):
    query: str = Field(..., description="ENS name like 'vitalik.eth' or EVM address like '0xabc…'")
    blockchain: Optional[str] = Field(
        None,
        description=(
            "Optional chain filter: accepts chain slug (e.g., 'ethereum'), human-readable name (e.g., 'Ethereum Mainnet'), "
            "or numeric chain ID (e.g., '1')."
        ),
    )
    direction: Optional[str] = Field(
        None,
        description="Optional direction: 'to_address' (name → address) or 'to_name' (address → name). Defaults to auto-detect.",
    )
    limit: int = Field(10, description="Max results to return (1–50). Defaults to 10.")


def _build_chain_filter_condition(chain_filter: Optional[str]) -> Optional[str]:
    """Builds a SQL condition that filters by chain slug, chain name, or numeric chain ID.

    Returns a string like "c.chain_id = 1" or a composite OR condition matching slug/name.
    """
    if chain_filter is None:
        return None
    s = str(chain_filter).strip()
    if not s:
        return None
    # Numeric chain ID support
    try:
        n = int(s)
        return f"c.chain_id = {n}"
    except Exception:
        pass
    # String: match against both canonical slug and chain name, and fallback to ENS label's blockchain slug
    esc = _sql_escape_literal(s)
    return (
        "(LOWER(c.blockchain) = LOWER('" + esc + "') "
        "OR LOWER(c.name) = LOWER('" + esc + "') "
        "OR LOWER(e.blockchain) = LOWER('" + esc + "'))"
    )


def _sql_escape_literal(text: str) -> str:
    # Minimal SQL literal sanitizer: double up single quotes
    return text.replace("'", "''")


class ENSResolverTool(BaseTool):
    name: str = "ens_resolver_tool"
    description: str = (
        "Resolve ENS names to EVM addresses and EVM addresses to ENS names using dune.ens_labels, "
        "joined with internal.chain_ids to annotate chain_id and network name. "
        "Accepts an ENS name (e.g., 'vitalik.eth') or an address ('0x…'); optional chain filter (slug, name, or ID). "
        "Returns compact rows: name, address, chain_slug, chain_id, chain_name. "
        "This tool is strictly for ENS ↔ address lookups."
    )
    args_schema: Type[BaseModel] = ENSResolveInput
    # Expose compact guidance for agent planning or debugging
    metadata: Dict[str, Any] = {"guide": ENS_KNOWLEDGE_GUIDE}

    def _resolve_to_name(self, address: str, blockchain: Optional[str], limit: int) -> List[Dict[str, Any]]:
        addr = normalize_evm_address(address)
        if not addr:
            logger.warning("ENSResolverTool: invalid address input")
            return []
        where = [f"LOWER(e.address) = LOWER('{_sql_escape_literal(addr)}')"]
        chain_cond = _build_chain_filter_condition(blockchain)
        if chain_cond:
            where.append(chain_cond)
        where_clause = " AND ".join(where)
        lim = max(1, min(int(limit or 10), 50))
        sql = (
            "SELECT e.name, e.address, e.blockchain AS chain_slug, c.chain_id, c.name AS chain_name\n"
            "FROM dune.ens_labels e\n"
            "LEFT JOIN internal.chain_ids c ON LOWER(c.blockchain) = LOWER(e.blockchain)\n"
            f"WHERE {where_clause}\n"
            "ORDER BY e.name NULLS LAST, c.chain_id NULLS LAST, e.blockchain ASC\n"
            f"LIMIT {lim}"
        )
        try:
            rows = DatabaseService.query_database(None, sql)
            return rows or []
        except Exception as e:
            logger.error("ENSResolverTool: DB error (to_name): %s", e, exc_info=True)
            return []

    def _resolve_to_address(self, ens_name: str, blockchain: Optional[str], limit: int) -> List[Dict[str, Any]]:
        name = normalize_ens_name(ens_name)
        if not name or "." not in name:
            logger.warning("ENSResolverTool: invalid ENS name input")
            return []
        where = [f"LOWER(e.name) = LOWER('{_sql_escape_literal(name)}')"]
        chain_cond = _build_chain_filter_condition(blockchain)
        if chain_cond:
            where.append(chain_cond)
        where_clause = " AND ".join(where)
        lim = max(1, min(int(limit or 10), 50))
        sql = (
            "SELECT e.name, e.address, e.blockchain AS chain_slug, c.chain_id, c.name AS chain_name\n"
            "FROM dune.ens_labels e\n"
            "LEFT JOIN internal.chain_ids c ON LOWER(c.blockchain) = LOWER(e.blockchain)\n"
            f"WHERE {where_clause}\n"
            "ORDER BY c.chain_id NULLS LAST, e.blockchain ASC, e.address ASC\n"
            f"LIMIT {lim}"
        )
        try:
            rows = DatabaseService.query_database(None, sql)
            return rows or []
        except Exception as e:
            logger.error("ENSResolverTool: DB error (to_address): %s", e, exc_info=True)
            return []

    def _run(self, query: str, blockchain: Optional[str] = None, direction: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            logger.info("ENSResolverTool: resolving query len=%d", len(query or ""))
            start_ts = time.time()
            try:
                emit_tool_event("ens_resolver.input", {"query": query, "blockchain": blockchain, "direction": direction, "limit": limit})
                emit_tool_event("tool.start", {"tool": self.name, "input": {"query_len": len(query or ""), "limit": limit}})
            except Exception:
                pass
            # Auto-detect direction if not provided
            if direction not in ("to_name", "to_address"):
                is_addr = bool(normalize_evm_address(query))
                direction = "to_name" if is_addr else "to_address"

            if direction == "to_name":
                rows = self._resolve_to_name(query, blockchain, limit)
            else:
                rows = self._resolve_to_address(query, blockchain, limit)
            try:
                emit_tool_event("ens_resolver.output", {"rows": rows[:3], "count": len(rows or [])})
                emit_tool_event("tool.end", {"tool": self.name, "status": "ok", "duration_ms": int((time.time() - start_ts) * 1000), "result": {"count": len(rows or [])}})
            except Exception:
                pass
            return rows
        except Exception as e:
            logger.error("ENSResolverTool: unexpected error: %s", e, exc_info=True)
            try:
                emit_tool_event("ens_resolver.error", {"message": str(e)})
                emit_tool_event("tool.end", {"tool": getattr(self, 'name', 'ens_resolver_tool'), "status": "error", "error": str(e)})
            except Exception:
                pass
            return []

    async def _arun(self, query: str, blockchain: Optional[str] = None, direction: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        return self._run(query=query, blockchain=blockchain, direction=direction, limit=limit)



