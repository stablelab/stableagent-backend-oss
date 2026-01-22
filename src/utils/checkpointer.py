from __future__ import annotations

import os
from typing import Any, Optional

from src.utils.logger import logger


def _ensure_dir(path: str) -> None:
    """Ensure the directory for a file path exists."""
    try:
        directory = os.path.dirname(os.path.abspath(path))
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
    except Exception:
        pass


# Global checkpointer instance (singleton)
_checkpointer_instance: Optional[Any] = None


def get_checkpointer() -> Any:
    """Return a LangGraph checkpointer based on environment configuration.

    Supported values for LANGGRAPH_CHECKPOINTER:
      - "memory" (default): in-process MemorySaver
      - "sqlite": sqlite-backed saver at LANGGRAPH_SQLITE_PATH (default ./data/langgraph.sqlite)
      - "postgresql": PostgreSQL-backed saver using LANGGRAPH_POSTGRES_URI
      
    For PostgreSQL, connection pool settings:
      - PG_POOL_MIN: Minimum pool size (default: 2)
      - PG_POOL_MAX: Maximum pool size (default: 10)
      - PG_TIMEOUT: Command timeout in seconds (default: 30)
    """
    global _checkpointer_instance
    
    # Return cached instance if available
    if _checkpointer_instance is not None:
        return _checkpointer_instance
    
    backend = (os.environ.get("LANGGRAPH_CHECKPOINTER", "memory") or "memory").lower()

    logger.info(f"[Checkpointer] Initializing with backend: {backend}")

    # PostgreSQL checkpointer
    if backend == "postgresql":
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
        except ImportError as e:
            logger.error("langgraph-checkpoint-postgres not installed")
            raise RuntimeError(
                "LangGraph PostgreSQL checkpointer not available. "
                "Install 'langgraph-checkpoint-postgres'."
            ) from e
        
        connection_string = os.environ.get("LANGGRAPH_POSTGRES_URI")
        if not connection_string:
            raise ValueError(
                "LANGGRAPH_POSTGRES_URI environment variable is required for PostgreSQL checkpointer. "
                "Format: postgresql://user:password@host:port/database"
            )
        
        # Connection pool configuration
        pool_min = int(os.environ.get("PG_POOL_MIN", "2"))
        pool_max = int(os.environ.get("PG_POOL_MAX", "10"))
        
        logger.info(f"[Checkpointer] Creating PostgreSQL checkpointer (pool: {pool_min}-{pool_max})")
        
        try:
            # Create synchronous PostgresSaver for non-async contexts
            _checkpointer_instance = PostgresSaver.from_conn_string(connection_string)
            logger.info("[Checkpointer] PostgreSQL checkpointer created successfully")
            return _checkpointer_instance
        except Exception as e:
            logger.error(f"[Checkpointer] Failed to create PostgreSQL checkpointer: {e}")
            raise RuntimeError(f"Failed to initialize PostgreSQL checkpointer: {e}") from e

    # SQLite checkpointer
    if backend == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as e:
            logger.error("LangGraph sqlite checkpointer not available")
            raise RuntimeError(
                "LangGraph sqlite checkpointer not available. Install 'langgraph'."
            ) from e
        
        db_path = os.environ.get("LANGGRAPH_SQLITE_PATH", "./data/langgraph.sqlite")
        _ensure_dir(db_path)
        
        logger.info(f"[Checkpointer] Creating SQLite checkpointer at {db_path}")
        _checkpointer_instance = SqliteSaver.from_file(db_path)
        return _checkpointer_instance

    # Default: Memory checkpointer
    try:
        from langgraph.checkpoint.memory import MemorySaver
    except ImportError as e:
        logger.error("LangGraph not installed")
        raise RuntimeError("LangGraph not installed. Please install 'langgraph'.") from e
    
    logger.info("[Checkpointer] Creating in-memory checkpointer")
    _checkpointer_instance = MemorySaver()
    return _checkpointer_instance


async def get_async_checkpointer() -> Any:
    """Return an async LangGraph checkpointer for PostgreSQL.
    
    This is useful for async contexts where we want non-blocking database operations.
    Falls back to sync checkpointer for memory/sqlite backends.
    
    Supported values for LANGGRAPH_CHECKPOINTER:
      - "memory": Returns sync MemorySaver (works in async context)
      - "sqlite": Returns sync SqliteSaver (works in async context)
      - "postgresql": Returns AsyncPostgresSaver for true async operations
    """
    backend = (os.environ.get("LANGGRAPH_CHECKPOINTER", "memory") or "memory").lower()
    
    if backend == "postgresql":
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        except ImportError as e:
            logger.error("langgraph-checkpoint-postgres not installed for async")
            raise RuntimeError(
                "LangGraph async PostgreSQL checkpointer not available. "
                "Install 'langgraph-checkpoint-postgres'."
            ) from e
        
        connection_string = os.environ.get("LANGGRAPH_POSTGRES_URI")
        if not connection_string:
            raise ValueError(
                "LANGGRAPH_POSTGRES_URI environment variable is required for PostgreSQL checkpointer."
            )
        
        logger.info("[Checkpointer] Creating async PostgreSQL checkpointer")
        
        try:
            return AsyncPostgresSaver.from_conn_string(connection_string)
        except Exception as e:
            logger.error(f"[Checkpointer] Failed to create async PostgreSQL checkpointer: {e}")
            raise RuntimeError(f"Failed to initialize async PostgreSQL checkpointer: {e}") from e
    
    # For non-PostgreSQL backends, return the sync version
    return get_checkpointer()


async def initialize_checkpointer() -> None:
    """Initialize the checkpointer tables (for PostgreSQL).
    
    This should be called at application startup to ensure
    the checkpoint tables exist in the database.
    
    For memory/sqlite backends, this is a no-op.
    """
    backend = (os.environ.get("LANGGRAPH_CHECKPOINTER", "memory") or "memory").lower()
    
    if backend != "postgresql":
        logger.info(f"[Checkpointer] No initialization needed for {backend} backend")
        return
    
    logger.info("[Checkpointer] Initializing PostgreSQL checkpointer tables...")
    
    try:
        checkpointer = await get_async_checkpointer()
        
        # Setup creates the necessary tables
        if hasattr(checkpointer, 'setup'):
            async with checkpointer:
                await checkpointer.setup()
            logger.info("[Checkpointer] PostgreSQL tables initialized successfully")
        else:
            logger.info("[Checkpointer] Checkpointer does not require setup")
            
    except Exception as e:
        logger.error(f"[Checkpointer] Failed to initialize tables: {e}")
        raise RuntimeError(
            f"Failed to initialize PostgreSQL checkpointer tables: {e}. "
            "Ensure the database is accessible and the user has CREATE TABLE permissions."
        ) from e


async def health_check_checkpointer() -> dict:
    """Check the health of the checkpointer connection.
    
    Returns a dict with:
      - status: "healthy" or "unhealthy"
      - backend: The checkpointer backend type
      - error: Error message if unhealthy
    """
    backend = (os.environ.get("LANGGRAPH_CHECKPOINTER", "memory") or "memory").lower()
    
    result = {
        "status": "healthy",
        "backend": backend,
    }
    
    if backend == "memory":
        # Memory is always healthy
        return result
    
    if backend == "sqlite":
        try:
            checkpointer = get_checkpointer()
            # Try to access the connection
            if hasattr(checkpointer, 'conn') and checkpointer.conn:
                result["status"] = "healthy"
            return result
        except Exception as e:
            result["status"] = "unhealthy"
            result["error"] = str(e)
            return result
    
    if backend == "postgresql":
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            
            connection_string = os.environ.get("LANGGRAPH_POSTGRES_URI")
            if not connection_string:
                result["status"] = "unhealthy"
                result["error"] = "LANGGRAPH_POSTGRES_URI not configured"
                return result
            
            # Try to create a connection
            checkpointer = AsyncPostgresSaver.from_conn_string(connection_string)
            async with checkpointer:
                # Connection successful
                result["status"] = "healthy"
            return result
            
        except Exception as e:
            result["status"] = "unhealthy"
            result["error"] = str(e)
            logger.error(f"[Checkpointer] Health check failed: {e}")
            return result
    
    result["status"] = "unhealthy"
    result["error"] = f"Unknown backend: {backend}"
    return result


def reset_checkpointer() -> None:
    """Reset the global checkpointer instance.
    
    This is useful for testing or when switching configurations.
    """
    global _checkpointer_instance
    _checkpointer_instance = None
    logger.info("[Checkpointer] Global instance reset")
