"""
FastAPI dependencies for authentication.

Provides dependency functions for protecting routes and accessing
the authenticated user.
"""

from typing import Dict, Any, Optional
from fastapi import Request, HTTPException, status


def get_current_user(request: Request) -> Dict[str, Any]:
    """
    FastAPI dependency to get the current authenticated user.

    This dependency should be used in route handlers that require authentication.
    The middleware must run before this dependency is called.

    Args:
        request: FastAPI request object

    Returns:
        User dict with authentication and permission information

    Raises:
        HTTPException: 401 if user is not authenticated

    Example:
        @app.get("/protected")
        async def protected_route(user: dict = Depends(get_current_user)):
            return {"user_id": user["sub"]}
    """
    print(f"request.state.user: {request.state}")
    if not hasattr(request.state, "user") or request.state.user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    print(f"USER! request.state.user: {request.state.user}")

    return request.state.user


def require_permission(permission: str, org_id: Optional[int] = None):
    """
    Create a dependency that requires a specific organization permission.

    Args:
        permission: Permission key to check (e.g., "org.write")
        org_id: Organization ID to check permission for

    Returns:
        Dependency function that checks the permission

    Example:
        @app.get("/org/{org_id}/settings")
        async def update_settings(
            org_id: int,
            user: dict = Depends(get_current_user),
            _: None = Depends(require_permission("org.write", org_id))
        ):
            return {"message": "Settings updated"}
    """

    def permission_checker(request: Request) -> None:
        user = get_current_user(request)
        has_perm = user["hasPermission"](org_id, permission)

        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
            )

    return permission_checker


def require_team_permission(permission: str, team_id: Optional[int] = None):
    """
    Create a dependency that requires a specific team permission.

    Args:
        permission: Permission key to check (e.g., "team.update")
        team_id: Team ID to check permission for

    Returns:
        Dependency function that checks the permission

    Example:
        @app.post("/team/{team_id}/invite")
        async def invite_member(
            team_id: int,
            user: dict = Depends(get_current_user),
            _: None = Depends(require_team_permission("team.member.invite", team_id))
        ):
            return {"message": "Invitation sent"}
    """

    def permission_checker(request: Request) -> None:
        user = get_current_user(request)
        has_perm = user["hasTeamPermission"](team_id, permission)

        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required team permission: {permission}",
            )

    return permission_checker


def require_global_admin(request: Request) -> None:
    """
    Dependency that requires the user to be a global admin.

    Args:
        request: FastAPI request object

    Raises:
        HTTPException: 403 if user is not a global admin

    Example:
        @app.get("/admin/dashboard")
        async def admin_dashboard(
            user: dict = Depends(get_current_user),
            _: None = Depends(require_global_admin)
        ):
            return {"message": "Admin dashboard"}
    """
    user = get_current_user(request)

    if not user["flags"].get("is_global_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Global admin access required",
        )

