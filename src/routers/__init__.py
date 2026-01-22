from fastapi import APIRouter

# Aggregate sub-routers for compatibility with existing main.py include
from .routes_chat import router as chat_router
from .routes_stream import router as stream_router
from .routes_responses import router as responses_router
from .routes_agent import router as agent_router

router = APIRouter()
router.include_router(chat_router)
router.include_router(stream_router)
router.include_router(responses_router)
router.include_router(agent_router)


