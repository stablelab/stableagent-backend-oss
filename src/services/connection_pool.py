"""
Database connection pooling to prevent repeated authentication failures.

This module provides a simple connection pool that reuses database connections
and handles connection failures gracefully with exponential backoff.
"""

import time
import threading
from typing import Optional, Dict, Any
import psycopg2
from psycopg2 import pool
from src.utils.logger import logger
from src.config.database_config import get_database_config


class DatabaseConnectionPool:
    """Thread-safe database connection pool with failure handling."""
    
    def __init__(self, min_connections: int = 1, max_connections: int = 5):
        self._pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
        self._lock = threading.Lock()
        self._min_connections = min_connections
        self._max_connections = max_connections
        self._last_failure_time = 0
        self._failure_count = 0
        self._max_failure_count = 3
        self._backoff_seconds = 30
        
    def _create_pool(self) -> psycopg2.pool.ThreadedConnectionPool:
        """Create a new connection pool."""
        config = get_database_config()
        connection_params = config.get_connection_params()
        
        logger.info("DatabaseConnectionPool: Creating connection pool (min=%d, max=%d)", 
                   self._min_connections, self._max_connections)
        
        return psycopg2.pool.ThreadedConnectionPool(
            self._min_connections,
            self._max_connections,
            **connection_params
        )
    
    def _should_retry(self) -> bool:
        """Check if we should retry after a failure."""
        if self._failure_count < self._max_failure_count:
            return True
        
        time_since_failure = time.time() - self._last_failure_time
        return time_since_failure > self._backoff_seconds
    
    def get_connection(self):
        """Get a connection from the pool."""
        with self._lock:
            # Check if we're in backoff period
            if not self._should_retry():
                raise RuntimeError(
                    f"Database connection pool in backoff mode. "
                    f"Too many failures ({self._failure_count}). "
                    f"Please wait {self._backoff_seconds} seconds before retrying."
                )
            
            # Create pool if it doesn't exist
            if self._pool is None:
                try:
                    self._pool = self._create_pool()
                    self._failure_count = 0  # Reset failure count on successful pool creation
                except Exception as e:
                    self._failure_count += 1
                    self._last_failure_time = time.time()
                    logger.error("DatabaseConnectionPool: Failed to create pool: %s", e)
                    raise RuntimeError(f"Failed to create database connection pool: {e}") from e
            
            # Get connection from pool
            try:
                conn = self._pool.getconn()
                if conn is None:
                    raise RuntimeError("No available connections in pool")
                
                # Test the connection
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                
                return conn
                
            except Exception as e:
                self._failure_count += 1
                self._last_failure_time = time.time()
                logger.error("DatabaseConnectionPool: Failed to get connection: %s", e)
                
                # Close and recreate pool on persistent failures
                if self._failure_count >= 2:
                    logger.warning("DatabaseConnectionPool: Recreating pool due to persistent failures")
                    self._close_pool()
                
                raise RuntimeError(f"Failed to get database connection: {e}") from e
    
    def return_connection(self, conn, close_connection: bool = False):
        """Return a connection to the pool."""
        if self._pool is None:
            return
        
        try:
            if close_connection:
                self._pool.putconn(conn, close=True)
            else:
                self._pool.putconn(conn)
        except Exception as e:
            logger.error("DatabaseConnectionPool: Error returning connection: %s", e)
    
    def _close_pool(self):
        """Close the connection pool."""
        if self._pool is not None:
            try:
                self._pool.closeall()
                logger.info("DatabaseConnectionPool: Closed connection pool")
            except Exception as e:
                logger.error("DatabaseConnectionPool: Error closing pool: %s", e)
            finally:
                self._pool = None
    
    def close(self):
        """Close the connection pool."""
        with self._lock:
            self._close_pool()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        with self._lock:
            if self._pool is None:
                return {
                    "pool_exists": False,
                    "failure_count": self._failure_count,
                    "last_failure_time": self._last_failure_time,
                    "in_backoff": not self._should_retry()
                }
            
            return {
                "pool_exists": True,
                "min_connections": self._min_connections,
                "max_connections": self._max_connections,
                "failure_count": self._failure_count,
                "last_failure_time": self._last_failure_time,
                "in_backoff": not self._should_retry()
            }


# Global connection pool instance
_connection_pool: Optional[DatabaseConnectionPool] = None
_pool_lock = threading.Lock()


def get_connection_pool() -> DatabaseConnectionPool:
    """Get the global connection pool instance."""
    global _connection_pool
    
    with _pool_lock:
        if _connection_pool is None:
            _connection_pool = DatabaseConnectionPool()
        return _connection_pool


def close_connection_pool():
    """Close the global connection pool."""
    global _connection_pool
    
    with _pool_lock:
        if _connection_pool is not None:
            _connection_pool.close()
            _connection_pool = None
