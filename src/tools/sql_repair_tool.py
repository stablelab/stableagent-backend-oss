from typing import Type, Optional
from pydantic import BaseModel, Field, ConfigDict

from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.llm.factory import create_tool_chat_model, identify_model_name, identify_provider
from src.utils.sql_validator import extract_sql_query
from src.utils.logger import logger
from src.utils.tool_events import emit_tool_event
import time
from src.knowledge.database_context import DATABASE_CONTEXT
from src.knowledge.dao_catalog import DAO_CATALOG

class SQLRepairInput(BaseModel):
    # Avoid shadowing BaseModel attributes by not using field name 'schema'.
    # Accept external payloads that still send 'schema' via alias.
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())
    user_query: str = Field(..., description="Original user question")
    previous_sql: str = Field(..., description="The SQL that failed or produced empty results")
    reason: Optional[str] = Field(None, description="Optional reason or error description if available")
    schema_text: Optional[str] = Field(
        None,
        description="Optional hints",
        alias="schema",
    )
    additional_context: str = Field("", description="Any extra hints or constraints for the repair step")


class SQLRepairTool(BaseTool):
    name: str = "sql_repair_tool"
    description: str = (
        "Repair or refactor a PostgreSQL SELECT query that failed or returned empty results. "
        "Provide the original user query, the previous SQL, and optionally the error reason and schema text. "
        "Returns a revised SQL query (string)."
    )
    args_schema: Type[BaseModel] = SQLRepairInput

    def __init__(self, **data):
        super().__init__(**data)
        system_text = "Repair a PostgreSQL SELECT query to be syntactically valid and aligned with the given schema and constraints." + DATABASE_CONTEXT + DAO_CATALOG
        safe_system_text = system_text.replace("{", "{{").replace("}", "}}")
        self._prompt = ChatPromptTemplate.from_messages([
            ("system", safe_system_text),
            ("human", """
Repair the following SQL for a PostgreSQL database. Ensure it is syntactically valid and aligned with the schema.

User query:
{user_query}

Previous SQL:
```sql
{previous_sql}
```
Context:
{context_blob}
"""),
        ])
        self._llm = create_tool_chat_model(self.name)
        self._chain = self._prompt | self._llm | StrOutputParser()
        try:
            from src.utils.logger import logger  # local import to avoid cycles
            logger.info(
                "SQLRepairTool: initialized with provider=%s model=%s",
                identify_provider(self._llm),
                identify_model_name(self._llm),
            )
        except Exception:
            pass

    def _run(
        self,
        user_query: str,
        previous_sql: str,
        reason: Optional[str] = None,
        schema_text: Optional[str] = None,
        additional_context: str = "",
    ) -> str:
        try:
            start_ts = time.time()
            context_parts = []
            if schema_text:
                context_parts.append("Schema:\n" + schema_text)
            if reason:
                context_parts.append("Reason:\n" + reason)
            if additional_context:
                context_parts.append("Hints:\n" + additional_context)
            context_blob = "\n\n".join(context_parts).strip()

            logger.info("SQLRepairTool: attempting repair; prev_sql_len=%d", len(previous_sql or ""))
            try:
                emit_tool_event("sql_repair.input", {"user_query_len": len(user_query or ""), "prev_sql_len": len(previous_sql or ""), "has_reason": bool(reason), "has_schema": bool(schema_text)})
                emit_tool_event("tool.start", {"tool": self.name, "input": {"prev_sql_len": len(previous_sql or "")}})
            except Exception:
                pass
            response = self._chain.invoke({
                "user_query": user_query,
                "previous_sql": previous_sql,
                "context_blob": context_blob,
            })
            repaired = extract_sql_query(response)
            if not repaired:
                logger.warning("SQLRepairTool: no SQL extracted from repair attempt")
                try:
                    emit_tool_event("sql_repair.output", {"repaired": False})
                    emit_tool_event("tool.end", {"tool": self.name, "status": "ok", "duration_ms": int((time.time() - start_ts) * 1000), "result": {"repaired": False}})
                except Exception:
                    pass
                return ""
            logger.info("SQLRepairTool: produced repaired SQL (len=%d)", len(repaired))
            try:
                emit_tool_event("sql_repair.output", {"repaired": True, "sql_len": len(repaired or "")})
                emit_tool_event("tool.end", {"tool": self.name, "status": "ok", "duration_ms": int((time.time() - start_ts) * 1000), "result": {"repaired": True}})
            except Exception:
                pass
            return repaired
        except Exception as e:
            logger.error("SQLRepairTool: unexpected error: %s", e, exc_info=True)
            try:
                emit_tool_event("sql_repair.error", {"message": str(e)})
                emit_tool_event("tool.end", {"tool": getattr(self, 'name', 'sql_repair_tool'), "status": "error", "error": str(e)})
            except Exception:
                pass
            return ""

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)