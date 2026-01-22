import psycopg2
import os
import re
import time
from psycopg2 import extensions
from src.config.common_settings import DATABASE_HOST, DATABASE_PORT, DATABASE_NAME, DATABASE_USER, DATABASE_PASSWORD
from src.utils.logger import logger
from src.utils.sql_validator import is_valid_sql_select
from src.services.connection_pool import get_connection_pool

class DatabaseService:
    @staticmethod
    def get_connection():
        """Get a database connection from the connection pool."""
        try:
            pool = get_connection_pool()
            conn = pool.get_connection()
            return conn
        except Exception as e:
            logger.error("DatabaseService: Failed to get connection from pool: %s", e)
            raise
    
    @staticmethod
    def _setup_connection(conn):
        """Setup connection with proper type casting and timeouts."""
        # Ensure DATE/TIMESTAMP come back as strings to avoid out-of-range conversions
        try:
            # Cast DATE and TIMESTAMP to TEXT on fetch
            extensions.register_type(extensions.new_type(1082, "DATE", lambda v, c: v))  # DATE
            extensions.register_type(extensions.new_type(1114, "TIMESTAMP", lambda v, c: v))  # TIMESTAMP WITHOUT TZ
            extensions.register_type(extensions.new_type(1184, "TIMESTAMPTZ", lambda v, c: v))  # TIMESTAMP WITH TZ
        except Exception:
            # Safe to continue; worst case default casting applies
            pass
        
        # Enforce a maximum query runtime per session (reduced from 300s to 60s for better UX)
        try:
            timeout_ms = int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "60000"))  # Reduced to 60 seconds
            with conn.cursor() as _cur:
                _cur.execute("SET statement_timeout = %s", (timeout_ms,))
                # Also set lock timeout to prevent hanging on locks
                _cur.execute("SET lock_timeout = %s", (timeout_ms,))
        except Exception as e:
            logger.warning("Failed to set database timeouts: %s", e)
            # Never fail connection setup due to timeout configuration
            pass

    @staticmethod
    def query_database(query_embedding, sql_select):
        conn = None
        pool = None
        try:
            # Get connection from pool
            pool = get_connection_pool()
            conn = pool.get_connection()
            
            # Setup connection for this query
            DatabaseService._setup_connection(conn)
            
            # validate the query
            if not is_valid_sql_select(sql_select):
                logger.error("Invalid SQL query: %s", sql_select)
                return []
            updated_query = DatabaseService._replace_prompt_vector(sql_select, query_embedding)
            # Use a cursor that returns raw strings for date/time types
            cur = conn.cursor()
            if not updated_query:
                return []
            # Log final SQL (after vector substitution) with embeddings redacted
            try:
                max_chars = int(os.environ.get("LOG_SQL_MAX_CHARS", "20000"))
            except Exception:
                max_chars = 20000
            try:
                to_log = DatabaseService._redact_vector_literals(updated_query)
            except Exception:
                to_log = updated_query
            if isinstance(to_log, str) and len(to_log) > max_chars:
                to_log = to_log[:max_chars] + "…"
            logger.info("DatabaseService: executing SQL (%d chars):\n%s", len(updated_query or ""), to_log)
            start_time = time.perf_counter()
            cur.execute(updated_query)
            results = cur.fetchall()
            elapsed = time.perf_counter() - start_time
            logger.info("DatabaseService: query completed in %.2fs, %d rows", elapsed, len(results))
            column_names = [desc[0] for desc in cur.description]
            return [dict(zip(column_names, row)) for row in results]
        except psycopg2.OperationalError as e:
            logger.error("Database operational error: %s", e, exc_info=True)
            # Provide more specific error messages for common issues
            error_msg = str(e).lower()
            if "password authentication failed" in error_msg:
                raise RuntimeError("Database authentication failed. Please check your credentials.") from e
            elif "timeout" in error_msg or "timed out" in error_msg:
                raise RuntimeError("Database query timed out. Please try a simpler query or contact support.") from e
            elif "connection" in error_msg:
                raise RuntimeError("Database connection lost. Please try again.") from e
            else:
                raise RuntimeError(f"Database error: {e}") from e
        except psycopg2.Error as e:
            logger.error("Database SQL error: %s", e, exc_info=True)
            # Handle SQL-specific errors
            raise RuntimeError(f"SQL execution error: {e}") from e
        except Exception as e:
            logger.error("Unexpected database error: %s", e, exc_info=True)
            # Propagate to callers so higher-level tools can attempt SQL repair
            raise RuntimeError(f"Unexpected database error: {e}") from e
        finally:
            if conn and pool:
                pool.return_connection(conn)

    @staticmethod
    def _replace_prompt_vector(query: str, prompt_vector) -> str:
        """
        Replaces the placeholder in the SQL query with the actual vector.
        
        Args:
            query: The SQL query containing the {prompt_vector} placeholder
            prompt_vector: The vector to insert, can be None, a list, or another format
            
        Returns:
            The SQL query with the vector placeholder replaced
        """
        if prompt_vector is None:
            logger.warning("No embedding vector provided for query")
            return query
            
        if isinstance(prompt_vector, list):
            vector_str = "[" + ", ".join(map(str, prompt_vector)) + "]"
        else:
            vector_str = str(prompt_vector)
        return query.replace("{prompt_vector}", vector_str) 

    @staticmethod
    def _redact_vector_literals(query: str) -> str:
        """
        Redact vector literals like '[0.12, 0.34, ...]'::vector from SQL for safe logging/history.
        Keeps structure but removes numeric contents.
        """
        if not isinstance(query, str):
            return query
        try:
            # Replace quoted vector literals: '[...]'::vector → '[REDACTED_EMBEDDING]'::vector
            redacted = re.sub(r"'\[[^\]]*\]'\s*::\s*vector", "'[REDACTED_EMBEDDING]'::vector", query)
            # Also handle unquoted bracket vector followed by ::vector (defensive)
            redacted = re.sub(r"\[[^\]]*\]\s*::\s*vector", "'[REDACTED_EMBEDDING]'::vector", redacted)
            # As a final fallback, collapse any long numeric bracket list to a placeholder
            redacted = re.sub(r"\[[\s0-9eE,\.-]{20,}\]", "[REDACTED_EMBEDDING]", redacted)
            return redacted
        except Exception:
            return query