"""
Authentication and authorization helpers for Criteria LLM Agent.

Provides permission checks for evaluation endpoints using Privy authentication.
"""

from typing import Dict, Any, Optional
from fastapi import HTTPException, status
import logging

logger = logging.getLogger(__name__)


def can_evaluate_submission(
    user: Dict[str, Any],
    org_id: int,
    user_id: int
) -> bool:
    """
    Check if the authenticated user can evaluate a submission.
    
    A user can evaluate if:
    1. They have evaluation.trigger.own permission AND are evaluating their own submission, OR
    2. They have evaluation.read.all permission (can evaluate anyone)
    
    Args:
        user: Authenticated user object from middleware
        org_id: Organization ID
        user_id: User ID whose submission is being evaluated
        
    Returns:
        True if authorized, False otherwise
    """
    # Check if user has evaluation permissions in the org
    has_trigger_own = user["hasPermission"](org_id, "evaluation.trigger.own")
    has_read_all = user["hasPermission"](org_id, "evaluation.read.all")
    
    # Admin with read.all can evaluate anyone
    if has_read_all:
        return True
    
    # User with trigger.own can only evaluate their own submission
    if has_trigger_own and user["sub"] == user_id:
        return True
    
    return False


def require_evaluation_permission(
    user: Dict[str, Any],
    org_id: int,
    user_id: int
) -> None:
    """
    Require that the user has permission to evaluate a submission.
    
    Raises HTTPException if not authorized.
    
    Args:
        user: Authenticated user object from middleware
        org_id: Organization ID
        user_id: User ID whose submission is being evaluated
        
    Raises:
        HTTPException: 403 if user lacks permission
    """
    # Special case: global admins can evaluate anything
    if user["flags"].get("is_global_admin", False):
        return
    
    # Check permissions
    if not can_evaluate_submission(user, org_id, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Requires evaluation.trigger.own permission to evaluate your own submission, "
                "or evaluation.read.all permission to evaluate any submission in this organization"
            )
        )


async def require_batch_evaluation_permission(
    user: Dict[str, Any],
    org_id: int
) -> None:
    """
    Require that the user has permission to perform batch evaluations.
    
    Batch evaluations require admin permissions in the organization.
    
    Args:
        user: Authenticated user object from middleware
        org_id: Organization ID
        
    Raises:
        HTTPException: 403 if user lacks permission
    """
    # Special case: global admins can batch evaluate anything
    if user["flags"].get("is_global_admin", False):
        return
    
    # For batch operations, require admin-level permissions
    has_read_all = user["hasPermission"](org_id, "evaluation.read.all")
    
    if not has_read_all:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Batch evaluation requires evaluation.read.all permission in this organization"
        )

