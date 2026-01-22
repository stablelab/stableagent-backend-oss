from typing import Type, List, Dict, Any
from pydantic import BaseModel, Field

from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.llm.factory import create_tool_chat_model, identify_model_name, identify_provider
from src.prompts.system_prompts import SQL_HELPER_SYSTEM
from src.services.database import DatabaseService
from src.services.gemini_embeddings import EmbeddingsService
from src.utils.sql_validator import extract_sql_query
from src.utils.logger import logger
from src.utils.tool_events import emit_tool_event
import os
import json
from src.tools.sql_repair_tool import SQLRepairTool
from src.knowledge.database_context import DATABASE_CONTEXT


class SQLQueryInput(BaseModel):
    user_query: str = Field(..., description="The user's question to translate into SQL and execute")
    additional_context: str = Field("", description=(
        "Optional context to guide SQL generation (e.g., expanded keywords, and if available)."
    ))


class SQLQueryTool(BaseTool):
    name: str = "sql_query_tool"
    description: str = (
        "Generate a PostgreSQL SELECT query from a user's question using the internal SQL agent, "
        "then execute it against the DAO database. Automatically replaces {prompt_vector} using an embedding of the user query. "
        #"If you already fetched the schema via schema_context_tool, pass that schema text in additional_context."
    )
    args_schema: Type[BaseModel] = SQLQueryInput

    def __init__(self, **data):
        super().__init__(**data)
        # Build a lightweight chain using the shared LLM factory and SQL helper system prompt
        # Escape braces in system text to avoid template parsing issues
        system_text = "\n".join(SQL_HELPER_SYSTEM)
        safe_system_text = system_text.replace("{", "{{").replace("}", "}}")
        self._sql_prompt = ChatPromptTemplate.from_messages([
            ("system", safe_system_text),
            (
                "human",
                (
                    "User question: {q}\n\n"
                    "Additional context (optional): {ctx}\n\n"
                ),
            ),
        ])
        self._llm = create_tool_chat_model(self.name)
        self._sql_chain = self._sql_prompt | self._llm | StrOutputParser()
        model_name = os.environ.get("EMBEDDING_MODEL_NAME", "text-embedding-005")
        self._embedding = EmbeddingsService(model_name=model_name)
        try:
            from src.utils.logger import logger  # local import to avoid cycles
            logger.info(
                "SQLQueryTool: initialized with provider=%s model=%s (embedding_model=%s)",
                identify_provider(self._llm),
                identify_model_name(self._llm),
                model_name,
            )
        except Exception:
            pass
        self._always_use_embeddings = os.environ.get("SQL_ALWAYS_USE_EMBEDDINGS", "1").strip() not in ("0", "false", "False")

    def _inject_recency_fallback(self, sql: str) -> str:
        lowered = sql.lower()
        if "<-> '{prompt_vector}'::vector" in lowered or "{prompt_vector}" in sql:
            try:
                sql_no_embed = sql.replace("e.embedding <-> '{prompt_vector}'::vector", "1")
                if "order by" not in sql_no_embed.lower():
                    sql_no_embed = sql_no_embed.rstrip(";\n ") + "\nORDER BY COALESCE(created_at, created, start_timestamp, start_date) DESC"
                logger.info("SQLQueryTool: applied recency fallback ordering")
                return sql_no_embed
            except Exception as e:
                logger.error("SQLQueryTool: error during recency fallback injection: %s", e, exc_info=True)
                return sql
        return sql

    def _enforce_recency_and_limit(self, sql: str, user_query: str) -> str:
        try:
            out = sql.rstrip(";\n ")
            if "order by" not in out.lower():
                out += "\nORDER BY COALESCE(created_at, created, start_timestamp, start_date) DESC"
            else:
                # Append secondary recency ordering if not present
                if "created_at" not in out.lower() and " start_" not in out.lower() and " created" not in out.lower():
                    out += ", COALESCE(created_at, created, start_timestamp, start_date) DESC"
            # Let the LLM decide the LIMIT based on query context - don't override
            return out
        except Exception:
            return sql

    def _run_once(self, user_query: str, additional_context: str) -> Dict[str, Any]:
        try:
            logger.info("SQLQueryTool: generating SQL for user_query length=%d", len(user_query or ""))
            logger.info("SQLQueryTool: user_query: %s", user_query)
            try:
                emit_tool_event("sql_query.input", {"user_query": user_query, "additional_context_len": len(additional_context or "")})
            except Exception:
                pass
            # 1) Generate SQL via LLM
            raw_text = self._sql_chain.invoke({"q": user_query, "ctx": additional_context})
            sql = extract_sql_query(raw_text)
            if not isinstance(sql, str) or not sql.strip():
                logger.warning("SQLQueryTool: empty SQL generated")
                try:
                    emit_tool_event("sql_query.output", {"row_count": 0, "sql": "", "repaired": False})
                except Exception:
                    pass
                return {"rows": [], "sql": ""}
            try:
                emit_tool_event("sql_query.generated", {"sql": sql})
            except Exception:
                pass

            # 1b) Enforce embedding usage if missing
            if self._always_use_embeddings and not self._contains_embedding_usage(sql):
                logger.info("SQLQueryTool: embedding usage missing; regenerating with strict instruction")
                strict_ctx = (additional_context + "\nMANDATORY: Use embedding-based similarity ordering using e.embedding <-> '{prompt_vector}'::vector; include the placeholder exactly. Do NOT omit.").strip()
                raw_text2 = self._sql_chain.invoke({"q": user_query, "ctx": strict_ctx})
                sql2 = extract_sql_query(raw_text2)
                if isinstance(sql2, str) and sql2.strip() and self._contains_embedding_usage(sql2):
                    sql = sql2
                else:
                    logger.warning("SQLQueryTool: second attempt still missing embedding usage; proceeding anyway")

            # 2) Compute embedding for {prompt_vector}
            vector = None
            try:
                vector = self._embedding.embed_query(user_query)
            except Exception as e:
                logger.error("SQLQueryTool: embedding error: %s", e, exc_info=True)

            # 3) Guidance-only checks (do not mutate SQL to avoid syntax issues in complex queries)
            try:
                if vector is None:
                    logger.info("SQLQueryTool: no embedding available; consider adding recency ORDER BY and LIMIT when asking for 'latest'.")
                lowered = (sql or "").lower()
                # LLM will handle ORDER BY and LIMIT based on prompt instructions
                pass
            except Exception:
                pass

            logger.info("SQLQueryTool: Run Query: %s", sql)
            # 4) Run query
            try:
                executed_sql = sql
                try:
                    logger.info("SQLQueryTool: final SQL to execute (embedding=%s):\n%s", "yes" if vector is not None else "no", executed_sql)
                    # Brief rationale for operators
                    if vector is None:
                        logger.info("SQLQueryTool: rationale: no embedding available → applied recency fallback and enforcement")
                    else:
                        logger.info("SQLQueryTool: rationale: embedding available → similarity ordering present; ensured recency/limit if implied by the query")
                except Exception:
                    pass
                rows = DatabaseService.query_database(vector, executed_sql)
                original_count = len(rows or [])
                shrunk = self._shrink_rows(rows or [])
                logger.info(
                    "SQLQueryTool: query returned %d row(s); delivering %d row(s) to agent after shrinking",
                    original_count,
                    len(shrunk or []),
                )
                try:
                    emit_tool_event("sql_query.output", {"row_count": len(shrunk or []), "sql": executed_sql, "repaired": False})
                except Exception:
                    pass
                return {"rows": shrunk, "sql": executed_sql}
            except Exception as e:
                logger.error("SQLQueryTool: database execution error: %s", e, exc_info=True)
                
                # Check if it's a timeout or connection error - these need immediate user feedback
                error_str = str(e).lower()
                if "timeout" in error_str or "timed out" in error_str:
                    logger.warning("SQLQueryTool: query timed out, suggesting simpler approach")
                    try:
                        emit_tool_event("sql_query.timeout", {"message": "Query timed out", "sql": sql})
                    except Exception:
                        pass
                    return {
                        "rows": [], 
                        "sql": sql, 
                        "error": "Query timed out. The request was too complex. Please try a simpler or more specific question.",
                        "repaired": False
                    }
                
                if "authentication failed" in error_str or "connection" in error_str or "database" in error_str:
                    logger.error("SQLQueryTool: database connection issue")
                    try:
                        emit_tool_event("sql_query.connection_error", {"message": "Database connection failed", "sql": sql})
                    except Exception:
                        pass
                    return {
                        "rows": [], 
                        "sql": sql, 
                        "error": "Database connection issue. Please try again or contact support if the problem persists.",
                        "repaired": False
                    }
                
                # Attempt automatic repair using the error message (sanitized)
                sanitized_reason = DatabaseService._redact_vector_literals(str(e))
                repaired = self._repair_and_execute(user_query, sql, sanitized_reason, additional_context)
                if isinstance(repaired, dict) and repaired.get("rows"):
                    try:
                        emit_tool_event("sql_query.output", {"row_count": len(repaired.get("rows") or []), "sql": repaired.get("sql"), "repaired": True})
                    except Exception:
                        pass
                    return repaired
                
                # If repair failed, provide helpful error message
                try:
                    emit_tool_event("sql_query.error", {"message": sanitized_reason, "sql": sql})
                except Exception:
                    pass
                return {
                    "rows": [], 
                    "sql": sql, 
                    "error": f"Unable to execute query: {sanitized_reason}. Please try rephrasing your question.",
                    "repaired": False
                }
        except Exception as e:
            logger.error("SQLQueryTool: unexpected error: %s", e, exc_info=True)
            try:
                emit_tool_event("sql_query.error", {"message": str(e)})
            except Exception:
                pass
            return {"rows": [], "sql": "", "error": str(e)}

    def _run(self, user_query: str, additional_context: str = "") -> Dict[str, Any]:
        # NEW: Check if query mentions a DAO that doesn't exist BEFORE running any SQL
        # Extract potential DAO names from the query
        import re
        potential_daos = re.findall(r'\b(scroll|polygon|avalanche|celestia|eigenlayer|base|blast|linea|zksync|starknet|mantle)\b', user_query.lower())
        
        # If a known missing DAO is mentioned, check immediately
        if potential_daos:
            for dao_name in potential_daos[:1]:  # Check first one only for speed
                try:
                    # Try exact and common variations first
                    check_sql = f"""
                    SELECT DISTINCT dao_id, COUNT(*) as proposal_count
                    FROM internal.unified_proposals
                    WHERE dao_id IN ('{dao_name}', '{dao_name}.eth', '{dao_name}dao.eth', '{dao_name}-dao')
                       OR dao_id ILIKE '{dao_name}'
                    GROUP BY dao_id
                    LIMIT 5
                    """
                    dao_check_results = DatabaseService.query_database(None, check_sql)
                    
                    # Filter out false matches (e.g., "bankscroll" when looking for "scroll")
                    if dao_check_results:
                        # Check if any match is an exact or close match
                        exact_matches = [d for d in dao_check_results if 
                                       d.get('dao_id', '').lower() in [dao_name, f'{dao_name}.eth', f'{dao_name}dao.eth', f'{dao_name}-dao']]
                        if not exact_matches:
                            logger.info("SQLQueryTool: No exact match for DAO '%s', only partial matches: %s", 
                                       dao_name, [d.get('dao_id') for d in dao_check_results])
                            dao_check_results = []  # Treat as not found
                    
                    if not dao_check_results:
                        logger.info("SQLQueryTool: DAO '%s' not found in database - skipping query and recommending web search", dao_name)
                        
                        # Get a sample of available DAOs to suggest
                        sample_daos_sql = """
                        SELECT DISTINCT dao_id, COUNT(*) as proposal_count
                        FROM internal.unified_proposals
                        GROUP BY dao_id
                        ORDER BY COUNT(*) DESC
                        LIMIT 10
                        """
                        sample_daos = DatabaseService.query_database(None, sample_daos_sql)
                        dao_list = ", ".join([d.get("dao_id", "") for d in (sample_daos or [])[:10]])
                        
                        return {
                            "rows": [],
                            "sql": f"-- DAO '{dao_name}' not found",
                            "message": f"**{dao_name.title()} governance data is not available in our database.**\n\n"
                                      f"Our database currently tracks the following DAOs:\n{dao_list}\n\n"
                                      f"Recommendation: Try web search for more information about {dao_name.title()}.",
                            "dao_not_found": True,
                            "missing_dao": dao_name,
                            "available_daos": [d.get("dao_id") for d in (sample_daos or [])],
                            "recommend_web_search": True,
                            "web_search_query": f"{dao_name} governance {user_query.replace(dao_name, '').strip()}"
                        }
                    else:
                        logger.info("SQLQueryTool: DAO '%s' exists: %s", dao_name, dao_check_results)
                        # DAO exists, continue with normal query
                        break
                except Exception as e:
                    logger.warning("SQLQueryTool: Failed to check DAO existence for '%s': %s", dao_name, e)
        
        out = self._run_once(user_query, additional_context)
        
        # If we got rows, return immediately
        if isinstance(out, dict) and out.get("rows"):
            return out
        
        # If there was a critical error (timeout, connection), return immediately
        if isinstance(out, dict) and out.get("error"):
            error_str = str(out.get("error", "")).lower()
            if "timeout" in error_str or "connection" in error_str:
                return out
        
        # If 0 rows and this looks like a proposal ID query, ask if they want similar search
        proposal_id_match = re.search(r'proposal\s+(\d+)', user_query, re.IGNORECASE)
        dao_match = re.search(r'(compound|aave|uniswap|maker|arbitrum|optimism|lido|curve|balancer)', user_query, re.IGNORECASE)
        
        if proposal_id_match and dao_match and not out.get("rows"):
            prop_id = proposal_id_match.group(1)
            dao_name = dao_match.group(1).title()
            
            # Return a clarification request instead of auto-searching
            logger.info("SQLQueryTool: No exact match for proposal '%s'. Offering to search for similar IDs", prop_id)
            return {
                "rows": [],
                "sql": out.get("sql", ""),
                "message": f"I couldn't find a {dao_name} proposal with exact ID '{prop_id}'.\n\nWould you like me to search for proposals with IDs containing '{prop_id}'? (This may find Tally's long-form IDs like '244093891835540{prop_id}4')",
                "clarification_needed": True,
                "clarification_type": "similar_proposal_search",
                "clarification_context": {"prop_id": prop_id, "dao": dao_name}
            }
        
        # First retry: broaden the search with more flexible criteria
        broadened_context = (additional_context + "\nBroaden results: minimize restrictive filters and prefer recency ordering. Limit result size to at most 100 rows and avoid selecting large blob fields. Consider alternative proxies for the user's concept (e.g., activity/effort via counts/lengths/recency). Where relevant, join to discourse.posts or snapshot.votelist. Use ILIKE for text matching instead of exact matches.").strip()
        logger.info("SQLQueryTool: retrying with broadened context; original rows=0")
        try:
            emit_tool_event("sql_query.retry", {"reason": "zero_rows", "broadened": True, "attempt": 1})
        except Exception:
            pass
        
        retry_out = self._run_once(user_query, broadened_context)
        if isinstance(retry_out, dict) and (retry_out.get("rows") or retry_out.get("error")):
            return retry_out
        
        # Second retry: try without embedding constraints if no results
        if not self._contains_embedding_usage(broadened_context):
            fallback_context = (broadened_context + "\nFallback strategy: If no results found, try querying without embedding similarity constraints. Focus on recent proposals (ORDER BY created_at DESC) and use text search with ILIKE patterns. Choose appropriate LIMIT based on query scope.").strip()
            logger.info("SQLQueryTool: second retry with fallback strategy")
            try:
                emit_tool_event("sql_query.retry", {"reason": "zero_rows", "broadened": True, "attempt": 2})
            except Exception:
                pass
            
            final_out = self._run_once(user_query, fallback_context)
            if isinstance(final_out, dict):
                return final_out
        
        # If all retries failed, check if this is a proposal ID mismatch and suggest alternatives
        import re
        proposal_id_match = re.search(r'proposal\s+(\d+)', user_query, re.IGNORECASE)
        dao_match = re.search(r'(compound|aave|uniswap|maker|arbitrum|optimism|lido|curve|balancer|arbitrum|gnosis)', user_query, re.IGNORECASE)
        
        if proposal_id_match and dao_match:
            # Multi-layer fallback strategy for proposal ID queries
            prop_id = proposal_id_match.group(1)
            dao_name = dao_match.group(1)
            
            # Strategy 1: Search by link pattern (for Tally/Snapshot URLs)
            link_search_sql = f"""
            SELECT proposal_id, title, body, state, created_at, source, link, for_votes, against_votes
            FROM internal.unified_proposals
            WHERE dao_id ILIKE '%{dao_name}%'
              AND (
                link LIKE '%/proposal/{prop_id}%' OR
                link LIKE '%/proposal/{prop_id}?%' OR
                link LIKE '%/{prop_id}%'
              )
            ORDER BY created_at DESC
            LIMIT 5
            """
            
            try:
                logger.info("SQLQueryTool: Searching for proposal '%s' in %s by link pattern", prop_id, dao_name)
                link_results = DatabaseService.query_database(None, link_search_sql)
                if link_results:
                    logger.info("SQLQueryTool: Found %d proposals by link pattern", len(link_results))
                    return {
                        "rows": link_results,
                        "sql": link_search_sql,
                        "message": f"Found {len(link_results)} proposal(s) matching '{dao_name} proposal {prop_id}' via URL pattern matching.",
                        "matched_by": "link_pattern"
                    }
            except Exception as e:
                logger.warning("Failed link pattern search: %s", e)
            
            # Strategy 2: Fuzzy search by proposal ID substring
            fuzzy_search_sql = f"""
            SELECT proposal_id, title, body, state, created_at, source, link, for_votes, against_votes
            FROM internal.unified_proposals
            WHERE dao_id ILIKE '%{dao_name}%'
              AND proposal_id LIKE '%{prop_id}%'
            ORDER BY created_at DESC
            LIMIT 5
            """
            
            try:
                logger.info("SQLQueryTool: Searching for similar proposal IDs to '%s' in %s", prop_id, dao_name)
                suggestions = DatabaseService.query_database(None, fuzzy_search_sql)
                if suggestions:
                    logger.info("SQLQueryTool: Found %d similar proposals", len(suggestions))
                    return {
                        "rows": suggestions,
                        "sql": fuzzy_search_sql,
                        "message": f"No exact match for proposal '{prop_id}', but found {len(suggestions)} proposals with '{prop_id}' in their ID. These may be the proposals you're looking for (Tally uses long-form IDs).",
                        "suggestions": True,
                        "matched_by": "fuzzy_id"
                    }
            except Exception as e:
                logger.warning("Failed to fetch proposal suggestions: %s", e)
            
            # Strategy 3: If still no results, return a helpful message suggesting web search
            logger.info("SQLQueryTool: No proposals found for '%s' in %s. Suggesting web search.", prop_id, dao_name)
            return {
                "rows": [],
                "sql": fuzzy_search_sql,
                "message": f"I couldn't find {dao_name} proposal {prop_id} in the database. This proposal may:\n"
                          f"1. Use a different ID format (e.g., long-form Tally IDs)\n"
                          f"2. Be very recent and not yet indexed\n"
                          f"3. Be from a different governance platform\n\n"
                          f"Recommendation: Try web search for 'tally.xyz {dao_name.lower()} proposal {prop_id}' or check Snapshot.",
                "recommend_web_search": True,
                "web_search_query": f"tally.xyz {dao_name.lower()} proposal {prop_id}"
            }
        
        # If no suggestions found, return generic error
        return {
            "rows": [],
            "sql": retry_out.get("sql", "") if isinstance(retry_out, dict) else "",
            "error": "No results found. The requested information may not be available in our database, or try rephrasing your question with different terms.",
            "repaired": False
        }

    async def _arun(self, user_query: str, additional_context: str = "") -> Dict[str, Any]:
        return self._run(user_query, additional_context)

    # ---------- Internal helpers
    def _shrink_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        try:
            max_rows = int(os.environ.get("TOOL_MAX_ROWS", "20"))
            max_fields = int(os.environ.get("TOOL_MAX_FIELDS", "16"))
            max_chars_per_value = int(os.environ.get("TOOL_MAX_CHARS_PER_VALUE", "500"))
            max_total_chars = int(os.environ.get("TOOL_MAX_TOTAL_CHARS", "20000"))

            out: List[Dict[str, Any]] = []
            total_chars = 0
            for raw in (rows or [])[: max_rows]:
                if not isinstance(raw, dict):
                    continue
                keys = list(raw.keys())[: max_fields]
                compact: Dict[str, Any] = {}
                for k in keys:
                    v = raw.get(k)
                    if isinstance(v, (dict, list)):
                        continue
                    if isinstance(v, (int, float)):
                        compact[k] = v
                    else:
                        s = str(v) if v is not None else ""
                        if len(s) > max_chars_per_value:
                            s = s[: max_chars_per_value] + "…"
                        compact[k] = s
                line = json.dumps(compact, ensure_ascii=False)
                if total_chars + len(line) + 1 > max_total_chars and out:
                    break
                out.append(compact)
                total_chars += len(line) + 1
            return out
        except Exception:
            return rows

    def _repair_and_execute(self, user_query: str, previous_sql: str, reason: str, additional_context: str) -> Dict[str, Any]:
        try:
            logger.info("SQLQueryTool: attempting automatic repair due to DB error")
            repair_tool = SQLRepairTool()
            repaired_sql = repair_tool._run(
                user_query=user_query,
                previous_sql=previous_sql,
                reason=reason,
                schema_text=DATABASE_CONTEXT,
                additional_context=additional_context,
            )
            if not repaired_sql:
                logger.warning("SQLQueryTool: repair produced no SQL; giving up")
                return {"rows": [], "sql": previous_sql, "repaired": False}
            # Recompute embedding in case repaired SQL still needs it
            try:
                vector = self._embedding.create_embeddings([user_query])[0]
            except Exception as e:
                logger.error("SQLQueryTool: embedding error during repair: %s", e, exc_info=True)
                vector = None
            try:
                logger.info("SQLQueryTool: executing repaired SQL:\n%s", repaired_sql)
                rows = DatabaseService.query_database(vector, repaired_sql)
                original_count = len(rows or [])
                shrunk = self._shrink_rows(rows or [])
                logger.info(
                    "SQLQueryTool: repaired query returned %d row(s); delivering %d row(s) after shrinking",
                    original_count,
                    len(shrunk or []),
                )
                try:
                    emit_tool_event("sql_query.repaired_output", {"row_count": len(shrunk or []), "sql": repaired_sql, "repaired": True})
                except Exception:
                    pass
                return {"rows": shrunk, "sql": repaired_sql, "repaired": True}
            except Exception as e:
                logger.error("SQLQueryTool: repaired query execution failed: %s", e, exc_info=True)
                try:
                    emit_tool_event("sql_query.error", {"message": str(e), "sql": repaired_sql, "repaired": True})
                except Exception:
                    pass
                return {"rows": [], "sql": repaired_sql, "repaired": True, "error": str(e)}
        except Exception as e:
            logger.error("SQLQueryTool: automatic repair failed: %s", e, exc_info=True)
            try:
                emit_tool_event("sql_query.error", {"message": str(e), "sql": previous_sql, "repaired": False})
            except Exception:
                pass
            return {"rows": [], "sql": previous_sql, "repaired": False, "error": str(e)}

    def _contains_embedding_usage(self, sql: str) -> bool:
        try:
            lowered = sql.lower()
            return ("{prompt_vector}" in sql) or ("<-> '{prompt_vector}'::vector" in lowered) or ("embedding <->" in lowered)
        except Exception:
            return False