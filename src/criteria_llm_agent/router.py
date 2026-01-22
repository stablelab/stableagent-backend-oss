"""
FastAPI router for criteria evaluation endpoints.

Provides REST API for evaluating grant application criteria using AI.
"""
import os
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Import Privy authentication
from src.auth.deps import get_current_user
from src.utils.logger import logger

from .types import EvaluationRequest, AggregatedScore
from .evaluator import CriteriaEvaluator
from .database import CriteriaDatabase
from .model_factory import get_model_provider
from src.utils.db_utils import get_database_connection, return_database_connection
from .save_evaluation import save_evaluation_result
from .auth import require_evaluation_permission, require_batch_evaluation_permission

# Router with authentication required for all routes by default
router = APIRouter(dependencies=[Depends(get_current_user)])

# Include retrieval endpoints
from .retrieval_endpoints import router as retrieval_router
router.include_router(retrieval_router, tags=["evaluation-retrieval"])


class BatchEvaluationRequest(BaseModel):
    """
    Request for batch evaluation of multiple submissions.
    
    Note:
        Criteria are automatically fetched from the grant_form_selected_criteria
        connection table, which includes the weights for each criterion.
    """
    org_id: int
    form_id: int
    user_ids: List[int]
    team_id: Optional[int] = None


@router.post("/evaluate")
async def evaluate_criteria(
    eval_request: EvaluationRequest,
    request: Request
) -> AggregatedScore:
    """
    Evaluate all criteria for a user's form submission.
    
    This endpoint evaluates grant application criteria using AI, providing
    objective scoring based on the user's responses.
    
    Authentication: Requires Privy authentication (enforced by router-level dependency).
    Authorization:
        - Requires evaluation.trigger.own to evaluate your own submission, OR
        - Requires evaluation.read.all to evaluate any submission in the organization
    
    Args:
        eval_request: EvaluationRequest with org_id, form_id, user_id
        request: FastAPI request object (contains authenticated user in request.state.user)
        
    Returns:
        AggregatedScore with evaluation results and final score
        
    Raises:
        HTTPException: If validation fails, not authorized, or evaluation errors occur
    """
    user = request.state.user
    logger.info(
        f"Criteria evaluation request by user {user['sub']}: org_id={eval_request.org_id}, "
        f"form_id={eval_request.form_id}, user_id={eval_request.user_id}"
    )
    
    # Get database connection from pool
    conn = None
    try:
        conn = get_database_connection()
        
        database = CriteriaDatabase(conn)
        evaluator = CriteriaEvaluator(database)
        
        # Resolve org_id to schema name
        org_schema = await database.resolve_org_schema(eval_request.org_id)
        
        # Check authorization: user can evaluate their own submission OR have admin permissions
        require_evaluation_permission(user, eval_request.org_id, eval_request.user_id)
        
        # Perform evaluation
        # Criteria are automatically fetched from the connection table
        result = await evaluator.evaluate_submission(
            org_id=eval_request.org_id,
            form_id=eval_request.form_id,
            user_id=eval_request.user_id,
            team_id=eval_request.team_id
        )
        
        logger.info(
            f"Evaluation complete for user {eval_request.user_id}: "
            f"normalized_score={result.normalized_score:.2f}%"
        )
        
        # Save evaluation results to database using resolved schema
        try:
            evaluation_id = await save_evaluation_result(
                db_connection=conn,
                org_schema=org_schema,
                evaluation=result
            )
            logger.info(f"Evaluation results saved with ID: {evaluation_id}")
        except Exception as save_error:
            logger.error(f"Failed to save evaluation results: {save_error}")
            # Continue and return results even if save fails
        
        return result
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is (404, 403, etc.)
        raise
    except ValueError as e:
        logger.error(f"Validation error in criteria evaluation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in criteria evaluation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Internal server error during evaluation: {str(e)}"
        )
    finally:
        # Return connection to pool
        if conn is not None:
            return_database_connection(conn)


@router.post("/evaluate/batch")
async def evaluate_criteria_batch(
    eval_request: BatchEvaluationRequest,
    request: Request
) -> List[AggregatedScore]:
    """
    Evaluate criteria for multiple users' submissions on the same form.
    
    This endpoint allows batch evaluation for efficiency when reviewing
    multiple grant applications.
    
    Authentication: Requires Privy authentication (enforced by router-level dependency).
    Authorization: Requires evaluation.read.all permission in the organization.
    
    Args:
        eval_request: BatchEvaluationRequest with org_id, form_id, and list of user_ids
        request: FastAPI request object (contains authenticated user in request.state.user)
        
    Returns:
        List of AggregatedScore results, one per user
        
    Raises:
        HTTPException: If validation fails, not authorized, or evaluation errors occur
    """
    user = request.state.user
    logger.info(
        f"Batch criteria evaluation request by user {user['sub']}: org_id={eval_request.org_id}, "
        f"form_id={eval_request.form_id}, users={len(eval_request.user_ids)}"
    )
    
    if not eval_request.user_ids:
        raise HTTPException(status_code=400, detail="user_ids cannot be empty")
    
    if len(eval_request.user_ids) > 100:
        raise HTTPException(
            status_code=400, 
            detail="Maximum 100 users per batch request"
        )
    
    # Get database connection from pool
    conn = None
    try:
        conn = get_database_connection()
        
        database = CriteriaDatabase(conn)
        evaluator = CriteriaEvaluator(database)
        
        # Resolve org_id to schema name (once for batch, for saving)
        org_schema = await database.resolve_org_schema(eval_request.org_id)
        
        # Check authorization: batch evaluation requires admin permissions
        await require_batch_evaluation_permission(user, eval_request.org_id)
        
        # Perform batch evaluation
        # Criteria are automatically fetched from the connection table
        results = await evaluator.evaluate_batch_submissions(
            org_id=eval_request.org_id,
            form_id=eval_request.form_id,
            user_ids=eval_request.user_ids,
            team_id=eval_request.team_id
        )
        
        logger.info(f"Batch evaluation complete for {len(results)} users")
        
        # Save all evaluation results to database using resolved schema
        saved_count = 0
        for result in results:
            try:
                evaluation_id = await save_evaluation_result(
                    db_connection=conn,
                    org_schema=org_schema,
                    evaluation=result
                )
                saved_count += 1
                logger.debug(f"Saved evaluation {evaluation_id} for user {result.user_id}")
            except Exception as save_error:
                logger.error(f"Failed to save evaluation for user {result.user_id}: {save_error}")
                # Continue with other saves
        
        logger.info(f"Saved {saved_count}/{len(results)} evaluation results to database")
        
        return results
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is (404, 403, etc.)
        raise
    except ValueError as e:
        logger.error(f"Validation error in batch evaluation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in batch evaluation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Internal server error during batch evaluation: {str(e)}"
        )
    finally:
        # Return connection to pool
        if conn is not None:
            return_database_connection(conn)


@router.get("/health", dependencies=[])  # Override router-level auth - health is public
async def health_check():
    """
    Health check endpoint with model configuration info.
    
    This endpoint is public and does not require authentication.
    
    Returns:
        dict: Status information including current model configuration
    """
    # Get current model configuration
    model_name = (
        os.environ.get("CRITERIA_AGENT_MODEL") or
        os.environ.get("FORM_MODEL") or
        os.environ.get("DEFAULT_MODEL", "gpt-4")
    )
    
    provider = get_model_provider(model_name)
    temperature = float(os.environ.get("CRITERIA_AGENT_TEMPERATURE", "0.3"))
    json_mode = os.environ.get("CRITERIA_AGENT_JSON_MODE", "true").lower() == "true"
    
    # Check API key availability for current provider
    api_key_status = "unknown"
    if provider == "openai":
        api_key_status = "available" if os.environ.get("OPENAI_API_KEY") else "missing"
    elif provider == "anthropic":
        api_key_status = "available" if os.environ.get("ANTHROPIC_API_KEY") else "missing"
    elif provider == "gemini":
        gcp_project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
        try:
            from src.config.common_settings import PROJECT_ID, credentials
            if (gcp_project or PROJECT_ID) and credentials:
                api_key_status = "available (Google Cloud JSON)"
            else:
                api_key_status = "missing (no credentials)"
        except Exception:
            api_key_status = "available (project only)" if gcp_project else "missing"
    elif provider == "xai":
        api_key_status = "available" if os.environ.get("X_AI_API_KEY") else "missing"
    
    return {
        "status": "healthy",
        "service": "criteria_llm_agent",
        "version": "1.0.0",
        "model_config": {
            "model_name": model_name,
            "provider": provider,
            "temperature": temperature,
            "json_mode": json_mode,
            "api_key_status": api_key_status
        },
        "supported_providers": ["openai", "anthropic", "gemini", "xai"],
        "features": {
            "parallel_evaluation": True,
            "batch_processing": True,
            "weighted_scoring": True,
            "scoring_levels": [0, 20, 33, 50, 66, 80, 100]
        },
        "environment_variables": {
            "CRITERIA_AGENT_MODEL": "Specific model for criteria agent",
            "FORM_MODEL": "General form model fallback",
            "DEFAULT_MODEL": "Global model fallback",
            "CRITERIA_AGENT_TEMPERATURE": "Temperature setting (default: 0.3)",
            "CRITERIA_AGENT_JSON_MODE": "Enable JSON mode (default: true)"
        }
    }


@router.get("/config")
async def get_current_config(request: Request):
    """
    Get current criteria agent configuration.
    
    Authentication: Requires Privy authentication (enforced by router-level dependency).
    
    Args:
        request: FastAPI request object (contains authenticated user in request.state.user)
        
    Returns:
        dict: Current configuration settings
    """
    
    model_name = (
        os.environ.get("CRITERIA_AGENT_MODEL") or
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
            "temperature": float(os.environ.get("CRITERIA_AGENT_TEMPERATURE", "0.3")),
            "json_mode": os.environ.get("CRITERIA_AGENT_JSON_MODE", "true").lower() == "true"
        },
        "evaluation": {
            "scoring_levels": [0, 20, 33, 50, 66, 80, 100],
            "scoring_description": {
                "0": "Completely fails to meet the criterion",
                "20": "Minimal effort, significantly below expectations",
                "33": "Below expectations, major improvements needed",
                "50": "Meets basic expectations, but with notable gaps",
                "66": "Meets expectations with minor areas for improvement",
                "80": "Exceeds expectations in most aspects",
                "100": "Exceptional, fully exceeds all expectations"
            }
        },
        "environment_variables": {
            "CRITERIA_AGENT_MODEL": os.environ.get("CRITERIA_AGENT_MODEL"),
            "FORM_MODEL": os.environ.get("FORM_MODEL"),
            "DEFAULT_MODEL": os.environ.get("DEFAULT_MODEL"),
            "CRITERIA_AGENT_TEMPERATURE": os.environ.get("CRITERIA_AGENT_TEMPERATURE"),
            "CRITERIA_AGENT_JSON_MODE": os.environ.get("CRITERIA_AGENT_JSON_MODE")
        }
    }
    
    # Determine model source
    if os.environ.get("CRITERIA_AGENT_MODEL"):
        config["model_selection"]["source"] = "CRITERIA_AGENT_MODEL (highest priority)"
    elif os.environ.get("FORM_MODEL"):
        config["model_selection"]["source"] = "FORM_MODEL (medium priority)"
    elif os.environ.get("DEFAULT_MODEL"):
        config["model_selection"]["source"] = "DEFAULT_MODEL (low priority)"
    
    return config
