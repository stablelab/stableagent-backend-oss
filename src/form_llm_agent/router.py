"""
FastAPI router for LangGraph form processing with multi-field support.

Provides streaming endpoint for processing field IDs with LangGraph integration.
Supports step-prefixed field IDs and multiple field processing.
"""
import json
import os
import asyncio
from typing import Optional, Dict, Any, List, Union
from fastapi import APIRouter, HTTPException, Header, Query, Body, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Import Privy authentication
from src.auth.deps import get_current_user
from src.utils.logger import logger

from .graph import stream_field_processing, stream_field_processing_with_context
from .types import LangGraphResult
from .model_factory import get_model_provider, is_anthropic_model, is_gemini_model, is_xai_model, is_anthropic_available, is_vertex_available
from .performance_logger import performance_logger, track_operation


class FormProcessingRequest(BaseModel):
    """Request model for form processing with evaluation instructions and current values."""
    id_requested: Union[str, List[str]]  # Single field ID or list of field IDs
    values: Optional[Dict[str, Any]] = {}
    form: Dict[str, Any]
    org_id: Optional[int] = None  # Optional organization ID for permission checking


# Router with authentication required for all routes by default
router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/process")
async def process_field_stream(
    request: Request,
    field_id: str = Query(..., description="The ID of the field to process"),
    org_id: Optional[int] = Query(None, description="Optional organization ID for permission checking")
):
    """
    Stream LangGraph processing results for a given field ID.

    This endpoint processes a field ID through a simple LangGraph workflow
    and streams the results in Server-Sent Events format.
    
    Authentication: Requires Privy authentication (enforced by router-level dependency).
    Authorization: If org_id provided, user must have submission.create permission.

    Args:
        field_id: The field identifier to process
        org_id: Optional organization ID for permission checking
        request: FastAPI request object (contains authenticated user in request.state.user)

    Returns:
        StreamingResponse with LangGraph results

    Raises:
        HTTPException: If field_id is empty, authentication fails, or lacking permissions
    """
    user = request.state.user
    logger.info(f"Form agent GET /process request by user {user['sub']}: field_id={field_id}, org_id={org_id}")
    
    # Check organization permission if org_id provided
    if org_id is not None:
        has_permission = user["flags"].get("is_global_admin", False) or user["hasPermission"](org_id, "submission.create")
        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail="Requires submission.create permission for this organization"
            )

    # Validate field_id
    if not field_id or not field_id.strip():
        raise HTTPException(
            status_code=400,
            detail="field_id parameter cannot be empty"
        )

    logger.info(f"Processing field ID: {field_id}")

    async def event_stream():
        """Generate Server-Sent Events stream with performance logging."""
        # Track the entire streaming request
        with track_operation(
            operation="http_streaming_request",
            field_id=field_id
        ) as request_operation_id:

            try:
                # Stream results from LangGraph processing
                async for result in stream_field_processing(field_id.strip()):
                    # Convert result to JSON and format as SSE
                    result_json = result.model_dump()
                    sse_data = f"data: {json.dumps(result_json)}\n\n"
                    yield sse_data

                    # Log the result with performance context
                    logger.info(
                        f"Streamed result for field {field_id}: {result.type}")

            except Exception as e:
                # Stream error response
                logger.error(
                    f"Error processing field {field_id}: {str(e)}", exc_info=True)

                error_result = LangGraphResult(
                    id=f"advice_{field_id}",
                    field_id=field_id,
                    response=f"Streaming error: {str(e)}",
                    type="issue",
                    is_error=True,
                    is_clear=False,
                    server_error=True,
                    note="streaming error"
                )

                yield f"data: {json.dumps(error_result.model_dump())}\n\n"

                # The context manager will handle the error logging
                raise

            # End of stream marker
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


def find_field_in_form(form_data: Dict[str, Any], field_id: str) -> Optional[Dict[str, Any]]:
    """
    Find a field by ID in the form structure and return its configuration.

    Supports both simple field IDs and step-prefixed IDs (e.g., "basic-info.title").

    Args:
        form_data: The complete form configuration
        field_id: The ID of the field to find (e.g., "title" or "basic-info.title")

    Returns:
        Field configuration dictionary or None if not found
    """
    if not form_data.get("steps"):
        return None

    # Parse step-prefixed field ID
    if "." in field_id:
        step_id, actual_field_id = field_id.split(".", 1)
    else:
        step_id = None
        actual_field_id = field_id

    # Search through all steps and fields
    for step in form_data["steps"]:
        if not step.get("fields"):
            continue

        # If step_id is specified, only search in that step
        if step_id and step.get("id") != step_id:
            continue

        for field in step["fields"]:
            # Direct field match
            if field.get("id") == actual_field_id:
                return field

            # Check nested fields in arrays (like teamMembers, milestones)
            if field.get("itemSchema"):
                for nested_field_id, nested_field in field["itemSchema"].items():
                    if nested_field_id == actual_field_id:
                        return nested_field

    return None


@router.post("/process")
async def process_field_with_form_context(
    form_request: FormProcessingRequest,
    request: Request
):
    """
    Minimal flow: incoming -> parsing -> call -> response stream.

    Processes one or multiple fields with form context and evaluation instructions.
    Supports step-prefixed field IDs (e.g., "basic-info.title").
    
    Authentication: Requires Privy authentication (enforced by router-level dependency).
    Authorization: If org_id provided in request, user must have submission.create permission.

    Args:
        form_request: FormProcessingRequest containing id_requested (str or list) and form data
        request: FastAPI request object (contains authenticated user in request.state.user)

    Returns:
        StreamingResponse with enhanced advice, yielding results as they become ready
        
    Raises:
        HTTPException: If authentication fails or lacking permissions
    """
    user = request.state.user
    logger.info(f"Form agent POST /process request by user {user['sub']}, org_id={form_request.org_id}")
    
    # Check organization permission if org_id provided
    if form_request.org_id is not None:
        has_permission = user["flags"].get("is_global_admin", False) or user["hasPermission"](form_request.org_id, "submission.create")
        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail="Requires submission.create permission for this organization"
            )

    # Handle both single field ID and list of field IDs
    if isinstance(form_request.id_requested, str):
        field_ids = [form_request.id_requested.strip()]
    else:
        field_ids = [fid.strip()
                     for fid in form_request.id_requested if fid.strip()]

    if not field_ids:
        raise HTTPException(
            status_code=400, detail="id_requested cannot be empty")

    logger.info(f"Processing {len(field_ids)} field(s): {field_ids}")

    # 3. CALL -> 4. RESPONSE: Stream multiple fields
    async def stream_multiple_responses():

        async def process_single_field(field_id: str):
            """Process a single field and return the result."""
            try:
                # 2. PARSING: Extract field context and current value
                field_config = find_field_in_form(form_request.form, field_id)
                if not field_config:
                    return LangGraphResult(
                        id=f"advice_{field_id}",
                        field_id=field_id,
                        response=f"Field '{field_id}' not found in form structure",
                        type="issue",
                        is_error=True,
                        is_clear=False,
                        server_error=True,
                        note="field not found"
                    )

                # Check if AI evaluation is disabled for this field (default is True)
                ai_evaluation_enabled = field_config.get("props", {}).get("aiEvaluation", True)
                if not ai_evaluation_enabled:
                    return LangGraphResult(
                        id=f"advice_{field_id}",
                        field_id=field_id,
                        response="",
                        type="advice",
                        is_error=False,
                        is_clear=True,
                        server_error=False,
                        note="AI evaluation disabled for this field"
                    )

                evaluation_instructions = field_config.get(
                    "props", {}).get("evaluationInstructions", "")
                field_label = field_config.get("label", field_id)
                field_type = field_config.get("type", "text")
                field_description = field_config.get("description", "")
                validation_rules = field_config.get("validation", {})

                # Get current value for the field (gracefully handle missing values)
                current_value = form_request.values.get(
                    field_id) if form_request.values else None

                # If no current value, return empty response
                if current_value is None:
                    return LangGraphResult(
                        id=f"advice_{field_id}",
                        field_id=field_id,
                        response="",
                        type="advice",
                        is_error=False,
                        is_clear=False,
                        server_error=True,
                        note="no value provided"
                    )

                # Process with current value for specific feedback
                async for result in stream_field_processing_with_context(
                    field_id=field_id,
                    field_label=field_label,
                    field_type=field_type,
                    field_description=field_description,
                    evaluation_instructions=evaluation_instructions,
                    validation_rules=validation_rules,
                    current_value=current_value
                ):
                    # Handle case where AI returns no response
                    if not result.response or result.response.strip() == "":
                        # AI returned empty response, mark as cleared
                        return LangGraphResult(
                            id=result.id,
                            field_id=result.field_id,
                            response="",
                            type="advice",
                            is_error=False,
                            is_clear=True,
                            server_error=False,
                            note="no AI response"
                        )
                    else:
                        # AI provided feedback, use as-is
                        return result

            except Exception as e:
                return LangGraphResult(
                    id=f"advice_{field_id}",
                    field_id=field_id,
                    response=f"Error: {str(e)}",
                    type="issue",
                    is_error=True,
                    is_clear=False,
                    server_error=True,
                    note="processing error"
                )

        try:
            # Create tasks for all field IDs to process them concurrently
            tasks = [process_single_field(field_id) for field_id in field_ids]

            # Process fields concurrently and yield results as they complete
            for completed_task in asyncio.as_completed(tasks):
                try:
                    result = await completed_task
                    yield f"data: {json.dumps(result.model_dump())}\n\n"
                except Exception as e:
                    # Handle task-level errors
                    error_result = LangGraphResult(
                        id="advice_unknown",
                        field_id="unknown",
                        response=f"Task error: {str(e)}",
                        type="issue",
                        is_error=True,
                        is_clear=False,
                        server_error=True,
                        note="task processing error"
                    )
                    yield f"data: {json.dumps(error_result.model_dump())}\n\n"

        except Exception as e:
            # Handle top-level errors
            error_result = LangGraphResult(
                id="advice_system",
                field_id="system",
                response=f"System error: {str(e)}",
                type="issue",
                is_error=True,
                isClear=False,
                note="system error"
            )
            yield f"data: {json.dumps(error_result.model_dump())}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_multiple_responses(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/health", dependencies=[])  # Override router-level auth - health is public
async def health_check():
    """
    Enhanced health check endpoint with model configuration info.
    
    This endpoint is public and does not require authentication.

    Returns:
        dict: Status information including current model configuration
    """
    # Get current model configuration
    model_name = (
        os.environ.get("FORM_AGENT_MODEL") or
        os.environ.get("FORM_MODEL") or
        os.environ.get("DEFAULT_MODEL", "gpt-4")
    )

    provider = get_model_provider(model_name)
    temperature = float(os.environ.get("FORM_AGENT_TEMPERATURE", "0.3"))
    json_mode = os.environ.get(
        "FORM_AGENT_JSON_MODE", "true").lower() == "true"

    # Check API key availability for current provider
    api_key_status = "unknown"
    if provider == "openai":
        api_key_status = "available" if os.environ.get(
            "OPENAI_API_KEY") else "missing"
    elif provider == "anthropic":
        api_key_status = "available" if os.environ.get(
            "ANTHROPIC_API_KEY") else "missing"
    elif provider == "gemini":
        # Gemini uses Google Cloud JSON authentication
        gcp_project = os.environ.get(
            "GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
        try:
            from src.config.common_settings import PROJECT_ID, credentials
            if (gcp_project or PROJECT_ID) and credentials:
                api_key_status = "available (Google Cloud JSON)"
            else:
                api_key_status = "missing (no credentials)"
        except Exception:
            api_key_status = "available (project only)" if gcp_project else "missing"
    elif provider == "xai":
        api_key_status = "available" if os.environ.get(
            "X_AI_API_KEY") else "missing"

    return {
        "status": "healthy",
        "service": "form_llm_agent",
        "version": "2.0.0",
        "model_config": {
            "model_name": model_name,
            "provider": provider,
            "temperature": temperature,
            "json_mode": json_mode,
            "api_key_status": api_key_status
        },
        "supported_providers": ["openai", "anthropic", "gemini", "xai"],
        "features": {
            "step_prefixed_ids": True,
            "multiple_field_processing": True,
            "isClear_flag": True,
            "value_based_feedback": True
        },
        "environment_variables": {
            "FORM_AGENT_MODEL": "Specific model for form agent",
            "FORM_MODEL": "General form model fallback",
            "DEFAULT_MODEL": "Global model fallback",
            "FORM_AGENT_TEMPERATURE": "Temperature setting (default: 0.3)",
            "FORM_AGENT_JSON_MODE": "Enable JSON mode (default: true)"
        }
    }


@router.get("/models")
async def list_supported_models(request: Request):
    """
    List all supported models and their providers.
    
    Authentication: Requires Privy authentication (enforced by router-level dependency).

    Args:
        request: FastAPI request object (contains authenticated user in request.state.user)

    Returns:
        dict: Available models organized by provider
    """

    models_by_provider = {
        "openai": [
            "gpt-4", "gpt-4o", "gpt-4-turbo",
            "gpt-3.5-turbo", "gpt-4o-mini"
        ],
        "anthropic": [
            "claude-3-opus", "claude-3-sonnet", "claude-3-haiku",
            "claude-2.1", "claude-instant-1.2"
        ],
        "gemini": [
            "gemini-3-flash-preview-lite", "gemini-3-flash-preview", "gemini-2.0-flash-lite",
            "gemini-1.5-pro", "gemini-1.0-pro"
        ],
        "xai": [
            "grok-4-fast-reasoning", "grok-4-fast-non-reasoning", "grok-code-fast-1",
            "grok-2", "grok-3-mini"
        ]
    }

    # Add provider detection examples
    model_examples = {}
    for provider, models in models_by_provider.items():
        model_examples[provider] = []
        for model in models[:2]:  # Show first 2 as examples
            model_examples[provider].append({
                "model": model,
                "provider_detected": get_model_provider(model),
                "is_anthropic": is_anthropic_model(model),
                "is_gemini": is_gemini_model(model),
                "is_xai": is_xai_model(model),
                "supports_json_mode": provider in ["openai", "xai"]
            })

    return {
        "supported_models": models_by_provider,
        "detection_examples": model_examples,
        "current_model": os.environ.get("FORM_AGENT_MODEL") or os.environ.get("FORM_MODEL") or os.environ.get("DEFAULT_MODEL", "gpt-4"),
        "note": "Use FORM_AGENT_MODEL, FORM_MODEL, or DEFAULT_MODEL environment variable to configure"
    }


@router.get("/config")
async def get_current_config(request: Request):
    """
    Get current form LLM agent configuration.
    
    Authentication: Requires Privy authentication (enforced by router-level dependency).

    Args:
        request: FastAPI request object (contains authenticated user in request.state.user)

    Returns:
        dict: Current configuration settings
    """

    model_name = (
        os.environ.get("FORM_AGENT_MODEL") or
        os.environ.get("FORM_MODEL") or
        os.environ.get("DEFAULT_MODEL", "gpt-4")
    )

    provider = get_model_provider(model_name)

    config = {
        "model_selection": {
            "current_model": model_name,
            "provider": provider,
            "source": "DEFAULT_MODEL (fallback)"
        },
        "settings": {
            "temperature": float(os.environ.get("FORM_AGENT_TEMPERATURE", "0.3")),
            "json_mode": os.environ.get("FORM_AGENT_JSON_MODE", "true").lower() == "true"
        },
        "environment_variables": {
            "FORM_AGENT_MODEL": os.environ.get("FORM_AGENT_MODEL"),
            "FORM_MODEL": os.environ.get("FORM_MODEL"),
            "DEFAULT_MODEL": os.environ.get("DEFAULT_MODEL"),
            "FORM_AGENT_TEMPERATURE": os.environ.get("FORM_AGENT_TEMPERATURE"),
            "FORM_AGENT_JSON_MODE": os.environ.get("FORM_AGENT_JSON_MODE")
        },
        "package_availability": {
            "anthropic": is_anthropic_available(),
            "vertex_ai": is_vertex_available()
        },
        "provider_requirements": {
            "openai": {
                "required": ["OPENAI_API_KEY"],
                "optional": [],
                "package_available": True
            },
            "anthropic": {
                "required": ["ANTHROPIC_API_KEY"],
                "optional": [],
                "package_available": is_anthropic_available()
            },
            "gemini": {
                "required": ["GOOGLE_CLOUD_PROJECT", ".gcloud.json file or Google Cloud credentials"],
                "optional": ["VERTEX_LOCATION"],
                "authentication": "Google Cloud JSON (not API key)",
                "package_available": is_vertex_available()
            },
            "xai": {
                "required": ["X_AI_API_KEY"],
                "optional": ["XAI_BASE_URL"],
                "package_available": True
            }
        }
    }

    # Determine model source
    if os.environ.get("FORM_AGENT_MODEL"):
        config["model_selection"]["source"] = "FORM_AGENT_MODEL (highest priority)"
    elif os.environ.get("FORM_MODEL"):
        config["model_selection"]["source"] = "FORM_MODEL (medium priority)"
    elif os.environ.get("DEFAULT_MODEL"):
        config["model_selection"]["source"] = "DEFAULT_MODEL (low priority)"

    return config
