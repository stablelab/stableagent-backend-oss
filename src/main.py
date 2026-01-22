from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import os
from src.routers.fastapi_router import router as api_router

from src.utils.langsmith import log_tracking_status
from src.utils.startup_validation import validate_startup
from src.utils.logger import logger

# Run startup validation
logger.info("StableAgent Backend starting up...")
if not validate_startup():
    logger.error("Startup validation failed. Please check configuration.")
    # Don't exit here as FastAPI might be running in a container where we want to see the errors
    # but still allow health checks to work

app = FastAPI(title="StableAgent Backend", version="0.1.0")

# Validate required environment variables
cors_origins_env = os.getenv("ALLOWED_ORIGINS")
if not cors_origins_env:
    raise ValueError("ALLOWED_ORIGINS environment variable is required")

# Parse allowed origins - cannot use "*" when credentials are enabled
allowed_origins = [origin.strip() for origin in cors_origins_env.split(",")]
logger.info(f"Allowed origins: {allowed_origins}")

# Add CORS middleware FIRST (so it wraps everything and runs first)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],  # Allow all headers
    expose_headers=["*"],  # Expose all response headers to the client
)
logger.info("✅ CORS middleware configured")

# Privy authentication configuration (optional - only if using auth)
privy_app_id = os.getenv("PRIVY_APP_ID")
privy_app_secret = os.getenv("PRIVY_APP_SECRET")

# Add Privy authentication middleware (if configured)
# This middleware passively authenticates all requests but doesn't enforce auth.
# Route dependencies (get_current_user) enforce authentication requirements.
if privy_app_id and privy_app_secret:
    from src.auth.middleware import PrivyAuthMiddleware
    
    app.add_middleware(PrivyAuthMiddleware)
    logger.info("✅ Privy authentication middleware enabled (passive mode)")
    logger.info("   Authentication is enforced by router-level dependencies")
else:
    logger.info("⚠️  Privy authentication disabled (PRIVY_APP_ID or PRIVY_APP_SECRET not set)")

@app.get("/healthz")
def healthz() -> dict:
    """Enhanced health check with system status."""
    try:
        # Basic health check
        health_status = {"status": "ok", "timestamp": logger.handlers[0].formatter.formatTime(logger.makeRecord("", 0, "", 0, "", (), None)) if logger.handlers else "unknown"}
        
        # Check database connectivity and pool status
        try:
            from src.services.connection_pool import get_connection_pool
            pool = get_connection_pool()
            pool_stats = pool.get_stats()
            
            if pool_stats.get("in_backoff"):
                health_status["database"] = "backoff mode"
                health_status["status"] = "degraded"
            else:
                # Test actual connection
                conn = pool.get_connection()
                pool.return_connection(conn)
                health_status["database"] = "connected"
                
            health_status["pool_stats"] = {
                "failure_count": pool_stats.get("failure_count", 0),
                "pool_exists": pool_stats.get("pool_exists", False)
            }
        except Exception as e:
            health_status["database"] = f"error: {str(e)[:100]}"
            health_status["status"] = "degraded"
        
        # Check required environment variables
        required_vars = ["STABLELAB_TOKEN", "DATABASE_HOST", "DATABASE_NAME", "DATABASE_USER"]
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        if missing_vars:
            health_status["config"] = f"missing: {', '.join(missing_vars)}"
            health_status["status"] = "error"
        else:
            health_status["config"] = "ok"
        
        return health_status
        
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.on_event("startup")
async def startup_event():
    """Initialize services on application startup."""
    logger.info("Starting StableAgent Backend...")
    
    # Log LangSmith tracking status
    log_tracking_status()
    
    # Initialize Criteria LLM Agent database connection pool
    try:
        from src.criteria_llm_agent.startup import initialize_criteria_agent
        initialize_criteria_agent()
        logger.info("✅ Criteria LLM Agent initialized")
    except ImportError:
        logger.info("Criteria LLM Agent not available, skipping initialization")
    except Exception as e:
        logger.warning(f"Failed to initialize Criteria LLM Agent: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on application shutdown."""
    logger.info("Shutting down StableAgent Backend...")
    
    # Shutdown Criteria LLM Agent
    try:
        from src.criteria_llm_agent.startup import shutdown_criteria_agent
        shutdown_criteria_agent()
        logger.info("✅ Criteria LLM Agent shut down")
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Error during Criteria LLM Agent shutdown: {e}")


# Mount API routes
app.include_router(api_router)

