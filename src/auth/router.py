"""
Authentication endpoints.

Provides endpoints for authentication-related operations like
getting current user information.
"""

from fastapi import APIRouter, Depends
from typing import Dict, Any
from src.auth.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["authentication"])

@router.get("/me")
async def get_me(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Get current authenticated user information.

    Returns the authenticated user's credentials and permissions.
    Requires a valid Privy ID token in headers or cookies.

    Returns:
        User object with:
        - sub: User ID
        - email: User email address
        - handle: User handle/username
        - flags: User flags (is_global_admin)
        - orgPermissions: Organization permissions by org ID
        - teamPermissions: Team permissions by team ID
        - privy: Full Privy user object (includes all Privy account data)

    Raises:
        401: If not authenticated or invalid token
    """
    # Return user info without the function references
    # (functions can't be serialized to JSON)
    return {
        "sub": user["sub"],
        "email": user["email"],
        "handle": user["handle"],
        "flags": user["flags"],
        "orgPermissions": user["orgPermissions"],
        "teamPermissions": user["teamPermissions"],
        "privy": user["privy"],
    }

