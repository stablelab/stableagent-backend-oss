"""
API endpoints for retrieving saved evaluation results.

Provides endpoints to query evaluation history and results.
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from src.auth.deps import get_current_user
from src.utils.logger import logger
from src.utils.db_utils import get_database_connection, return_database_connection

from .database import CriteriaDatabase
from .save_evaluation import get_latest_evaluation
from .auth import require_evaluation_permission

router = APIRouter()


class EvaluationSummary(BaseModel):
    """Summary of a saved evaluation."""
    evaluation_id: int
    form_id: int
    user_id: int
    normalized_score: float
    evaluated_at: str


class EvaluationDetail(BaseModel):
    """Detailed evaluation with all criterion scores."""
    evaluation_id: int
    form_id: int
    user_id: int
    total_weighted_score: float
    max_possible_score: float
    normalized_score: float
    reasoning: Optional[str]
    evaluation_timestamp: str
    criteria_evaluations: List[Dict[str, Any]]


@router.get("/evaluations/latest")
async def get_latest_user_evaluation(
    org_id: int,
    form_id: int,
    user_id: int,
    user: Dict[str, Any] = Depends(get_current_user)
) -> EvaluationDetail:
    """
    Get the most recent evaluation for a user's form submission.
    
    Authentication: Requires Privy authentication.
    Authorization: 
        - Requires evaluation.trigger.own to view your own evaluation, OR
        - Requires evaluation.read.all to view any evaluation in the organization
    
    Args:
        org_id: Organization ID
        form_id: Form ID
        user_id: User ID whose evaluation to retrieve
        user: Authenticated user from middleware
        
    Returns:
        EvaluationDetail with full evaluation data
        
    Raises:
        HTTPException: If not authorized or evaluation not found
    """
    conn = None
    try:
        conn = get_database_connection()
        database = CriteriaDatabase(conn)
        
        # Resolve org_id to schema
        org_schema = await database.resolve_org_schema(org_id)
        
        # Check authorization
        require_evaluation_permission(user, org_id, user_id)
        
        # Retrieve evaluation
        evaluation = await get_latest_evaluation(
            db_connection=conn,
            org_schema=org_schema,
            form_id=form_id,
            user_id=user_id
        )
        
        if not evaluation:
            raise HTTPException(
                status_code=404,
                detail=f"No evaluation found for user {user_id} on form {form_id}"
            )
        
        logger.info(
            f"Retrieved evaluation {evaluation['evaluation_id']} for user {user_id} "
            f"by user {user['sub']}"
        )
        
        return EvaluationDetail(**evaluation)
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is (404, 403, etc.)
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving evaluation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve evaluation: {str(e)}"
        )
    finally:
        if conn:
            return_database_connection(conn)


@router.get("/evaluations/history")
async def get_user_evaluation_history(
    org_id: int,
    form_id: int,
    user_id: int,
    limit: int = Query(default=10, ge=1, le=100),
    user: Dict[str, Any] = Depends(get_current_user)
) -> List[EvaluationSummary]:
    """
    Get evaluation history for a user's form submission.
    
    Returns a list of all evaluations, most recent first.
    
    Authentication: Requires Privy authentication.
    Authorization:
        - Requires evaluation.trigger.own to view your own history, OR
        - Requires evaluation.read.all to view any user's history in the organization
    
    Args:
        org_id: Organization ID
        form_id: Form ID
        user_id: User ID whose history to retrieve
        limit: Maximum number of results (default 10, max 100)
        user: Authenticated user from middleware
        
    Returns:
        List of EvaluationSummary objects
        
    Raises:
        HTTPException: If not authorized
    """
    conn = None
    try:
        conn = get_database_connection()
        database = CriteriaDatabase(conn)
        
        # Resolve org_id to schema
        org_schema = await database.resolve_org_schema(org_id)
        
        # Check authorization
        require_evaluation_permission(user, org_id, user_id)
        
        # Query evaluation history
        cursor = conn.cursor()
        query = f"""
            SELECT 
                id as evaluation_id,
                id_form as form_id,
                id_user as user_id,
                normalized_score,
                evaluated_at
            FROM {org_schema}.grant_form_ai_evaluations
            WHERE id_form = %s AND id_user = %s
            ORDER BY evaluated_at DESC
            LIMIT %s
        """
        
        cursor.execute(query, [form_id, user_id, limit])
        
        results = []
        for row in cursor.fetchall():
            results.append(EvaluationSummary(
                evaluation_id=row[0],
                form_id=row[1],
                user_id=row[2],
                normalized_score=float(row[3]),
                evaluated_at=row[4].isoformat() if row[4] else None
            ))
        
        cursor.close()
        
        logger.info(
            f"Retrieved {len(results)} evaluations for user {user_id} "
            f"by user {user['sub']}"
        )
        
        return results
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is (404, 403, etc.)
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving evaluation history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve evaluation history: {str(e)}"
        )
    finally:
        if conn:
            return_database_connection(conn)


@router.get("/evaluations/form/{form_id}/all")
async def get_all_form_evaluations(
    org_id: int,
    form_id: int,
    limit: int = Query(default=100, ge=1, le=1000),
    user: Dict[str, Any] = Depends(get_current_user)
) -> List[EvaluationSummary]:
    """
    Get all latest evaluations for all users on a form.
    
    Admin only - requires evaluation.read.all permission.
    
    Authentication: Requires Privy authentication.
    Authorization: Requires evaluation.read.all permission in the organization.
    
    Args:
        org_id: Organization ID
        form_id: Form ID
        limit: Maximum number of results (default 100, max 1000)
        user: Authenticated user from middleware
        
    Returns:
        List of EvaluationSummary objects (one per user, latest evaluation)
        
    Raises:
        HTTPException: If not authorized
    """
    conn = None
    try:
        conn = get_database_connection()
        database = CriteriaDatabase(conn)
        
        # Resolve org_id to schema
        org_schema = await database.resolve_org_schema(org_id)
        
        # Check authorization - must have admin permission
        if not user["flags"].get("is_global_admin"):
            if not user["hasPermission"](org_id, "evaluation.read.all"):
                raise HTTPException(
                    status_code=403,
                    detail="Requires evaluation.read.all permission"
                )
        
        # Query latest evaluation for each user
        cursor = conn.cursor()
        query = f"""
            SELECT DISTINCT ON (id_user)
                id as evaluation_id,
                id_form as form_id,
                id_user as user_id,
                normalized_score,
                evaluated_at
            FROM {org_schema}.grant_form_ai_evaluations
            WHERE id_form = %s
            ORDER BY id_user, evaluated_at DESC
            LIMIT %s
        """
        
        cursor.execute(query, [form_id, limit])
        
        results = []
        for row in cursor.fetchall():
            results.append(EvaluationSummary(
                evaluation_id=row[0],
                form_id=row[1],
                user_id=row[2],
                normalized_score=float(row[3]),
                evaluated_at=row[4].isoformat() if row[4] else None
            ))
        
        cursor.close()
        
        logger.info(
            f"Retrieved {len(results)} evaluations for form {form_id} "
            f"by admin user {user['sub']}"
        )
        
        return results
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is (404, 403, etc.)
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving form evaluations: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve form evaluations: {str(e)}"
        )
    finally:
        if conn:
            return_database_connection(conn)

