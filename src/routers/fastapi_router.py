from fastapi import APIRouter

from src.utils.logger import logger

from .routes_agent import agent_run  # noqa: F401
# Thin compatibility shim: delegate to split route modules without changing behavior
from .routes_chat import lc_chat  # noqa: F401
from .routes_responses import compat_openai_responses  # noqa: F401
from .routes_stream import compat_openai_chat_completions  # noqa: F401
from .routes_stream import lc_chat_stream
from .routes_delegate import analyse_proposal_with_reasoning, get_analysis_cache_stats, invalidate_analysis_cache, get_cached_base_analysis  # noqa: F401
from .routes_multiperspective import analyze_text_multiperspective  # noqa: F401

try:
    from src.form_llm_agent.router import router as form_agent_router
    FORM_AGENT_AVAILABLE = True
except ImportError as e:
    logger.info(f"Form LLM Agent not available: {e}")
    FORM_AGENT_AVAILABLE = False

try:
    from src.criteria_llm_agent.router import router as criteria_agent_router
    CRITERIA_AGENT_AVAILABLE = True
except ImportError as e:
    logger.info(f"Criteria LLM Agent not available: {e}")
    CRITERIA_AGENT_AVAILABLE = False

try:
    from src.auth.router import router as auth_router
    AUTH_ROUTER_AVAILABLE = True
except ImportError as e:
    logger.info(f"Auth router not available: {e}")
    AUTH_ROUTER_AVAILABLE = False
except Exception as e:
    logger.warning(f"Error loading auth router: {e}")
    AUTH_ROUTER_AVAILABLE = False


try:
    from src.forse_analyze_agent.router.main import \
        router as forse_analyze_agent_router
    FORSE_ANALYZE_AGENT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Forse Analyze Agent import error: {e}")
    FORSE_ANALYZE_AGENT_AVAILABLE = False
except Exception as e:
    logger.warning(f"Forse Analyze Agent not available: {e}", exc_info=True)
    FORSE_ANALYZE_AGENT_AVAILABLE = False

try:
    from src.supervisor_agent.router import router as supervisor_agent_router
    SUPERVISOR_AGENT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Supervisor agent import error: {e}")
    SUPERVISOR_AGENT_AVAILABLE = False
except Exception as e:
    logger.warning(f"Supervisor agent not available: {e}", exc_info=True)
    SUPERVISOR_AGENT_AVAILABLE = False

try:
    from src.growth_chat.router import router as growth_chat_router
    GROWTH_CHAT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Growth Chat import error: {e}", exc_info=True)
    GROWTH_CHAT_AVAILABLE = False
except Exception as e:
    logger.warning(f"Growth Chat not available: {e}", exc_info=True)
    GROWTH_CHAT_AVAILABLE = False


router = APIRouter()
router.add_api_route("/lc/v1/chat", lc_chat, methods=["POST"])
router.add_api_route("/lc/v1/chat/stream", lc_chat_stream, methods=["POST"])
router.add_api_route("/v1/chat/completions",
                     compat_openai_chat_completions, methods=["POST"])
router.add_api_route(
    "/v1/responses", compat_openai_responses, methods=["POST"])
router.add_api_route("/agent/run", agent_run, methods=["POST"])
router.add_api_route(
    "/analyse", analyse_proposal_with_reasoning, methods=["GET"])
router.add_api_route("/admin/cache-stats",
                     get_analysis_cache_stats, methods=["GET"])
router.add_api_route("/admin/invalidate-cache",
                     invalidate_analysis_cache, methods=["GET", "POST"])
router.add_api_route("/debug/base-analysis",
                     get_cached_base_analysis, methods=["GET"])
router.add_api_route("/multi-perspective/analyze-text",
                     analyze_text_multiperspective, methods=["POST"])

# Include form_llm_agent routes if available
if FORM_AGENT_AVAILABLE:
    logger.info("Form LLM Agent available")
    router.include_router(
        form_agent_router, prefix="/form", tags=["form-llm-agent"])
else:
    logger.info("Form LLM Agent not available")

# Include criteria_llm_agent routes if available
if CRITERIA_AGENT_AVAILABLE:
    logger.info("Criteria LLM Agent available")
    router.include_router(
        criteria_agent_router, prefix="/criteria", tags=["criteria-llm-agent"])
else:
    logger.info("Criteria LLM Agent not available")

# Include knowledge_base_agent routes if available
# TODO: uncomment this
# if KNOWLEDGE_BASE_AGENT_AVAILABLE:
#     logger.info("Knowledge Base Agent available")
#     router.include_router(
#         knowledge_base_router, prefix="/knowledge", tags=["knowledge-base-agent"])
# else:
#     logger.info("Knowledge Base Agent not available")

# Include app_automation_agent routes if available
# if app_automation_agent_AVAILABLE:
#     logger.info("Grants Admin Agent available")
#     # TODO: change prefix from /knowledge
#     router.include_router(
#         app_automation_agent_router, prefix="/knowledge", tags=["grants-admin-agent"])
# else:
#     logger.info("Grants Admin Agent not available")

# Include auth routes if available
if AUTH_ROUTER_AVAILABLE:
    logger.info("Auth router available")
    router.include_router(auth_router)
else:
    logger.info("Auth router not available")

# Include forse_analyze_agent routes if available
if FORSE_ANALYZE_AGENT_AVAILABLE:
    logger.info("Forse Analyze Agent available")
    router.include_router(
        forse_analyze_agent_router, prefix="/forse-analyze", tags=["forse-analyze-agent"])
else:
    logger.info("Forse Analyze Agent not available")

# Include supervisor_agent routes if available
if SUPERVISOR_AGENT_AVAILABLE:
    logger.info("Supervisor Agent available")
    router.include_router(
        supervisor_agent_router, prefix="/supervisor", tags=["supervisor-agent"])
else:
    logger.info("Supervisor Agent not available")

# Include growth_chat routes if available
if GROWTH_CHAT_AVAILABLE:
    logger.info("Growth Chat available")
    router.include_router(
        # TODO: change prefix
        growth_chat_router, prefix="/knowledge", tags=["growth-chat"])
else:
    logger.info("Growth Chat not available")

# Include delegate_agent routes if available
