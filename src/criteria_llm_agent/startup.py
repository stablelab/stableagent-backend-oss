"""
Startup initialization for Criteria LLM Agent.

Handles application startup tasks including database connection pool initialization.
"""
import logging
from src.utils.db_utils import initialize_database, test_database_connection

logger = logging.getLogger(__name__)


def initialize_criteria_agent():
    """
    Initialize the criteria agent on application startup.
    
    This function should be called once during application startup to:
    1. Load database configuration from environment variables
    2. Initialize the database connection pool
    3. Test database connectivity
    
    Required environment variables:
    - GROWTH_DATABASE_HOST: Database host
    - GROWTH_DATABASE_NAME: Database name
    - GROWTH_DATABASE_USER: Database user
    - GROWTH_DATABASE_PASSWORD: Database password
    
    Optional environment variables:
    - GROWTH_DATABASE_PORT: Database port (default: 5432)
    - GROWTH_DATABASE_MIN_CONN: Minimum pool connections (default: 1)
    - GROWTH_DATABASE_MAX_CONN: Maximum pool connections (default: 10)
    
    Raises:
        ValueError: If required environment variables are missing
        RuntimeError: If database initialization fails
    
    Example:
        # In your FastAPI app startup
        from src.criteria_llm_agent.startup import initialize_criteria_agent
        
        @app.on_event("startup")
        async def startup_event():
            initialize_criteria_agent()
    """
    logger.info("Initializing Criteria LLM Agent...")
    
    try:
        # Initialize database connection pool
        db_manager = initialize_database()
        logger.info("Database connection pool initialized successfully")
        
        # Test database connectivity
        if test_database_connection():
            logger.info("Database connectivity test passed")
        else:
            logger.warning("Database connectivity test failed - check connection settings")
        
        logger.info("Criteria LLM Agent initialization complete")
        
    except ValueError as e:
        logger.error(f"Configuration error during initialization: {e}")
        raise
    except RuntimeError as e:
        logger.error(f"Runtime error during initialization: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during initialization: {e}", exc_info=True)
        raise


def shutdown_criteria_agent():
    """
    Shutdown the criteria agent.
    
    This function should be called during application shutdown to:
    1. Close all database connections
    2. Clean up resources
    
    Example:
        # In your FastAPI app shutdown
        from src.criteria_llm_agent.startup import shutdown_criteria_agent
        
        @app.on_event("shutdown")
        async def shutdown_event():
            shutdown_criteria_agent()
    """
    logger.info("Shutting down Criteria LLM Agent...")
    
    try:
        from src.utils.db_utils import close_database
        close_database()
        logger.info("Criteria LLM Agent shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)
