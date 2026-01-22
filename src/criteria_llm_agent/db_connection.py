"""
Database connection management for Criteria LLM Agent.

Loads database credentials from environment variables and manages
connection pooling for PostgreSQL.
"""
import os
import logging
from typing import Optional
from contextlib import contextmanager

try:
    import psycopg2
    from psycopg2 import pool
    _HAS_PSYCOPG2 = True
except ImportError:
    psycopg2 = None
    pool = None
    _HAS_PSYCOPG2 = False

logger = logging.getLogger(__name__)


class DatabaseConnectionManager:
    """
    Manages database connections with connection pooling.
    
    Loads configuration from environment variables and provides
    a connection pool for efficient database access.
    """
    
    def __init__(self):
        """Initialize connection manager with environment variables."""
        self._pool: Optional[pool.SimpleConnectionPool] = None
        self._config = self._load_config_from_env()
        
    def _load_config_from_env(self) -> dict:
        """
        Load database configuration from environment variables.
        
        Required environment variables:
        - GROWTH_DATABASE_HOST: Database host
        - GROWTH_DATABASE_NAME: Database name
        - GROWTH_DATABASE_USER: Database user
        - GROWTH_DATABASE_PASSWORD: Database password
        
        Optional environment variables:
        - GROWTH_DATABASE_PORT: Database port (default: 5432)
        - GROWTH_DATABASE_MIN_CONN: Minimum pool connections (default: 1)
        - GROWTH_DATABASE_MAX_CONN: Maximum pool connections (default: 10)
        
        Returns:
            dict: Database configuration
            
        Raises:
            ValueError: If required environment variables are missing
        """
        required_vars = [
            'GROWTH_DATABASE_HOST',
            'GROWTH_DATABASE_NAME',
            'GROWTH_DATABASE_USER',
            'GROWTH_DATABASE_PASSWORD'
        ]
        
        # Check for missing required variables
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}. "
                "Please set all required database configuration variables."
            )
        
        logger.info(f"Loading database configuration from environment variables: {os.environ['GROWTH_DATABASE_HOST']}")
        logger.info(f"Loading database configuration from environment variables: {os.environ['GROWTH_DATABASE_NAME']}")
        config = {
            'host': os.environ['GROWTH_DATABASE_HOST'],
            'database': os.environ['GROWTH_DATABASE_NAME'],
            'user': os.environ['GROWTH_DATABASE_USER'],
            'password': os.environ['GROWTH_DATABASE_PASSWORD'],
            'port': int(os.environ.get('GROWTH_DATABASE_PORT', '5432')),
            'min_conn': int(os.environ.get('GROWTH_DATABASE_MIN_CONN', '1')),
            'max_conn': int(os.environ.get('GROWTH_DATABASE_MAX_CONN', '10'))
        }
        
        logger.info(
            f"Database configuration loaded: host={config['host']}, "
            f"database={config['database']}, user={config['user']}, "
            f"port={config['port']}"
        )
        
        return config
    
    def initialize_pool(self):
        """
        Initialize the connection pool.
        
        Creates a connection pool with the configured min/max connections.
        
        Raises:
            RuntimeError: If psycopg2 is not available
            Exception: If connection pool creation fails
        """
        if not _HAS_PSYCOPG2:
            raise RuntimeError(
                "psycopg2 is not installed. Install it with: pip install psycopg2-binary"
            )
        
        if self._pool is not None:
            logger.warning("Connection pool already initialized")
            return
        
        try:
            self._pool = psycopg2.pool.SimpleConnectionPool(
                minconn=self._config['min_conn'],
                maxconn=self._config['max_conn'],
                host=self._config['host'],
                database=self._config['database'],
                user=self._config['user'],
                password=self._config['password'],
                port=self._config['port']
            )
            
            logger.info(
                f"Database connection pool initialized: "
                f"min={self._config['min_conn']}, max={self._config['max_conn']}"
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise
    
    def get_connection(self):
        """
        Get a connection from the pool.
        
        Returns:
            Database connection from the pool
            
        Raises:
            RuntimeError: If pool is not initialized
            Exception: If getting connection fails
        """
        if self._pool is None:
            raise RuntimeError(
                "Connection pool not initialized. Call initialize_pool() first."
            )
        
        try:
            conn = self._pool.getconn()
            logger.debug("Database connection acquired from pool")
            return conn
        except Exception as e:
            logger.error(f"Failed to get connection from pool: {e}")
            raise
    
    def return_connection(self, conn):
        """
        Return a connection to the pool.
        
        Args:
            conn: Database connection to return
        """
        if self._pool is None:
            logger.warning("Cannot return connection: pool not initialized")
            return
        
        try:
            self._pool.putconn(conn)
            logger.debug("Database connection returned to pool")
        except Exception as e:
            logger.error(f"Failed to return connection to pool: {e}")
    
    @contextmanager
    def get_connection_context(self):
        """
        Context manager for database connections.
        
        Automatically acquires and returns connections to the pool.
        
        Yields:
            Database connection
            
        Example:
            with db_manager.get_connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM table")
        """
        conn = self.get_connection()
        try:
            yield conn
        finally:
            self.return_connection(conn)
    
    def close_all_connections(self):
        """
        Close all connections in the pool.
        
        Should be called when shutting down the application.
        """
        if self._pool is None:
            logger.warning("Cannot close connections: pool not initialized")
            return
        
        try:
            self._pool.closeall()
            self._pool = None
            logger.info("All database connections closed")
        except Exception as e:
            logger.error(f"Error closing connections: {e}")
    
    def get_direct_connection(self):
        """
        Get a direct database connection (not from pool).
        
        Useful for testing or special cases where pooling is not desired.
        
        Returns:
            Direct database connection
            
        Raises:
            RuntimeError: If psycopg2 is not available
        """
        if not _HAS_PSYCOPG2:
            raise RuntimeError(
                "psycopg2 is not installed. Install it with: pip install psycopg2-binary"
            )
        
        try:
            conn = psycopg2.connect(
                host=self._config['host'],
                database=self._config['database'],
                user=self._config['user'],
                password=self._config['password'],
                port=self._config['port']
            )
            logger.info("Direct database connection created")
            return conn
        except Exception as e:
            logger.error(f"Failed to create direct connection: {e}")
            raise
    
    def test_connection(self) -> bool:
        """
        Test database connectivity.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            conn = self.get_direct_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if result and result[0] == 1:
                logger.info("Database connection test successful")
                return True
            else:
                logger.error("Database connection test failed: unexpected result")
                return False
                
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    @property
    def is_initialized(self) -> bool:
        """Check if connection pool is initialized."""
        return self._pool is not None
    
    @property
    def config(self) -> dict:
        """Get database configuration (with password redacted)."""
        safe_config = self._config.copy()
        safe_config['password'] = '***REDACTED***'
        return safe_config


# Global database manager instance
_db_manager: Optional[DatabaseConnectionManager] = None


def get_db_manager() -> DatabaseConnectionManager:
    """
    Get or create the global database manager instance.
    
    Returns:
        DatabaseConnectionManager: Global database manager
    """
    global _db_manager
    
    if _db_manager is None:
        _db_manager = DatabaseConnectionManager()
        logger.info("Database manager created")
    
    return _db_manager


def initialize_database() -> DatabaseConnectionManager:
    """
    Initialize the database connection pool.
    
    This should be called once during application startup.
    
    Returns:
        DatabaseConnectionManager: Initialized database manager
        
    Raises:
        ValueError: If required environment variables are missing
        RuntimeError: If psycopg2 is not available
    """
    db_manager = get_db_manager()
    
    if not db_manager.is_initialized:
        db_manager.initialize_pool()
        logger.info("Database connection pool initialized successfully")
    else:
        logger.warning("Database already initialized")
    
    return db_manager


def get_database_connection():
    """
    Get a database connection from the pool.
    
    This is the main function to use for getting database connections.
    
    Returns:
        Database connection
        
    Raises:
        RuntimeError: If database is not initialized
        
    Example:
        conn = get_database_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM table")
        finally:
            return_database_connection(conn)
    """
    db_manager = get_db_manager()
    
    if not db_manager.is_initialized:
        raise RuntimeError(
            "Database not initialized. Call initialize_database() first. "
            "This should be done during application startup."
        )
    
    return db_manager.get_connection()


def return_database_connection(conn):
    """
    Return a database connection to the pool.
    
    Args:
        conn: Database connection to return
    """
    db_manager = get_db_manager()
    db_manager.return_connection(conn)


@contextmanager
def get_db_connection_context():
    """
    Context manager for database connections.
    
    Automatically handles connection acquisition and return.
    
    Yields:
        Database connection
        
    Example:
        with get_db_connection_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM table")
    """
    db_manager = get_db_manager()
    with db_manager.get_connection_context() as conn:
        yield conn


def close_database():
    """
    Close all database connections.
    
    Should be called during application shutdown.
    """
    db_manager = get_db_manager()
    db_manager.close_all_connections()
    logger.info("Database connections closed")


def test_database_connection() -> bool:
    """
    Test database connectivity.
    
    Returns:
        bool: True if connection successful, False otherwise
    """
    db_manager = get_db_manager()
    return db_manager.test_connection()
