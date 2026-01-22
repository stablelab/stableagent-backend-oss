"""
FastAPI router for Growth Chat Super Graph.

Provides REST API endpoints for the unified knowledge base + grants admin agent.
"""
import json
import os
import traceback
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.utils.db_utils import (get_database_connection,
                                return_database_connection)
from src.utils.langsmith import is_langsmith_enabled
from src.utils.logger import logger

from .knowledge_base_agent.database import KnowledgeDatabase
from .knowledge_base_agent.types import GrowthChatResult
from .schemas import GrowthChatRequest, UserInfo
from .stream import stream_processing

# Router with authentication required
# TODO: uncomment this once we figure out how to get the user from the request
# from src.auth.deps import get_current_user
# router = APIRouter(dependencies=[Depends(get_current_user)])
router = APIRouter()


def _get_auth_token_and_user(
    request: Request,
    authorization: Optional[str] = Header(None)
) -> tuple[str, dict]:
    """
    Get both authentication token and user from request.
    
    Args:
        request: FastAPI request object
        authorization: Authorization header
        
    Returns:
        Tuple of (auth_token, user_dict)
        
    Raises:
        HTTPException: If no token found
    """
    # Get user from request state (set by auth middleware)
    # Note: getattr returns None if the attribute exists but is None,
    # so we need an explicit None check
    user = getattr(request.state, "user", None)
    if user is None:
        user = {"sub": "anonymous"}
    
    # Extract token: try Authorization header first
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    
    # Try to get from cookies
    if not token:
        token = request.cookies.get("privy-id-token")
    
    # Try from request state (set by middleware)
    if not token and hasattr(request.state, "privy_id_token"):
        token = request.state.privy_id_token
    
    if not token:
        raise HTTPException(status_code=401, detail="No authentication token provided")
    
    return token, user


async def _get_user_info_and_visibility(auth_token: str, org_id: int) -> tuple[UserInfo, Optional[str]]:
    """
    Fetch user info and permissions from Growth Backend.
    
    Calls GET /api/users/me to get the user's info and role in the specified organization.
    Based on the role, determines visibility for knowledge hub searches:
    - "Guest" or "Builder" roles: visibility = "public" (only public items)
    - "Staff" or "Admin" roles: visibility = None (access to all items)
    
    Args:
        auth_token: Privy authentication token
        org_id: Organization ID to check role for
        
    Returns:
        Tuple of (UserInfo, visibility_filter)
        - UserInfo: dict with id, handle, email, display_name
        - visibility: "public" for limited access, None for full access
    """
    growth_backend_url = os.getenv("GROWTH_BACKEND_URL", "http://localhost:4000")
    empty_user_info: UserInfo = {}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{growth_backend_url}/api/users/me",
                headers={"privy-id-token": auth_token}
            )
            
            if response.status_code != 200:
                logger.warning(
                    f"Failed to fetch user permissions: {response.status_code}. "
                    f"Defaulting to public visibility."
                )
                return empty_user_info, "public"
            
            data = response.json()
            user_data = data.get("user", {})
            organisations = user_data.get("organisations", [])
            
            # Check if user is a global admin (from user data or is_global_admin flag)
            is_global_admin = user_data.get("is_global_admin", False) or user_data.get("isGlobalAdmin", False)
            
            # Extract user info
            user_info: UserInfo = {
                "id": user_data.get("id"),
                "handle": user_data.get("handle", ""),
                "email": user_data.get("email", ""),
                "display_name": user_data.get("display_name", ""),
                "org_slug": "",  # will be set later
                "is_global_admin": is_global_admin,
            }
            
            # Find the user's role in the current organization
            for org in organisations:
                if org.get("id") == org_id:
                    role_name = org.get("roleName", "")
                    
                    # Staff and Admin have full access (visibility = None)
                    if role_name in ("Staff", "Admin"):
                        logger.info(
                            f"User {user_info.get('email')} has role '{role_name}' in org {org_id}: "
                            f"granting full knowledge hub access"
                        )
                        return user_info, None
                    
                    # Guest and Builder have public-only access
                    logger.info(
                        f"User {user_info.get('email')} has role '{role_name}' in org {org_id}: "
                        f"restricting to public knowledge hub items"
                    )
                    return user_info, "public"
            
            # User not found in organization - default to public
            logger.warning(
                f"User {user_info.get('email')} not found in org {org_id}. Defaulting to public visibility."
            )
            return user_info, "public"
            
    except httpx.TimeoutException:
        logger.error("Timeout fetching user permissions. Defaulting to public visibility.")
        return empty_user_info, "public"
    except Exception as e:
        logger.error(f"Error fetching user permissions: {e}. Defaulting to public visibility.")
        return empty_user_info, "public"


async def _resolve_org_schema(org_id: int) -> str:
    """
    Resolve organization ID to schema name.
    
    Args:
        org_id: Organization ID
        
    Returns:
        Organization schema name
        
    Raises:
        HTTPException: If org_id cannot be resolved
    """
    conn = None
    try:
        conn = get_database_connection()
        database = KnowledgeDatabase(conn)
        org_schema = await database.resolve_org_schema(str(org_id))
        return org_schema
    except ValueError as e:
        logger.error(f"Validation error resolving org schema: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error resolving org schema: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error resolving organization: {str(e)}")
    finally:
        if conn is not None:
            return_database_connection(conn)

def _resolve_org_slug(org_id: int) -> str:
    """
    Resolve organization ID to slug.
    
    Args:
        org_id: Organization ID
        
    Returns:
        Organization slug
    """
    conn = None
    try:
        conn = get_database_connection()
        database = KnowledgeDatabase(conn)
        org_slug = database.resolve_org_slug(org_id)
        return org_slug
    except Exception as e:
        logger.error(f"Error resolving org slug: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error resolving organization slug: {str(e)}")
    finally:
        if conn is not None:
            return_database_connection(conn)

@router.post("/query")
async def chat_stream(
    query_request: GrowthChatRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
) -> StreamingResponse:
    """
    Streaming chat endpoint for Growth Chat super graph.
    
    Routes between knowledge_base_agent and app_automation_agent based on user intent.
    Streams the agent's response as Server-Sent Events (SSE) with KnowledgeRAGResult format.
    
    Args:
        query_request: Growth chat request with query, conversation_id, org_id
        request: FastAPI request object
        authorization: Authorization header
        
    Returns:
        StreamingResponse with SSE events containing KnowledgeRAGResult objects
    """
    try:
        auth_token, user = _get_auth_token_and_user(request, authorization)
        message_text = query_request.query
        conversation_id = query_request.conversation_id
        org_id = query_request.org_id
        
        logger.info(
            f"Growth chat request from user {user.get('sub', 'unknown')}: "
            f"'{message_text[:50]}...' (conversation_id={conversation_id}, org_id={org_id})"
        )
        
        # Resolve org_id to schema
        org_schema = await _resolve_org_schema(org_id)
        org_slug = _resolve_org_slug(org_id)
        
        # Get user info and visibility level for knowledge hub based on their role
        user_info, knowledge_visibility = await _get_user_info_and_visibility(auth_token, org_id)

        user_info["org_slug"] = org_slug
        
        # Get attached files from request
        attached_files = query_request.attached_files
        
        # Log attached files for debugging
        if attached_files:
            logger.info(
                f"Received {len(attached_files)} attached files: "
                f"{[f.filename for f in attached_files]}"
            )
            for f in attached_files:
                logger.info(f"  - {f.filename}: bucket={f.gcs_bucket}, path={f.gcs_path}")
        else:
            logger.info("No attached files in request")
        
        # Event stream generator
        async def event_stream():
            """Generate Server-Sent Events stream with results."""
            try:
                async for result in stream_processing(
                    message=message_text,
                    conversation_id=conversation_id,
                    auth_token=auth_token,
                    org_id=org_id,
                    org_schema=org_schema,
                    org_slug=org_slug,
                    knowledge_visibility=knowledge_visibility,
                    user_info=user_info,
                    attached_files=attached_files,
                ):
                    # Convert result to JSON and format as SSE
                    result_json = result.model_dump()
                    sse_data = f"data: {json.dumps(result_json)}\n\n"
                    yield sse_data
                    
                    logger.info(
                        f"Streamed {result.stage} stage for query '{message_text[:30]}...'"
                    )
                
            except Exception as e:
                logger.error(
                    f"Error in stream processing: {str(e)}", exc_info=True
                )
                
                error_result = GrowthChatResult(
                    stage="answer",
                    query=message_text,
                    answer=f"Error during processing: {str(e)}"
                )
                
                error_json = error_result.model_dump()
                yield f"data: {json.dumps(error_json)}\n\n"
        
        # Return streaming response
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in growth chat endpoint: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/continue/{conversation_id}")
async def continue_processing(
    conversation_id: str,
    request: Request,
    authorization: Optional[str] = Header(None),
) -> StreamingResponse:
    """
    Continue a previously interrupted conversation.
    
    This endpoint allows resuming a conversation that was interrupted
    (e.g., due to timeout, network disconnect, or page navigation).
    It retrieves the conversation state from the checkpointer and
    continues processing from where it left off.
    
    Args:
        conversation_id: The conversation/thread ID to continue
        request: FastAPI request object
        authorization: Authorization header
        
    Returns:
        StreamingResponse with SSE events containing GrowthChatResult objects
        
    Raises:
        404: If conversation not found
        403: If conversation belongs to different user
        409: If conversation is already being processed
        410: If conversation has expired/been deleted
    """
    try:
        from src.utils.checkpointer import get_checkpointer
        
        auth_token, user = _get_auth_token_and_user(request, authorization)
        user_id = user.get("sub", "anonymous")
        
        logger.info(
            f"Continue request from user {user_id} for conversation {conversation_id}"
        )
        
        # Get checkpointer to verify conversation exists
        checkpointer = get_checkpointer()
        
        # Try to get the conversation state
        config = {"configurable": {"thread_id": conversation_id}}
        
        try:
            # Note: Different checkpointer implementations may have different APIs
            # This is a simplified check - in production you'd want more robust validation
            state = None
            if hasattr(checkpointer, 'get'):
                state = checkpointer.get(config)
            elif hasattr(checkpointer, 'aget'):
                state = await checkpointer.aget(config)
            
            if state is None:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Conversation '{conversation_id}' not found or has expired"
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error checking conversation state: {e}")
            raise HTTPException(
                status_code=404,
                detail=f"Conversation '{conversation_id}' not found"
            )
        
        # Get org info from conversation state if available
        # Default to extracting from conversation_id format or using defaults
        org_id = 0  # Will be populated from state if available
        org_schema = ""
        org_slug = ""
        
        # Try to get org info from the state
        if state and hasattr(state, 'values'):
            values = state.values
            org_id = values.get('org_id', 0)
            org_schema = values.get('org_schema', '')
        
        if org_id and not org_schema:
            try:
                org_schema = await _resolve_org_schema(org_id)
                org_slug = _resolve_org_slug(org_id)
            except Exception:
                pass
        
        # Get user info
        user_info, knowledge_visibility = await _get_user_info_and_visibility(auth_token, org_id)
        user_info["org_slug"] = org_slug
        
        # Event stream generator for continuation
        async def continue_stream():
            """Generate Server-Sent Events stream continuing from checkpoint."""
            try:
                # Send reconnecting stage first
                reconnect_result = GrowthChatResult(
                    stage="reconnecting",
                    query="",
                    message=f"Resuming conversation {conversation_id}..."
                )
                yield f"data: {json.dumps(reconnect_result.model_dump())}\n\n"
                
                # Continue streaming from the existing conversation
                # This will pick up from the last checkpoint
                async for result in stream_processing(
                    message="",  # Empty message - continuation from checkpoint
                    conversation_id=conversation_id,
                    auth_token=auth_token,
                    org_id=org_id,
                    org_schema=org_schema,
                    org_slug=org_slug,
                    knowledge_visibility=knowledge_visibility,
                    user_info=user_info,
                ):
                    result_json = result.model_dump()
                    yield f"data: {json.dumps(result_json)}\n\n"
                    
            except Exception as e:
                logger.error(f"Error in continue stream: {e}", exc_info=True)
                error_result = GrowthChatResult(
                    stage="error",
                    query="",
                    error_code=500,
                    error_message=f"Failed to continue conversation: {str(e)}",
                    retryable=True,
                )
                yield f"data: {json.dumps(error_result.model_dump())}\n\n"
        
        return StreamingResponse(
            continue_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in continue endpoint: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/config")
async def get_current_config(
    request: Request,
):
    """
    Get current Growth Chat super graph configuration.
    
    Args:
        request: FastAPI request object
        
    Returns:
        dict: Current configuration settings for the super graph
    """
    import os

    # Get LLM model configuration for sub-agents
    embeddings_model = os.environ.get("EMBEDDING_MODEL_NAME", "gemini-embedding-001")
    
    config = {
        "mode": "growth_chat_streaming",
        "sub_agents": ["knowledge_hub_agent", "app_automation_agent", "conversation", "forse_analyzer_agent"],
        "embeddings": {
            "model": embeddings_model,
            "dimensionality": 768,
            "provider": "google_gemini"
        },
        "llm": {
            "model": os.getenv("GROWTH_CHAT_ROUTER_MODEL"),
            "temperature": os.getenv("GROWTH_CHAT_ROUTER_TEMPERATURE"),
        },
        "streaming": {
            "enabled_by_default": True,
            "format": "server_sent_events",
            "stages": ["documents", "context", "answer"]
        },
        "langsmith": {
            "enabled": is_langsmith_enabled(),
            "project": os.getenv("LANGSMITH_PROJECT", "growth-chat"),
        },
    }
    
    return config


@router.get("/health")
async def health_check():
    """Basic health check endpoint for load balancers."""
    return {
        "status": "healthy",
        "service": "growth_chat",
        "description": "Unified agent combining knowledge_base and grants_admin",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/ready")
async def readiness_check():
    """
    Readiness check - verifies all dependencies are available.
    Returns 503 if any critical dependency is unhealthy.
    """
    from datetime import datetime
    from src.utils.checkpointer import health_check_checkpointer
    
    try:
        # Check checkpointer
        checkpointer_health = await health_check_checkpointer()
        
        # Check database connection (if configured)
        database_health = {"status": "healthy"}  # Placeholder - add actual DB check if needed
        
        checks = {
            "checkpointer": checkpointer_health,
            "database": database_health,
        }
        
        # Determine overall status
        all_healthy = all(
            c.get("status") == "healthy" 
            for c in checks.values()
        )
        any_unhealthy = any(
            c.get("status") == "unhealthy" 
            for c in checks.values()
        )
        
        overall_status = (
            "unhealthy" if any_unhealthy 
            else "healthy" if all_healthy 
            else "degraded"
        )
        
        status_code = 503 if overall_status == "unhealthy" else 200
        
        return JSONResponse(
            status_code=status_code,
            content={
                "status": overall_status,
                "checks": checks,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

