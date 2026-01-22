from typing import Type, List, Dict, Any, Optional
import time
from pydantic import BaseModel, Field

from langchain_core.tools import BaseTool

from src.services.database import DatabaseService
from src.utils.logger import logger
from src.utils.tool_events import emit_tool_event


class ChainResolveInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "Chain identifier to resolve. Accepts numeric chain ID (e.g., '1'), chain slug (e.g., 'ethereum'), "
            "or human-readable name (e.g., 'Ethereum Mainnet')."
        ),
    )
    limit: int = Field(10, description="Max results to return (1–50). Defaults to 10.")


def _sql_escape_literal(text: str) -> str:
    return text.replace("'", "''")


class ChainResolverTool(BaseTool):
    name: str = "chain_resolver_tool"
    description: str = (
        "Resolve blockchain details from chain ID, slug, or name using internal.chain_ids. "
        "Returns compact rows: chain_id, blockchain (slug), name (human-readable), chain_type, rollup_type, "
        "settlement, native_token_symbol, explorer_link, wrapped_native_token_address."
    )
    args_schema: Type[BaseModel] = ChainResolveInput

    def _query_exact(self, q: str, limit: int) -> List[Dict[str, Any]]:
        where: str
        # Numeric chain ID
        try:
            n = int(q.strip())
            where = f"c.chain_id = {n}"
        except Exception:
            esc = _sql_escape_literal(q.strip())
            where = (
                "(LOWER(c.blockchain) = LOWER('" + esc + "') "
                "OR LOWER(c.name) = LOWER('" + esc + "'))"
            )
        lim = max(1, min(int(limit or 10), 50))
        sql = (
            "SELECT c.chain_id, c.blockchain, c.name, c.chain_type, c.rollup_type, c.settlement, "
            "c.native_token_symbol, c.explorer_link, c.wrapped_native_token_address\n"
            "FROM internal.chain_ids c\n"
            f"WHERE {where}\n"
            "ORDER BY c.chain_id ASC\n"
            f"LIMIT {lim}"
        )
        try:
            return DatabaseService.query_database(None, sql) or []
        except Exception as e:
            logger.error("ChainResolverTool: DB error (exact): %s", e, exc_info=True)
            return []

    def _query_fuzzy(self, q: str, limit: int) -> List[Dict[str, Any]]:
        esc = _sql_escape_literal(q.strip())
        lim = max(1, min(int(limit or 10), 50))
        sql = (
            "SELECT c.chain_id, c.blockchain, c.name, c.chain_type, c.rollup_type, c.settlement, "
            "c.native_token_symbol, c.explorer_link, c.wrapped_native_token_address\n"
            "FROM internal.chain_ids c\n"
            f"WHERE LOWER(c.blockchain) LIKE LOWER('%{esc}%') OR LOWER(c.name) LIKE LOWER('%{esc}%')\n"
            "ORDER BY c.chain_id ASC\n"
            f"LIMIT {lim}"
        )
        try:
            return DatabaseService.query_database(None, sql) or []
        except Exception as e:
            logger.error("ChainResolverTool: DB error (fuzzy): %s", e, exc_info=True)
            return []

    def _run(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            logger.info("ChainResolverTool: resolving query len=%d", len(query or ""))
            start_ts = time.time()
            try:
                emit_tool_event("chain_resolver.input", {"query": query, "limit": limit})
                emit_tool_event("tool.start", {"tool": self.name, "input": {"query_len": len(query or ""), "limit": limit}})
            except Exception:
                pass
            rows = self._query_exact(query, limit)
            if rows:
                try:
                    emit_tool_event("chain_resolver.output", {"rows": rows[:3], "count": len(rows or [])})
                    emit_tool_event("tool.end", {"tool": self.name, "status": "ok", "duration_ms": int((time.time() - start_ts) * 1000), "result": {"count": len(rows or [])}})
                except Exception:
                    pass
                return rows
            rows = self._query_fuzzy(query, limit)
            try:
                emit_tool_event("chain_resolver.output", {"rows": rows[:3], "count": len(rows or [])})
                emit_tool_event("tool.end", {"tool": self.name, "status": "ok", "duration_ms": int((time.time() - start_ts) * 1000), "result": {"count": len(rows or [])}})
            except Exception:
                pass
            return rows
        except Exception as e:
            logger.error("ChainResolverTool: unexpected error: %s", e, exc_info=True)
            try:
                emit_tool_event("chain_resolver.error", {"message": str(e)})
                emit_tool_event("tool.end", {"tool": getattr(self, 'name', 'chain_resolver_tool'), "status": "error", "error": str(e)})
            except Exception:
                pass
            return []

    async def _arun(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        return self._run(query=query, limit=limit)


