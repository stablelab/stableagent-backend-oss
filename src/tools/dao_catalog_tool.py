from typing import Type
from pydantic import BaseModel

from langchain_core.tools import BaseTool

from src.utils.logger import logger
from src.knowledge.dao_catalog import DAO_CATALOG
import json
from src.utils.tool_events import emit_tool_event


class _EmptyInput(BaseModel):
    pass


class DaoCatalogTool(BaseTool):
    name: str = "dao_catalog_tool"
    description: str = (
        "Return a small JSON document listing supported DAOs. "
        "If a DAO is not supported and the question is very specific for a DAO, answer with 'This DAO is not supported.'. But offer alternatives."
    )
    args_schema: Type[BaseModel] = _EmptyInput

    def __init__(self, **data):
        super().__init__(**data)
        try:
            logger.info("DaoCatalogTool: initialized (no LLM)")
        except Exception:
            pass

    def _run(self) -> str:
        payload = DAO_CATALOG.strip()
        # Try JSON first; if it fails, return the raw payload (may be YAML-like)
        try:
            parsed = json.loads(payload)
            rendered = json.dumps(parsed, ensure_ascii=False, indent=2)
            logger.info("DaoCatalogTool: returning JSON DAO catalog (len=%d)", len(rendered or ""))
            try:
                emit_tool_event("dao_catalog.output", {"format": "json", "length": len(rendered or "")})
            except Exception:
                pass
            return rendered
        except Exception:
            logger.info("DaoCatalogTool: returning raw DAO catalog text (non-JSON)")
            try:
                emit_tool_event("dao_catalog.output", {"format": "text", "length": len(payload or "")})
            except Exception:
                pass
            return payload

    async def _arun(self) -> str:
        return self._run()

