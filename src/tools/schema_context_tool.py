from typing import Type
from pydantic import BaseModel

from langchain_core.tools import BaseTool

from src.knowledge.database_context import DATABASE_CONTEXT
from src.utils.logger import logger
from src.utils.tool_events import emit_tool_event


class _EmptyInput(BaseModel):
    pass


class SchemaContextTool(BaseTool):
    name: str = "schema_context_tool"
    description: str = (
        "Return the database schema context (tables, columns, relationships) used for SQL generation. "
        "Use this tool when you need to inspect the schema before generating SQL."
    )
    args_schema: Type[BaseModel] = _EmptyInput

    _cached: str | None = None

    def __init__(self, **data):
        super().__init__(**data)
        try:
            logger.info("SchemaContextTool: initialized (no LLM)")
        except Exception:
            pass

    def _run(self) -> str:
        if self._cached is None:
            logger.info("SchemaContextTool: returning full schema context")
            self._cached = DATABASE_CONTEXT
            try:
                emit_tool_event("schema_context.output", {"provided": True, "length": len(self._cached or "")})
            except Exception:
                pass
            return self._cached
        logger.info("SchemaContextTool: schema already provided; suppressing duplicate output")
        try:
            emit_tool_event("schema_context.output", {"provided": False, "length": 0})
        except Exception:
            pass
        return ""

    async def _arun(self) -> str:
        return self._run()